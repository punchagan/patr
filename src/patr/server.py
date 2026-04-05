import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
import tomllib
import urllib.request
from email.utils import formataddr
from importlib.metadata import metadata as pkg_metadata
from pathlib import Path

import markdown as md_lib
import yaml
from bs4 import BeautifulSoup
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    stream_with_context,
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
    hugo_mode,
    load_hugo_config,
    load_newsletter_config,
    save_hugo_patr_params,
)
from patr.contacts import fetch_contacts, get_already_sent, log_sent
from patr.content import build_email_html, get_editions, load_edition, load_footer
from patr.gmail import send_email
from playwright.sync_api import sync_playwright

app = Flask(__name__)


@app.route("/images/<path:filename>")
def static_images(filename):
    return send_from_directory(state.REPO_ROOT / "static" / "images", filename)


@app.route("/")
def index():
    cfg = load_newsletter_config()
    unconfigured = not cfg.get("name", "").strip()
    name = cfg.get("name", "").strip()
    title = f"{name} — Patr" if name else "Patr"
    return render_template("index.html", unconfigured=unconfigured, title=title)


@app.route("/api/auth-status")
def api_auth_status():
    connected, _ = auth_status()
    needs_credentials = not state.CREDENTIALS_FILE.exists()
    sender_email = (
        state.SENDER_EMAIL_FILE.read_text().strip()
        if state.SENDER_EMAIL_FILE.exists()
        else None
    )
    return jsonify(
        {
            "connected": connected,
            "needs_credentials": needs_credentials,
            "sender_email": sender_email,
        }
    )


@app.route("/oauth/start")
def oauth_start():
    if not state.CREDENTIALS_FILE.exists():
        return (
            "credentials.json not found at ~/.config/patr/credentials.json",
            400,
        )
    flow = Flow.from_client_secrets_file(
        state.CREDENTIALS_FILE,
        scopes=state.SCOPES,
        redirect_uri=oauth_redirect_uri(app.config["PORT"]),
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
    try:
        creds = flow.credentials
        oauth2 = build("oauth2", "v2", credentials=creds)
        email = oauth2.userinfo().get().execute().get("email", "")
        if email:
            state.SENDER_EMAIL_FILE.write_text(email)
    except Exception:
        pass
    return redirect(stored.get("origin", "/"))


@app.route("/oauth/disconnect", methods=["POST"])
def oauth_disconnect():
    if state.TOKEN_FILE.exists():
        state.TOKEN_FILE.unlink()
    if state.SENDER_EMAIL_FILE.exists():
        state.SENDER_EMAIL_FILE.unlink()
    return jsonify({"ok": True})


@app.route("/api/editions")
def api_editions():
    """Return all editions plus any warnings about the content directory."""
    editions = get_editions()
    warnings = []
    if state.CONTENT_DIR.exists():
        flat = [
            f.name
            for f in state.CONTENT_DIR.iterdir()
            if f.is_file() and f.suffix == ".md" and f.name != "_index.md"
        ]
        if flat:
            names = ", ".join(flat[:3]) + ("…" if len(flat) > 3 else "")
            warnings.append(
                f"Found flat .md files ({names}) — these won't appear as editions."
                " Run: patr migrate --repo ..."
            )
    return jsonify({"editions": editions, "warnings": warnings})


@app.route("/api/new-edition", methods=["POST"])
def new_edition():
    from datetime import date

    data = request.json or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    edition_dir = state.CONTENT_DIR / slug
    if edition_dir.exists():
        return jsonify({"error": f"Edition '{slug}' already exists"}), 400
    edition_dir.mkdir(parents=True)
    fm = yaml.dump(
        {"title": title, "date": date.today(), "draft": True},  # noqa: DTZ011
        Dumper=_PatrYamlDumper,
        sort_keys=False,
        allow_unicode=True,
    )
    (edition_dir / "index.md").write_text(f"---\n{fm}---\n\n")
    return jsonify({"slug": slug, "path": str((edition_dir / "index.md").resolve())})


@app.route("/newsletter/<slug>/<path:filename>")
def edition_resource(slug, filename):
    return send_from_directory(state.CONTENT_DIR / slug, filename)


@app.route("/api/edition/<slug>/content", methods=["GET"])
def get_edition_content(slug):
    f, post = load_edition(slug)
    if f is None or post is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(
        {
            "title": post.get("title", ""),
            "intro": post.get("intro", ""),
            "body": post.content,
            "mtime": f.stat().st_mtime,
        }
    )


class _PatrYamlDumper(yaml.SafeDumper):
    pass


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_PatrYamlDumper.add_representer(str, _str_representer)


@app.route("/api/edition/<slug>/content", methods=["POST"])
def save_edition_content(slug):
    """Save title, intro, and/or body for an edition.

    Accepts an optional ``mtime`` field; if the file has been modified since
    that timestamp a 409 is returned with the current body and mtime so the
    caller can handle the conflict. Content is written atomically via a temp
    file + os.replace() to avoid data loss if encoding fails mid-write.
    """
    f, post = load_edition(slug)
    if f is None or post is None:
        return jsonify({"error": "Not found"}), 404
    data = request.json or {}
    if "mtime" in data and data["mtime"] != f.stat().st_mtime:
        return jsonify({"body": post.content, "mtime": f.stat().st_mtime}), 409
    if "title" in data and data["title"].strip():
        post.metadata["title"] = data["title"].strip()
    if "intro" in data:
        intro = (data["intro"] or "").strip()
        if intro:
            post.metadata["intro"] = intro
        else:
            post.metadata.pop("intro", None)
    body = data.get("body", post.content)
    fm_yaml = yaml.dump(
        post.metadata, Dumper=_PatrYamlDumper, sort_keys=False, allow_unicode=True
    )
    content = f"---\n{fm_yaml}---\n\n{body.strip()}\n"
    # Write to a temp file in the same directory, then atomically replace.
    # This prevents data loss if the process dies or encoding fails mid-write.
    tmp_fd, tmp_path = tempfile.mkstemp(dir=f.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
        os.replace(tmp_path, f)
    except Exception:
        os.unlink(tmp_path)
        raise
    return jsonify({"ok": True, "mtime": f.stat().st_mtime})


ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


@app.route("/api/edition/<slug>/upload-image", methods=["POST"])
def upload_image(slug):
    f, post = load_edition(slug)
    if f is None or post is None:
        return jsonify({"error": "Not found"}), 404
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400
    filename = Path(file.filename).name  # strip any directory components
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({"error": f"File type .{ext} not allowed"}), 400
    dest_dir = state.CONTENT_DIR / slug
    dest = dest_dir / filename
    if dest.exists():
        stem = filename.rsplit(".", 1)[0]
        dest = dest_dir / f"{stem}-{secrets.token_hex(4)}.{ext}"
    file.save(dest)
    return jsonify({"path": dest.name})


@app.route("/api/edition/<slug>/check-images")
def check_images(slug):
    f, post = load_edition(slug)
    if f is None or post is None:
        return jsonify({"error": "Not found"}), 404
    edition_dir = state.CONTENT_DIR / slug
    app.config["PORT"]
    fake_hugo_config = {"baseURL": ""}
    html = build_email_html(
        slug,
        post,
        load_footer(),
        fake_hugo_config,
        absolute_urls=False,
        edition_dir=edition_dir,
    )
    soup = BeautifulSoup(html, "html.parser")
    missing = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith(("http://", "https://")):
            continue
        if src.startswith("/"):
            img_path = state.REPO_ROOT / "static" / src.lstrip("/")
        else:
            img_path = edition_dir / src
        if not img_path.exists():
            missing.append(src)

    return jsonify({"missing": missing})


@app.route("/preview/<slug>/email")
def preview_email(slug):
    _, post = load_edition(slug)
    if post is None:
        return "Not found", 404
    port = app.config["PORT"]
    return build_email_html(
        slug, post, load_footer(), {"baseURL": f"http://127.0.0.1:{port}"}
    )


@app.route("/preview/<slug>/email.pdf")
def preview_email_pdf(slug):
    _, post = load_edition(slug)
    if post is None:
        return "Not found", 404
    port = app.config["PORT"]
    url = f"http://127.0.0.1:{port}/preview/{slug}/email"
    with sync_playwright() as p:
        for channel in ("chromium", "chrome", "msedge"):
            try:
                browser = p.chromium.launch(channel=channel)
                break
            except Exception:  # noqa: S112
                continue
        else:
            return "No usable browser found. Install Chromium or Chrome.", 501
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        height = page.evaluate(
            "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )
        pdf_bytes = page.pdf(
            width="670px", height=f"{height + 100}px", print_background=True
        )
        browser.close()
    return (
        pdf_bytes,
        200,
        {
            "Content-Type": "application/pdf",
            "Content-Disposition": f'attachment; filename="{slug}.pdf"',
        },
    )


@app.route("/preview/<slug>/web")
def preview_web(slug):
    """Render Hugo web preview. Returns 501 in hugo-free mode."""
    if not hugo_mode():
        return "Web preview is not available in hugo-free mode.", 501
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
    post.metadata["draft"] = new_draft
    fm_yaml = yaml.dump(
        post.metadata, Dumper=_PatrYamlDumper, sort_keys=False, allow_unicode=True
    )
    f.write_text(f"---\n{fm_yaml}---\n\n{post.content.strip()}\n")
    return jsonify({"draft": new_draft})


@app.route("/api/publish/<slug>", methods=["POST"])
def publish_edition(slug):
    f, post = load_edition(slug)
    if f is None or post is None:
        return jsonify({"error": "Not found"}), 404
    if post.get("draft", True):
        return jsonify({"error": "Edition is still a draft"}), 400

    edition_dir = state.CONTENT_DIR / slug
    for cmd in [
        ["git", "add", str(edition_dir)],
        ["git", "commit", "-m", f"Publish: {post['title']}"],
        ["git", "push"],
    ]:
        result = subprocess.run(
            cmd, cwd=state.REPO_ROOT, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            # "nothing to commit" is not an error
            if "nothing to commit" in result.stdout + result.stderr:
                continue
            return jsonify({"error": result.stderr or result.stdout}), 500
    return jsonify({"ok": True})


COMMIT_DIFF_THRESHOLD = 500  # bytes; below this amends the last wip commit


@app.route("/api/edition/<slug>/commit", methods=["POST"])
def commit_edition(slug):
    f, post = load_edition(slug)
    if f is None or post is None:
        return jsonify({"error": "Not found"}), 404

    edition_dir = state.CONTENT_DIR / slug
    title = post.metadata.get("title", slug)

    diff = subprocess.run(
        ["git", "diff", "HEAD", "--", str(f)],
        cwd=state.REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    diff_size = len(diff.stdout)

    subprocess.run(
        ["git", "add", str(edition_dir)],
        cwd=state.REPO_ROOT,
        capture_output=True,
        check=False,
    )

    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=state.REPO_ROOT, check=False
    )
    if staged.returncode == 0:
        return jsonify({"ok": True, "committed": False})

    last_msg = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=state.REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    if diff_size < COMMIT_DIFF_THRESHOLD and last_msg.startswith("wip:"):
        result = subprocess.run(
            ["git", "commit", "--amend", "--no-edit"],
            cwd=state.REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        result = subprocess.run(
            ["git", "commit", "-m", f"wip: {title}"],
            cwd=state.REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        return jsonify({"error": f"git commit failed: {result.stderr.strip()}"}), 500

    return jsonify({"ok": True, "committed": True})


@app.route("/api/check-deployment/<slug>")
def check_deployment(slug):
    f, post = load_edition(slug)
    if f is None or post is None:
        return jsonify({"error": "Not found"}), 404

    newsletter_config = load_newsletter_config()
    if newsletter_config.get("email_only"):
        return jsonify(
            {"email_only": True, "live": None, "uncommitted": None, "unpushed": None}
        )

    hugo_config = load_hugo_config()
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    if not base_url or "example.com" in base_url:
        return jsonify(
            {
                "live": False,
                "uncommitted": None,
                "unpushed": None,
                "reason": "baseURL not configured in hugo.toml",
            }
        )

    edition_dir = state.CONTENT_DIR / slug

    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-b", "--", str(edition_dir)],
        cwd=state.REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = status.stdout.split("\n") if status.stdout else []
    branch_line = lines[0] if lines else ""
    unpushed = "[ahead" in branch_line
    uncommitted = any(line.strip() for line in lines[1:])

    url = f"{base_url}/newsletter/{slug}/"
    try:
        req = urllib.request.urlopen(url, timeout=5)
        live = req.status == 200
    except Exception as e:
        return jsonify(
            {
                "live": False,
                "uncommitted": uncommitted,
                "unpushed": unpushed,
                "url": url,
                "reason": str(e),
            }
        )
    return jsonify(
        {"live": live, "uncommitted": uncommitted, "unpushed": unpushed, "url": url}
    )


@app.route("/api/help")
def get_help():
    readme = state.PATR_ROOT.parent.parent / "README.md"
    if readme.exists():
        text = readme.read_text()
    else:
        text = pkg_metadata("patr").get_payload() or ""
    start = text.find("<!-- help-start -->")
    end = text.find("<!-- help-end -->")
    if start != -1 and end != -1:
        text = text[start + len("<!-- help-start -->") : end].strip()
    html = md_lib.markdown(text, extensions=["extra", "tables"])
    return jsonify({"html": html})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    newsletter_config = load_newsletter_config()
    return jsonify(
        {
            "newsletter_name": newsletter_config.get("name", ""),
            "has_sheet_id": bool(newsletter_config.get("sheet_id")),
            "email_only": bool(newsletter_config.get("email_only", False)),
        }
    )


@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.json or {}
    hugo_updates = {}
    local_updates = {}
    if "newsletter_name" in data:
        hugo_updates["name"] = data["newsletter_name"]
    if "email_only" in data:
        hugo_updates["email_only"] = bool(data["email_only"])
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
    email_only = bool(newsletter_config.get("email_only", False))
    edition_dir = state.CONTENT_DIR / slug
    data = request.json or {}
    recipients = data.get("recipients")  # list of {name, email} or None = just self
    try:
        creds = get_auth()
        gmail = build("gmail", "v1", credentials=creds)
        oauth2 = build("oauth2", "v2", credentials=creds)
        userinfo = oauth2.userinfo().get().execute()
        sender = formataddr((userinfo.get("name", ""), userinfo["email"]))
        subject = f"[TEST] {post['title']} — {newsletter_name}"
        footer_md = load_footer()
        if not recipients:
            recipients = [{"name": "You", "email": userinfo["email"]}]
        else:
            for r in recipients:
                if r.get("email") == "__self__":
                    r["email"] = userinfo["email"]
        for r in recipients:
            html = build_email_html(
                slug,
                post,
                footer_md,
                hugo_config,
                recipient_name=r["name"],
                email_only=email_only,
                edition_dir=edition_dir,
            )
            send_email(
                gmail, sender, formataddr((r["name"], r["email"])), subject, html
            )
            sheet_id = newsletter_config.get("sheet_id")
            if sheet_id is not None:
                log_sent(sheet_id, creds, r["email"], f"test-{slug}")

        return jsonify({"ok": True, "sent": len(recipients)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/send/<slug>", methods=["POST"])
def send_all(slug):
    """Send edition to all contacts, streaming progress as Server-Sent Events.

    Pre-flight validation (draft check, baseURL, sheet_id, auth, contacts)
    returns JSON errors with appropriate status codes. Once validation passes,
    the response switches to text/event-stream and yields one SSE event per
    contact: {"type": "progress", "sent": N, "total": N, "name": "..."} for
    successes, {"type": "error", "email": "...", "error": "..."} for failures,
    and a final {"type": "done", "sent": N, "failed": [...], "skipped": N}.
    """
    _, post = load_edition(slug)
    if post is None:
        return jsonify({"error": "Not found"}), 404
    if post.get("draft", True):
        return jsonify({"error": "Cannot send a draft edition"}), 400
    hugo_config = load_hugo_config()
    newsletter_config = load_newsletter_config()
    email_only = bool(newsletter_config.get("email_only", False))
    if not email_only:
        base_url = hugo_config.get("baseURL", "").rstrip("/")
        if not base_url or "example.com" in base_url:
            return jsonify({"error": "baseURL not configured in hugo.toml"}), 400
    sheet_id = newsletter_config.get("sheet_id")
    newsletter_name = newsletter_config.get("name", "Newsletter")
    if not sheet_id:
        return (
            jsonify(
                {"error": "No contacts sheet configured — add a sheet ID in ⚙ Settings"}
            ),
            400,
        )
    try:
        creds = get_auth()
        gmail = build("gmail", "v1", credentials=creds)
        oauth2 = build("oauth2", "v2", credentials=creds)
        userinfo = oauth2.userinfo().get().execute()
        sender = formataddr((userinfo.get("name", ""), userinfo["email"]))
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    subject = f"{post['title']} — {newsletter_name}"
    footer_md = load_footer()
    edition_dir = state.CONTENT_DIR / slug
    total = len(pending)
    skipped = len(contacts) - total

    def generate():
        sent, failed = 0, []
        for contact in pending:
            try:
                html = build_email_html(
                    slug,
                    post,
                    footer_md,
                    hugo_config,
                    recipient_name=contact["name"],
                    email_only=email_only,
                    edition_dir=edition_dir,
                )
                send_email(
                    gmail,
                    sender,
                    formataddr((contact["name"], contact["email"])),
                    subject,
                    html,
                )
                # log_sent is called immediately after send_email. If it fails,
                # the email was sent but not recorded — re-running would send again.
                log_sent(sheet_id, creds, contact["email"], slug)
                sent += 1
                yield f"data: {json.dumps({'type': 'progress', 'sent': sent, 'total': total, 'name': contact['name']})}\n\n"
                time.sleep(0.9)
            except Exception as e:
                failed.append({"email": contact["email"], "error": str(e)})
                yield f"data: {json.dumps({'type': 'error', 'email': contact['email'], 'error': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'sent': sent, 'failed': failed, 'skipped': skipped})}\n\n"

    return Response(stream_with_context(generate()), content_type="text/event-stream")


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
