#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "flask>=3.0",
#   "python-frontmatter>=1.1",
#   "markdown>=3.6",
#   "google-auth-oauthlib>=1.2",
#   "google-api-python-client>=2.120",
#   "premailer>=3.10",
# ]
# ///

import base64
import hashlib
import os
import re
import secrets
import subprocess
import threading
import time
import tomllib
import urllib.request
import webbrowser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import frontmatter
import markdown
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_from_directory,
)
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from premailer import transform

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

app = Flask(__name__)


PATR_ROOT = Path(__file__).parent  # patr's own repo (layouts, assets, etc.)
REPO_ROOT = Path.cwd()               # target Hugo site root — overridden by --repo arg
CONTENT_DIR = REPO_ROOT / "content" / "newsletter"
CONFIG_DIR = Path.home() / ".config" / "patr"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/spreadsheets",
]


# --- Config ---


def load_hugo_config():
    with open(REPO_ROOT / "hugo.toml", "rb") as f:
        return tomllib.load(f)


def load_newsletter_config():
    hugo = load_hugo_config()
    config = dict(hugo.get("params", {}).get("patr", {}))
    local_file = CONFIG_DIR / "config.toml"
    if local_file.exists():
        with open(local_file, "rb") as f:
            config.update(tomllib.load(f))
    return config


def save_hugo_patr_params(updates: dict):
    """Surgically write [params.patr] keys into hugo.toml."""
    hugo_toml = REPO_ROOT / "hugo.toml"
    text = hugo_toml.read_text()

    for key, value in updates.items():
        quoted = f'"{value}"'
        # Update existing key inside [params.patr] block
        pattern = (
            r"(\[params\.newsletter\][^\[]*?)(" + re.escape(key) + r'\s*=\s*"[^"]*")'
        )
        if re.search(pattern, text, re.DOTALL):
            text = re.sub(
                pattern,
                lambda m: m.group(1) + f"{key} = {quoted}",
                text,
                flags=re.DOTALL,
            )
        else:
            # Key doesn't exist — append to section or create section
            if "[params.patr]" in text:
                text = re.sub(
                    r"(\[params\.newsletter\])", f"\\1\n  {key} = {quoted}", text
                )
            else:
                text += f"\n[params.patr]\n  {key} = {quoted}\n"

    hugo_toml.write_text(text)


# --- Auth ---

OAUTH_CALLBACK = "/oauth/callback"


_oauth_state_store: dict[str, dict] = {}  # state -> {verifier, origin}


def oauth_redirect_uri():
    return f"http://127.0.0.1:{app.config.get('PORT', 5000)}{OAUTH_CALLBACK}"


def get_auth():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            TOKEN_FILE.write_text(creds.to_json())
        else:
            raise RuntimeError("not_authenticated")
    return creds


def auth_status():
    """Returns (connected: bool, email: str|None)"""
    if not TOKEN_FILE.exists():
        return False, None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            TOKEN_FILE.write_text(creds.to_json())
        if creds.valid:
            # Extract email from token file
            import json

            data = json.loads(TOKEN_FILE.read_text())
            return True, data.get("client_id", "").split("-")[0] or None
    except Exception:
        pass
    return False, None


# --- Hugo build ---


def find_hugo():
    import shutil
    local = REPO_ROOT / "hugo.sh"
    if local.exists():
        return str(local)
    for candidate in ("hugo", "hugo.sh"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("Hugo not found. Install hugo or provide a hugo.sh in the repo root.")


def build_hugo():
    result = subprocess.run(
        [find_hugo(), "-D", f"--baseURL=http://127.0.0.1:{app.config['PORT']}/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0, result.stderr


# --- Content helpers ---


def get_editions():
    posts = []
    for f in sorted(CONTENT_DIR.glob("*.md")):
        if f.name in ("_index.md", "footer.md"):
            continue
        try:
            post = frontmatter.load(f)
        except Exception as e:
            posts.append(
                {
                    "slug": f.stem,
                    "title": f"⚠ {f.stem} (frontmatter error)",
                    "date": "",
                    "draft": True,
                    "path": str(f.resolve()),
                    "error": str(e),
                }
            )
            continue
        posts.append(
            {
                "slug": f.stem,
                "title": post.get("title", f.stem),
                "date": str(post.get("date", ""))[:10],
                "draft": post.get("draft", False),
                "path": str(f.resolve()),
            }
        )
    posts.sort(key=lambda x: x["date"], reverse=True)
    return posts


def load_edition(slug):
    f = CONTENT_DIR / f"{slug}.md"
    if not f.exists():
        return None, None
    try:
        return f, frontmatter.load(f)
    except Exception as e:
        raise ValueError(f"Frontmatter parse error in {f.name}: {e}") from e


def load_footer():
    footer_file = CONTENT_DIR / "footer.md"
    if not footer_file.exists():
        return ""
    return frontmatter.load(footer_file).content


def render_md(text):
    html = markdown.markdown(text or "", extensions=["extra", "smarty"])

    # Mirror Hugo's render hook: wrap <img> with <figure>/<figcaption>
    def img_to_figure(m):
        tag = m.group(0)
        alt = re.search(r'alt="([^"]+)"', tag)
        if not alt:
            return tag
        return f"<figure>{tag}<figcaption>{alt.group(1)}</figcaption></figure>"

    return re.sub(r"<img[^>]+>", img_to_figure, html)


# --- HTML builders ---


def build_web_html(post, footer_md):
    date = str(post.get("date", ""))[:10]
    intro_html = render_md(post.get("intro", ""))
    body_html = render_md(post.content)
    footer_html = render_md(footer_md)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{post["title"]}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 640px; margin: 2rem auto; padding: 0 1.5rem; color: #333; line-height: 1.7; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.25rem; }}
  .date {{ color: #999; font-size: 0.85em; margin-bottom: 1.5rem; }}
  .intro {{ font-style: italic; color: #555; border-bottom: 1px solid #ddd; padding-bottom: 1rem; margin-bottom: 1.5rem; font-size: 1.05em; }}
  .footer {{ border-top: 1px solid #ddd; margin-top: 2rem; padding-top: 1rem; font-size: 0.9em; color: #666; }}
  img {{ max-width: 500px; height: auto; display: block; margin: 1rem auto; }}
  figure {{ margin: 1.5rem 0; text-align: center; }}
  figcaption {{ font-size: 0.85em; color: #888; margin-top: 0.5rem; }}
</style>
</head>
<body>
  <p class="date">{date}</p>
  <h1>{post["title"]}</h1>
  {"<div class='intro'>" + intro_html + "</div>" if intro_html else ""}
  <div class="content">{body_html}</div>
  {"<div class='footer'>" + footer_html + "</div>" if footer_html else ""}
</body>
</html>"""


def build_email_html(slug, post, footer_md, hugo_config, recipient_name=None):
    base_url = hugo_config.get("baseURL", "").rstrip("/")
    web_url = f"{base_url}/newsletter/{slug}/"
    greeting = f"Hi {recipient_name}," if recipient_name else "Hi,"
    intro_html = render_md(post.get("intro", ""))
    body_html = render_md(post.content)
    footer_html = render_md(footer_md)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>img {{ max-width: 500px; height: auto; display: block; margin: 1rem auto; }}</style></head>
<body style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333; background: #fff; line-height: 1.7;">
  <p style="font-size: 0.8em; color: #aaa; margin-bottom: 2em;">
    <a href="{web_url}" style="color: #aaa;">View in browser</a>
  </p>
  <p>{greeting}</p>
  {"<div style='font-style:italic;color:#555;border-bottom:1px solid #eee;padding-bottom:1em;margin-bottom:1.5em;font-size:1.05em;'>" + intro_html + "</div>" if intro_html else ""}
  <div>{body_html}</div>
  {"<div style='border-top:1px solid #eee;margin-top:2em;padding-top:1em;font-size:0.9em;color:#666;'>" + footer_html + "</div>" if footer_html else ""}
</body>
</html>"""
    return transform(html)


# --- Gmail helper ---


def send_email(gmail, sender, to_email, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()


# --- Contacts helper ---


def fetch_contacts(sheet_id, creds):
    service = build("sheets", "v4", credentials=creds)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="A:D")
        .execute()
    )
    rows = result.get("values", [])
    if len(rows) < 2:
        return []
    header = [h.strip().lower() for h in rows[0]]
    contacts = []
    for row in rows[1:]:
        d = dict(zip(header, row + [""] * 4))
        if (
            d.get("send", "").strip().lower() not in ("n", "no")
            and d.get("email", "").strip()
        ):
            contacts.append(
                {
                    "name": d.get("name", "").strip(),
                    "email": d["email"].strip(),
                }
            )
    return contacts


def get_already_sent(sheet_id, creds, slug):
    """Return set of emails already sent for this slug from the Sent Log tab."""
    service = build("sheets", "v4", credentials=creds)
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="Sent Log!A:C")
            .execute()
        )
    except Exception:
        return set()
    rows = result.get("values", [])
    if len(rows) < 2:
        return set()
    return {
        row[0].strip().lower()
        for row in rows[1:]
        if len(row) >= 2 and row[1].strip() == slug
    }


def log_sent(sheet_id, creds, email, slug):
    """Append a row to the Sent Log tab."""
    service = build("sheets", "v4", credentials=creds)
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Ensure the sheet tab exists
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    tab_names = [s["properties"]["title"] for s in meta["sheets"]]
    if "Sent Log" not in tab_names:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": "Sent Log"}}}]},
        ).execute()
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Sent Log!A1",
            valueInputOption="RAW",
            body={"values": [["email", "slug", "sent_at"]]},
        ).execute()
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sent Log!A:C",
        valueInputOption="RAW",
        body={"values": [[email, slug, timestamp]]},
    ).execute()


# --- Flask routes ---


@app.route("/images/<path:filename>")
def static_images(filename):
    return app.send_static_file(f"images/{filename}")


@app.route("/")
def index():
    return render_template_string(MAIN_HTML)


@app.route("/api/auth-status")
def api_auth_status():
    connected, _ = auth_status()
    needs_credentials = not CREDENTIALS_FILE.exists()
    return jsonify({"connected": connected, "needs_credentials": needs_credentials})


@app.route("/oauth/start")
def oauth_start():
    if not CREDENTIALS_FILE.exists():
        return (
            "credentials.json not found at ~/.config/patr/credentials.json",
            400,
        )
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=oauth_redirect_uri()
    )
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    _oauth_state_store[state] = {
        "verifier": code_verifier,
        "origin": request.host_url.rstrip("/"),
    }
    return redirect(auth_url)


@app.route(OAUTH_CALLBACK)
def oauth_callback():
    state = request.args.get("state", "")
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=oauth_redirect_uri(),
        state=state,
    )
    stored = _oauth_state_store.pop(state, {})
    flow.fetch_token(
        authorization_response=request.url,
        code_verifier=stored.get("verifier"),
    )
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(flow.credentials.to_json())
    return redirect(stored.get("origin", "/"))


@app.route("/oauth/disconnect", methods=["POST"])
def oauth_disconnect():
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
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
    ok, err = build_hugo()
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
        text = new_fm + text[m.end() :]
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
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        local_file = CONFIG_DIR / "config.toml"
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
    public_dir = REPO_ROOT / "public"
    filepath = public_dir / filename
    if filepath.is_file():
        return send_from_directory(public_dir, filename)
    # Try index.html for directory paths
    index = public_dir / filename / "index.html"
    if index.is_file():
        return send_from_directory(public_dir / filename, "index.html")
    return "Not found", 404


# --- Main HTML template ---

MAIN_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Newsletter</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #f5f5f5;
    --surface: #fff;
    --border: #e0e0e0;
    --border-subtle: #f0f0f0;
    --text: #222;
    --text-secondary: #555;
    --text-muted: #999;
    --text-placeholder: #aaa;
    --toolbar-bg: #fafafa;
    --btn-bg: #fff;
    --btn-hover: #f0f0f0;
    --active-bg: #f0f4ff;
    --active-accent: #4a6fa5;
    --modal-overlay: rgba(0,0,0,0.4);
  }

  body.dark {
    --bg: #1a1a1a;
    --surface: #242424;
    --border: #383838;
    --border-subtle: #2e2e2e;
    --text: #e8e8e8;
    --text-secondary: #aaa;
    --text-muted: #666;
    --text-placeholder: #555;
    --toolbar-bg: #1e1e1e;
    --btn-bg: #2e2e2e;
    --btn-hover: #383838;
    --active-bg: #1e2a3a;
    --active-accent: #6b93c9;
    --modal-overlay: rgba(0,0,0,0.6);
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* Layout */
  .layout {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* Sidebar */
  .sidebar {
    width: 260px;
    min-width: 260px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .auth-bar {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }
  .auth-dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  }
  .auth-dot.ok  { background: #4caf80; }
  .auth-dot.err { background: #f08080; }
  .auth-label { flex: 1; color: var(--text-secondary); }

  .sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border);
    font-weight: 600;
    font-size: 13px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .edition-list {
    overflow-y: auto;
    flex: 1;
  }

  .edition-item {
    padding: 12px 16px;
    cursor: pointer;
    border-bottom: 1px solid #f0f0f0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .edition-item:hover { background: var(--btn-hover); }
  .edition-item.active { background: var(--active-bg); border-left: 3px solid var(--active-accent); }

  .edition-title {
    font-weight: 500;
    font-size: 13px;
    line-height: 1.3;
  }

  .edition-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text-muted);
  }

  .badge {
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .badge-draft { background: #fff3cd; color: #856404; }
  .badge-live  { background: #d1e7dd; color: #0a5c36; }
  body.dark .badge-draft { background: #3a2e00; color: #f0c040; }
  body.dark .badge-live  { background: #0a2e1a; color: #4caf80; }

  /* Main panel */
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--surface);
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--toolbar-bg);
    flex-shrink: 0;
  }

  .toolbar-title {
    font-weight: 500;
    font-size: 14px;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text);
  }

  .toolbar-title.empty { color: var(--text-placeholder); font-weight: 400; }

  .btn {
    padding: 5px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--btn-bg);
    color: var(--text);
    cursor: pointer;
    font-size: 13px;
    white-space: nowrap;
  }

  .btn:hover:not(:disabled) { background: var(--btn-hover); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .btn-toggle.active {
    background: var(--active-accent);
    border-color: var(--active-accent);
    color: #fff;
  }

  .btn-draft-toggle { font-size: 12px; }
  .btn-danger { border-color: #c53030; color: #c53030; }
  .btn-danger:hover:not(:disabled) { background: #fff5f5; }
  body.dark .btn-danger:hover:not(:disabled) { background: #2a0a0a; }
  .btn-primary { background: var(--active-accent); border-color: var(--active-accent); color: #fff; }
  .btn-primary:hover:not(:disabled) { background: #3d5f8f; }

  .preview-frame {
    flex: 1;
    border: none;
    background: #fff;
  }

  .empty-state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-placeholder);
    font-size: 15px;
  }

  /* Action bar */
  .action-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    border-top: 1px solid var(--border);
    background: var(--toolbar-bg);
    flex-shrink: 0;
  }

  .action-bar .spacer { flex: 1; }

  .status-msg {
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 4px;
  }

  .status-msg.ok   { background: #d1e7dd; color: #0a5c36; }
  .status-msg.warn { background: #fff3cd; color: #856404; }
  .status-msg.err  { background: #f8d7da; color: #842029; }
  .status-msg.info { background: #e8f0fe; color: #1a3a6b; }
  body.dark .status-msg.ok   { background: #0a2e1a; color: #4caf80; }
  body.dark .status-msg.warn { background: #3a2e00; color: #f0c040; }
  body.dark .status-msg.err  { background: #2a0a0a; color: #f08080; }
  body.dark .status-msg.info { background: #0a1a3a; color: #80aaee; }

  /* Modal */
  .modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: 100;
    align-items: center;
    justify-content: center;
  }

  .modal-overlay.visible { display: flex; }

  .modal {
    background: var(--surface);
    border-radius: 8px;
    padding: 28px;
    max-width: 380px;
    width: 90%;
    box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  }

  .modal h3 { font-size: 16px; margin-bottom: 10px; }
  .modal p  { color: var(--text-secondary); font-size: 13px; margin-bottom: 20px; line-height: 1.5; }

  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; }

  .btn-theme { font-size: 15px; padding: 4px 8px; border-radius: 4px; line-height: 1; }
</style>
</head>
<body>

<div class="layout">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="auth-bar" id="auth-bar">
      <span class="auth-dot" id="auth-dot"></span>
      <span class="auth-label" id="auth-label">Checking…</span>
      <a class="btn" id="auth-btn" href="/oauth/start" style="font-size:11px;padding:3px 8px;display:none">Connect</a>
      <button class="btn" id="auth-disconnect" onclick="disconnect()" style="font-size:11px;padding:3px 8px;display:none">Disconnect</button>
    </div>
    <div class="sidebar-header">Editions <button class="btn" onclick="openSettings()" style="font-size:11px;padding:2px 7px;float:right">⚙</button></div>
    <div class="edition-list" id="edition-list">
      <div style="padding:16px; color:var(--text-placeholder); font-size:13px;">Loading…</div>
    </div>
  </aside>

  <!-- Main panel -->
  <main class="main" id="main">
    <div class="toolbar">
      <span class="toolbar-title empty" id="toolbar-title">Select an edition</span>
      <button class="btn btn-toggle active" id="btn-email" onclick="setView('email')" style="display:none">Email</button>
      <button class="btn btn-toggle" id="btn-web" onclick="setView('web')" style="display:none">Web</button>
      <button class="btn btn-draft-toggle" id="btn-draft" onclick="toggleDraft()" style="display:none"></button>
      <button class="btn btn-theme" id="btn-theme" onclick="toggleTheme()" title="Toggle dark mode">🌙</button>
    </div>

    <div class="empty-state" id="empty-state">← Select an edition to preview</div>
    <iframe class="preview-frame" id="preview-frame" style="display:none"></iframe>

    <div class="action-bar" id="action-bar" style="display:none">
      <a class="btn" id="btn-obsidian" href="#" target="_blank">Edit in Obsidian</a>
      <div class="spacer"></div>
      <span class="status-msg" id="deploy-status" style="display:none"></span>
      <button class="btn" id="btn-test" onclick="testSend()" disabled>Test Send</button>
      <button class="btn btn-danger" id="btn-send" onclick="confirmSend()" disabled>Send All</button>
    </div>
  </main>
</div>

<!-- Settings modal -->
<div class="modal-overlay" id="settings-modal">
  <div class="modal">
    <h3>Settings</h3>
    <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:20px">
      <label style="font-size:13px">
        Newsletter name
        <input id="settings-name" type="text" style="display:block;width:100%;margin-top:4px;padding:6px 8px;font-size:13px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);box-sizing:border-box">
      </label>
      <label style="font-size:13px">
        Contacts sheet ID <span style="color:var(--text-placeholder);font-size:11px">(stored locally, never in repo)</span>
        <div style="display:flex;gap:6px;margin-top:4px">
          <input id="settings-sheet" type="text" style="flex:1;padding:6px 8px;font-size:13px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);box-sizing:border-box">
          <button class="btn" onclick="testContacts()" style="font-size:12px;white-space:nowrap">Test</button>
        </div>
        <span id="contacts-test-result" style="font-size:12px;color:var(--text-secondary);margin-top:4px;display:block"></span>
      </label>
      <div>
        <button class="btn" onclick="checkSentLog()" style="font-size:12px">Check Sent Log</button>
        <pre id="sent-log-result" style="display:none;margin-top:8px;font-size:11px;max-height:160px;overflow-y:auto;background:var(--bg-secondary);padding:8px;border-radius:4px;white-space:pre-wrap"></pre>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn" onclick="closeSettings()">Cancel</button>
      <button class="btn btn-primary" onclick="saveSettings()">Save</button>
    </div>
  </div>
</div>

<!-- Test send modal -->
<div class="modal-overlay" id="test-modal">
  <div class="modal">
    <h3>Test Send</h3>
    <p style="margin-bottom:10px;font-size:13px;color:var(--text-secondary)">Select recipients: <span id="test-selection-count" style="font-weight:600;color:var(--text-primary)"></span></p>
    <div id="test-contact-list" style="max-height:260px;overflow-y:auto;display:flex;flex-direction:column;gap:6px;margin-bottom:16px;font-size:13px"></div>
    <div class="modal-actions">
      <button class="btn" onclick="closeTestModal()">Cancel</button>
      <button class="btn btn-primary" onclick="doTestSend()">Send</button>
    </div>
  </div>
</div>

<!-- Confirm modal -->
<div class="modal-overlay" id="modal">
  <div class="modal">
    <h3>Send to everyone?</h3>
    <p id="modal-body">This will send the email to all recipients. This cannot be undone.</p>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="doSend()">Send</button>
    </div>
  </div>
</div>

<script>
let currentSlug = null;
let currentDraft = false;
let viewMode = 'email';
let contactCount = null;
let deploymentLive = false;

// Auth status
function refreshAuthStatus() {
  fetch('/api/auth-status').then(r => r.json()).then(d => {
    const dot = document.getElementById('auth-dot');
    const label = document.getElementById('auth-label');
    const connectBtn = document.getElementById('auth-btn');
    const disconnectBtn = document.getElementById('auth-disconnect');
    if (d.needs_credentials) {
      dot.className = 'auth-dot err';
      label.textContent = 'No credentials.json';
      connectBtn.style.display = 'none';
      disconnectBtn.style.display = 'none';
    } else if (d.connected) {
      dot.className = 'auth-dot ok';
      label.textContent = 'Gmail connected';
      connectBtn.style.display = 'none';
      disconnectBtn.style.display = '';
    } else {
      dot.className = 'auth-dot err';
      label.textContent = 'Not connected';
      connectBtn.style.display = '';
      disconnectBtn.style.display = 'none';
    }
  });
}

function disconnect() {
  fetch('/oauth/disconnect', { method: 'POST' }).then(() => refreshAuthStatus());
}

refreshAuthStatus();

// Dark mode
function applyTheme(dark) {
  document.body.classList.toggle('dark', dark);
  document.getElementById('btn-theme').textContent = dark ? '☀️' : '🌙';
}
function toggleTheme() {
  const dark = !document.body.classList.contains('dark');
  localStorage.setItem('theme', dark ? 'dark' : 'light');
  applyTheme(dark);
}
applyTheme(localStorage.getItem('theme') === 'dark');

// Load editions on startup
fetch('/api/editions')
  .then(r => r.json())
  .then(editions => {
    const list = document.getElementById('edition-list');
    if (!editions.length) {
      list.innerHTML = '<div style="padding:16px;color:#aaa;font-size:13px;">No editions found.</div>';
      return;
    }
    list.innerHTML = editions.map(e => `
      <div class="edition-item" id="item-${e.slug}" onclick="selectEdition(${JSON.stringify(e).replace(/"/g, '&quot;')})">
        <div class="edition-title">${e.title}</div>
        <div class="edition-meta">
          <span>${e.date}</span>
          <span class="badge ${e.draft ? 'badge-draft' : 'badge-live'}" id="badge-${e.slug}">
            ${e.draft ? 'Draft' : 'Live'}
          </span>
        </div>
      </div>
    `).join('');
    // Pre-fetch contact count once
    fetch('/api/contacts/count')
      .then(r => r.json())
      .then(d => { contactCount = d.count; });

    // Restore state from URL hash
    const [hashSlug, hashView] = location.hash.slice(1).split('/');
    if (hashSlug) {
      const match = editions.find(e => e.slug === hashSlug);
      if (match) selectEdition(match, hashView || 'email');
    }
  });

function updateHash() {
  const hash = viewMode === 'email' ? currentSlug : `${currentSlug}/web`;
  history.replaceState(null, '', `#${hash}`);
}

function selectEdition(e, view = 'email') {
  // Deselect previous
  if (currentSlug) {
    document.getElementById(`item-${currentSlug}`)?.classList.remove('active');
  }
  currentSlug = e.slug;
  currentDraft = e.draft;
  viewMode = view;

  document.getElementById(`item-${e.slug}`).classList.add('active');
  document.getElementById('toolbar-title').textContent = e.title;
  document.getElementById('toolbar-title').classList.remove('empty');

  // Show controls
  ['btn-email','btn-web','btn-draft'].forEach(id => {
    document.getElementById(id).style.display = '';
  });
  document.getElementById('btn-email').classList.toggle('active', view === 'email');
  document.getElementById('btn-web').classList.toggle('active', view === 'web');
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('preview-frame').style.display = '';
  document.getElementById('action-bar').style.display = '';

  // Draft toggle button label
  updateDraftButton();

  // Obsidian link
  document.getElementById('btn-obsidian').href = `obsidian://open?path=${encodeURIComponent(e.path)}`;

  updateHash();
  loadPreview();
  checkDeployment();
}

function setView(mode) {
  viewMode = mode;
  document.getElementById('btn-email').classList.toggle('active', mode === 'email');
  document.getElementById('btn-web').classList.toggle('active', mode === 'web');
  updateHash();
  loadPreview();
}

function loadPreview() {
  const frame = document.getElementById('preview-frame');
  frame.src = `/preview/${currentSlug}/${viewMode}`;
}

function updateDraftButton() {
  const btn = document.getElementById('btn-draft');
  btn.textContent = currentDraft ? 'Mark as Live' : 'Mark as Draft';
}

function toggleDraft() {
  fetch(`/api/toggle-draft/${currentSlug}`, { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      currentDraft = d.draft;
      updateDraftButton();
      // Update badge in sidebar
      const badge = document.getElementById(`badge-${currentSlug}`);
      badge.textContent = d.draft ? 'Draft' : 'Live';
      badge.className = `badge ${d.draft ? 'badge-draft' : 'badge-live'}`;
      updateSendButtons();
    });
}

function checkDeployment() {
  const statusEl = document.getElementById('deploy-status');
  statusEl.style.display = '';
  statusEl.className = 'status-msg info';
  statusEl.textContent = 'Checking deployment…';
  updateSendButtons();

  fetch(`/api/check-deployment/${currentSlug}`)
    .then(r => r.json())
    .then(d => {
      deploymentLive = d.live;
      if (d.live) {
        statusEl.className = 'status-msg ok';
        statusEl.textContent = 'Live ✓';
      } else {
        statusEl.className = 'status-msg warn';
        statusEl.textContent = d.reason ? `Not live: ${d.reason}` : 'Not deployed yet';
      }
      updateSendButtons();
    });
}

function updateSendButtons() {
  const canSend = !currentDraft && deploymentLive;
  document.getElementById('btn-test').disabled = false;
  document.getElementById('btn-send').disabled = !canSend;
}

function testSend() {
  const listEl = document.getElementById('test-contact-list');
  listEl.innerHTML = '<span style="color:var(--text-secondary)">Loading…</span>';
  document.getElementById('test-modal').classList.add('visible');
  fetch('/api/contacts').then(r => r.json()).then(d => {
    if (d.error) { listEl.innerHTML = `<span style="color:#f08080">${d.error}</span>`; return; }
    const contacts = d.contacts;
    listEl.innerHTML = '';
    const updateCount = () => {
      const n = listEl.querySelectorAll('input[type=checkbox]:checked').length;
      document.getElementById('test-selection-count').textContent = `(${n} selected)`;
    };
    const addRow = (html, checked) => {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex;align-items:center;gap:8px;cursor:pointer';
      label.innerHTML = html;
      label.querySelector('input').checked = checked;
      label.querySelector('input').addEventListener('change', updateCount);
      listEl.appendChild(label);
    };
    // "myself" option always first
    addRow('<input type="checkbox" data-self="1"> <span>Myself</span>', true);
    contacts.forEach(c => {
      addRow(`<input type="checkbox" data-name="${c.name}" data-email="${c.email}"> <span>${c.name || c.email} <span style="color:var(--text-secondary);font-size:11px">${c.name ? '&lt;' + c.email + '&gt;' : ''}</span></span>`, false);
    });
    updateCount();
  });
}

function closeTestModal() {
  document.getElementById('test-modal').classList.remove('visible');
}

function doTestSend() {
  const checkboxes = document.querySelectorAll('#test-contact-list input[type=checkbox]:checked');
  const recipients = [];
  checkboxes.forEach(cb => {
    if (cb.dataset.self) return;  // handled server-side when recipients empty? No — add as entry
    recipients.push({ name: cb.dataset.name, email: cb.dataset.email });
  });
  // Check if "myself" is checked
  const selfCb = document.querySelector('#test-contact-list input[data-self]');
  if (selfCb && selfCb.checked) recipients.unshift({ name: 'You', email: '__self__' });

  closeTestModal();
  const btn = document.getElementById('btn-test');
  btn.disabled = true;
  btn.textContent = 'Sending…';
  fetch(`/api/test-send/${currentSlug}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ recipients })
  }).then(r => r.json()).then(d => {
    btn.textContent = 'Test Send';
    updateSendButtons();
    const statusEl = document.getElementById('deploy-status');
    statusEl.style.display = '';
    if (d.ok) {
      statusEl.className = 'status-msg ok';
      statusEl.textContent = `Test sent to ${d.sent} recipient${d.sent !== 1 ? 's' : ''} ✓`;
    } else {
      statusEl.className = 'status-msg err';
      statusEl.textContent = `Error: ${d.error}`;
    }
  });
}

function confirmSend() {
  const count = contactCount !== null ? contactCount : '?';
  document.getElementById('modal-body').textContent =
    `This will send "${document.getElementById('toolbar-title').textContent}" to ${count} recipient${count !== 1 ? 's' : ''}. This cannot be undone.`;
  document.getElementById('modal').classList.add('visible');
}

function closeModal() {
  document.getElementById('modal').classList.remove('visible');
}

function doSend() {
  closeModal();
  const btn = document.getElementById('btn-send');
  btn.disabled = true;
  btn.textContent = 'Sending…';
  fetch(`/api/send/${currentSlug}`, { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      btn.textContent = 'Send All';
      updateSendButtons();
      const statusEl = document.getElementById('deploy-status');
      statusEl.style.display = '';
      if (d.ok) {
        statusEl.className = d.failed && d.failed.length ? 'status-msg warn' : 'status-msg ok';
        let msg = `Sent to ${d.sent} recipient${d.sent !== 1 ? 's' : ''} ✓`;
        if (d.skipped) msg += `, ${d.skipped} already sent`;
        if (d.failed && d.failed.length) msg += `, ${d.failed.length} failed`;
        statusEl.textContent = msg;
      } else {
        statusEl.className = 'status-msg err';
        statusEl.textContent = `Error: ${d.error}`;
      }
    });
}

// Close modal on overlay click
document.getElementById('modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();
});
document.getElementById('test-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeTestModal();
});

// Settings
function openSettings() {
  fetch('/api/settings').then(r => r.json()).then(d => {
    document.getElementById('settings-name').value = d.newsletter_name || '';
    document.getElementById('settings-sheet').value = d.has_sheet_id ? '(saved)' : '';
    document.getElementById('settings-modal').classList.add('visible');
  });
}
function closeSettings() {
  document.getElementById('settings-modal').classList.remove('visible');
}
function checkSentLog() {
  const el = document.getElementById('sent-log-result');
  el.style.display = 'block';
  el.textContent = 'Loading…';
  fetch('/api/sent-log').then(r => r.json()).then(d => {
    if (d.error) { el.textContent = `Error: ${d.error}`; return; }
    if (!d.rows || d.rows.length <= 1) { el.textContent = '(no entries yet)'; return; }
    const [header, ...rows] = d.rows;
    el.textContent = [header.join(' | '), ...rows.slice(-10).map(r => r.join(' | '))].join('\\n');
    if (rows.length > 10) el.textContent = `(showing last 10 of ${rows.length})\\n` + el.textContent;
  });
}
function testContacts() {
  const el = document.getElementById('contacts-test-result');
  el.textContent = 'Checking…';
  fetch('/api/contacts/count').then(r => r.json()).then(d => {
    el.textContent = d.error ? `Error: ${d.error}` : `✓ ${d.count} contact${d.count !== 1 ? 's' : ''} with Send=y`;
  });
}
function saveSettings() {
  const name = document.getElementById('settings-name').value.trim();
  const sheet = document.getElementById('settings-sheet').value.trim();
  const payload = {};
  if (name) payload.newsletter_name = name;
  if (sheet && sheet !== '(saved)') payload.sheet_id = sheet;
  fetch('/api/settings', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) })
    .then(r => r.json()).then(() => closeSettings());
}
document.getElementById('settings-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeSettings();
});
</script>
</body>
</html>"""


# --- Install command ---

def cmd_install(args):
    import shutil
    repo = Path(args.repo).resolve()
    if not (repo / "hugo.toml").exists() and not (repo / "config.toml").exists():
        print(f"Error: {repo} doesn't look like a Hugo site (no hugo.toml found).")
        return

    # Copy layouts
    src_layouts = PATR_ROOT / "layouts"
    dst_layouts = repo / "layouts" / "newsletter"
    if dst_layouts.exists():
        shutil.rmtree(dst_layouts)
    shutil.copytree(src_layouts, dst_layouts)
    print(f"✓ Layouts installed → {dst_layouts}")

    # Copy/append CSS
    src_css = PATR_ROOT / "assets" / "newsletter.css"
    dst_styles = repo / "assets" / "styles.css"
    dst_css = repo / "assets" / "newsletter.css"
    sentinel = "/* patr:newsletter */"
    if dst_styles.exists():
        existing = dst_styles.read_text()
        if sentinel not in existing:
            dst_styles.write_text(existing + f"\n{sentinel}\n" + src_css.read_text())
            print(f"✓ Newsletter CSS appended → {dst_styles}")
        else:
            print(f"✓ Newsletter CSS already in {dst_styles} (skipped)")
    else:
        shutil.copy(src_css, dst_css)
        print(f"✓ Newsletter CSS installed → {dst_css}")
        print(f"  Add it to your baseof.html: <link rel=\"stylesheet\" href=\"{{{{ $newsletter | relURL }}}}\">")

    # Create content stubs (don't overwrite)
    content_dst = repo / "content" / "newsletter"
    content_dst.mkdir(parents=True, exist_ok=True)

    index_md = content_dst / "_index.md"
    if not index_md.exists():
        index_md.write_text('---\ntitle: "Newsletter"\ndescription: ""\n---\n')
        print(f"✓ Created {index_md}")
    else:
        print(f"  Skipped {index_md} (already exists)")

    footer_md = content_dst / "footer.md"
    if not footer_md.exists():
        footer_md.write_text('---\ntitle: "Footer"\n_build:\n  render: never\n  list: never\n---\n')
        print(f"✓ Created {footer_md}")
    else:
        print(f"  Skipped {footer_md} (already exists)")

    print("\nPatr installed. Run: patr.py serve --repo", repo)


# --- Entry point ---

if __name__ == "__main__":
    import argparse
    import socket

    parser = argparse.ArgumentParser(prog="patr", description="Patr — Hugo newsletter tool")
    sub = parser.add_subparsers(dest="command")

    # serve
    serve_parser = sub.add_parser("serve", help="Start the Patr web UI")
    serve_parser.add_argument("--repo", default=".", help="Path to Hugo site root (default: cwd)")
    serve_parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode (fixed port 5000)")

    # install
    install_parser = sub.add_parser("install", help="Install Patr layouts/CSS into a Hugo site")
    install_parser.add_argument("--repo", required=True, help="Path to Hugo site root")

    args = parser.parse_args()

    if args.command == "install":
        cmd_install(args)

    else:
        # Default to serve (also handles no subcommand for backwards compat)
        repo_arg = getattr(args, "repo", ".")
        debug_arg = getattr(args, "debug", False)

        REPO_ROOT = Path(repo_arg).resolve()
        CONTENT_DIR = REPO_ROOT / "content" / "newsletter"

        # Patch module-level names used by Flask routes
        import sys
        this = sys.modules[__name__]
        this.REPO_ROOT = REPO_ROOT
        this.CONTENT_DIR = CONTENT_DIR

        if debug_arg:
            port = 5000
        else:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]

            def open_browser():
                time.sleep(1)
                webbrowser.open(f"http://127.0.0.1:{port}")

            threading.Thread(target=open_browser, daemon=True).start()

        app.config["PORT"] = port
        app.run(host="127.0.0.1", port=port, debug=debug_arg)
