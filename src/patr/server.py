import base64
import hashlib
import re
import secrets
import tomllib
import time
import urllib.request

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
)
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from patr import state
from patr.auth import (
    OAUTH_CALLBACK,
    _oauth_state_store,
    auth_status,
    get_auth,
    oauth_redirect_uri,
)
from patr.config import (
    build_hugo,
    load_hugo_config,
    load_newsletter_config,
    save_hugo_patr_params,
)
from patr.contacts import fetch_contacts, get_already_sent, log_sent
from patr.content import build_email_html, load_edition, load_footer, get_editions
from patr.gmail import send_email

app = Flask(__name__)


@app.route("/images/<path:filename>")
def static_images(filename):
    return send_from_directory(state.REPO_ROOT / "static", filename)


@app.route("/")
def index():
    cfg = load_newsletter_config()
    unconfigured = not cfg.get("name", "").strip()
    return render_template("index.html", unconfigured=unconfigured)


@app.route("/api/auth-status")
def api_auth_status():
    connected, _ = auth_status()
    needs_credentials = not state.CREDENTIALS_FILE.exists()
    return jsonify({"connected": connected, "needs_credentials": needs_credentials})


@app.route("/oauth/start")
def oauth_start():
    if not state.CREDENTIALS_FILE.exists():
        return (
            "credentials.json not found at ~/.config/patr/credentials.json",
            400,
        )
    flow = Flow.from_client_secrets_file(
        state.CREDENTIALS_FILE, scopes=state.SCOPES, redirect_uri=oauth_redirect_uri(app.config["PORT"])
    )
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    auth_url, oauth_state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    _oauth_state_store[oauth_state] = {
        "verifier": code_verifier,
        "origin": request.host_url.rstrip("/"),
    }
    return redirect(auth_url)


@app.route(OAUTH_CALLBACK)
def oauth_callback():
    oauth_state = request.args.get("state", "")
    flow = Flow.from_client_secrets_file(
        state.CREDENTIALS_FILE,
        scopes=state.SCOPES,
        redirect_uri=oauth_redirect_uri(app.config["PORT"]),
        state=oauth_state,
    )
    stored = _oauth_state_store.pop(oauth_state, {})
    flow.fetch_token(
        authorization_response=request.url,
        code_verifier=stored.get("verifier"),
    )
    state.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    state.TOKEN_FILE.write_text(flow.credentials.to_json())
    return redirect(stored.get("origin", "/"))


@app.route("/oauth/disconnect", methods=["POST"])
def oauth_disconnect():
    if state.TOKEN_FILE.exists():
        state.TOKEN_FILE.unlink()
    return jsonify({"ok": True})


@app.route("/api/editions")
def api_editions():
    return jsonify(get_editions())


@app.route("/preview/<slug>/email")
def preview_email(slug):
    _, post = load_edition(slug)
    if post is None:
        return "Not found", 404
    hugo_config = load_hugo_config()
    return build_email_html(
        slug, post, load_footer(), hugo_config, recipient_name="Friend"
    )


@app.route("/preview/<slug>/web")
def preview_web(slug):
    _, post = load_edition(slug)
    if post is None:
        return "Not found", 404
    ok, err = build_hugo(app.config["PORT"])
    if not ok:
        return f"<pre>Hugo build failed:\n{err}</pre>", 500
    return redirect(f"/newsletter/{slug}/")


@app.route("/api/toggle-draft/<slug>", methods=["POST"])
def toggle_draft(slug):
    f, post = load_edition(slug)
    if f is None or post is None:
        return jsonify({"error": "Not found"}), 404
    new_draft = not post.get("draft", False)
    text = f.read_text()
    new_value = "true" if new_draft else "false"
    # Only patch inside the first frontmatter block (between the two --- fences)
    fm_pattern = re.compile(r"^(---\n.*?^---\n)", re.DOTALL | re.MULTILINE)
    m = fm_pattern.match(text)
    if m:
        fm = m.group(1)
        if re.search(r"^draft:", fm, re.MULTILINE):
            new_fm = re.sub(
                r"^draft:.*$", f"draft: {new_value}", fm, flags=re.MULTILINE
            )
        else:
            # Insert draft before the closing ---
            new_fm = fm[:-4] + f"draft: {new_value}\n---\n"
        text = new_fm + text[m.end():]
    f.write_text(text)
    return jsonify({"draft": new_draft})


@app.route("/api/check-deployment/<slug>")
def check_deployment(slug):
    hugo_config = load_hugo_config()
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    if not base_url or "example.com" in base_url:
        return jsonify({"live": False, "reason": "baseURL not configured in hugo.toml"})
    url = f"{base_url}/newsletter/{slug}/"
    try:
        req = urllib.request.urlopen(url, timeout=5)
        live = req.status == 200
        return jsonify({"live": live, "url": url})
    except Exception as e:
        return jsonify({"live": False, "reason": str(e), "url": url})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    newsletter_config = load_newsletter_config()
    return jsonify(
        {
            "newsletter_name": newsletter_config.get("name", ""),
            "has_sheet_id": bool(newsletter_config.get("sheet_id")),
        }
    )


@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.json or {}
    hugo_updates = {}
    local_updates = {}
    if "newsletter_name" in data:
        hugo_updates["name"] = data["newsletter_name"]
    if "sheet_id" in data:
        local_updates["sheet_id"] = data["sheet_id"]
    if hugo_updates:
        save_hugo_patr_params(hugo_updates)
    if local_updates:
        state.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        local_file = state.CONFIG_DIR / "config.toml"
        existing = {}
        if local_file.exists():
            with open(local_file, "rb") as f:
                existing = tomllib.load(f)
        existing.update(local_updates)
        lines = [f'{k} = "{v}"' for k, v in existing.items()]
        local_file.write_text("\n".join(lines) + "\n")
    return jsonify({"ok": True})


@app.route("/api/contacts")
def contacts_list():
    newsletter_config = load_newsletter_config()
    sheet_id = newsletter_config.get("sheet_id")
    if not sheet_id:
        return jsonify({"error": "sheet_id not configured"}), 400
    try:
        creds = get_auth()
        contacts = fetch_contacts(sheet_id, creds)
        return jsonify({"contacts": contacts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/contacts/count")
def contacts_count():
    newsletter_config = load_newsletter_config()
    sheet_id = newsletter_config.get("sheet_id")
    if not sheet_id:
        return jsonify(
            {
                "count": None,
                "error": "sheet_id not set in ~/.config/patr/config.toml",
            }
        )
    try:
        creds = get_auth()
        contacts = fetch_contacts(sheet_id, creds)
        return jsonify({"count": len(contacts)})
    except Exception as e:
        return jsonify({"count": None, "error": str(e)})


@app.route("/api/sent-log")
def sent_log():
    newsletter_config = load_newsletter_config()
    sheet_id = newsletter_config.get("sheet_id")
    if not sheet_id:
        return jsonify({"error": "sheet_id not configured"}), 400
    try:
        creds = get_auth()
        service = build("sheets", "v4", credentials=creds)
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="Sent Log!A:C")
            .execute()
        )
        rows = result.get("values", [])
        return jsonify({"rows": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-send/<slug>", methods=["POST"])
def test_send(slug):
    _, post = load_edition(slug)
    if post is None:
        return jsonify({"error": "Not found"}), 404
    hugo_config = load_hugo_config()
    newsletter_config = load_newsletter_config()
    newsletter_name = newsletter_config.get("name", "Newsletter")
    data = request.json or {}
    recipients = data.get("recipients")  # list of {name, email} or None = just self
    try:
        creds = get_auth()
        gmail = build("gmail", "v1", credentials=creds)
        oauth2 = build("oauth2", "v2", credentials=creds)
        sender = oauth2.userinfo().get().execute()["email"]
        subject = f"[TEST] {post['title']} — {newsletter_name}"
        footer_md = load_footer()
        if not recipients:
            recipients = [{"name": "You", "email": sender}]
        else:
            for r in recipients:
                if r.get("email") == "__self__":
                    r["email"] = sender
        for r in recipients:
            html = build_email_html(
                slug, post, footer_md, hugo_config, recipient_name=r["name"]
            )
            send_email(gmail, sender, r["email"], subject, html)
        return jsonify({"ok": True, "sent": len(recipients)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/send/<slug>", methods=["POST"])
def send_all(slug):
    _, post = load_edition(slug)
    if post is None:
        return jsonify({"error": "Not found"}), 404
    hugo_config = load_hugo_config()
    newsletter_config = load_newsletter_config()
    sheet_id = newsletter_config.get("sheet_id")
    newsletter_name = newsletter_config.get("name", "Newsletter")
    if not sheet_id:
        return (
            jsonify({"error": "sheet_id not set in ~/.config/patr/config.toml"}),
            400,
        )
    try:
        creds = get_auth()
        gmail = build("gmail", "v1", credentials=creds)
        oauth2 = build("oauth2", "v2", credentials=creds)
        sender = oauth2.userinfo().get().execute()["email"]
        contacts = fetch_contacts(sheet_id, creds)
        if not contacts:
            return jsonify({"error": "No contacts found"}), 400
        already_sent = get_already_sent(sheet_id, creds, slug)
        pending = [
            c for c in contacts if c["email"].strip().lower() not in already_sent
        ]
        if not pending:
            return (
                jsonify({"error": "Already sent to all contacts for this edition"}),
                400,
            )
        subject = f"{post['title']} — {newsletter_name}"
        footer_md = load_footer()
        sent, failed = 0, []
        for contact in pending:
            try:
                html = build_email_html(
                    slug, post, footer_md, hugo_config, recipient_name=contact["name"]
                )
                send_email(gmail, sender, contact["email"], subject, html)
                log_sent(sheet_id, creds, contact["email"], slug)
                sent += 1
                time.sleep(0.9)
            except Exception as e:
                failed.append({"email": contact["email"], "error": str(e)})
        return jsonify(
            {
                "ok": True,
                "sent": sent,
                "failed": failed,
                "skipped": len(contacts) - len(pending),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/<path:filename>")
def serve_public(filename):
    public_dir = state.REPO_ROOT / "public"
    filepath = public_dir / filename
    if filepath.is_file():
        return send_from_directory(public_dir, filename)
    # Try index.html for directory paths
    index = public_dir / filename / "index.html"
    if index.is_file():
        return send_from_directory(public_dir / filename, "index.html")
    return "Not found", 404
