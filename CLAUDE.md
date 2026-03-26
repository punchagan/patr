# CLAUDE.md

This file provides guidance to Claude Code when working with the Patr repository.

## Overview

**Patr** is a local Flask web app for managing and sending Hugo-based newsletters. It runs on the author's machine, points at a Hugo site repo, and provides a browser UI for previewing, toggling draft/live status, and sending editions via Gmail.

The name comes from पत्र/పత్రం (Sanskrit/Telugu for "letter/document"). Spiritual successor to Inkling (which used Google Docs + GAS + Netlify).

## Running Patr

```bash
# Point at a Hugo site and start the UI
./patr.py serve --repo /path/to/hugo-site

# Debug mode: fixed port 5000, Flask reloader enabled, no browser auto-open
./patr.py serve --repo /path/to/hugo-site --debug

# Install layouts/CSS into a Hugo site (one-time setup)
./patr.py install --repo /path/to/hugo-site
```

Patr uses `uv` inline script dependencies (PEP 723) — no separate install step needed. Run directly with `./patr.py` or `uv run patr.py`.

## Architecture

### Repo Structure

```
patr/
  patr.py                          # Main Flask app + CLI entry point
  layouts/                           # Hugo layout templates (copied to {repo}/layouts/newsletter/ by install)
    list.html                        # Archive list page
    single.html                      # Single post (includes footer via GetPage)
    _markup/render-image.html        # Newsletter-scoped render hook (figure/figcaption)
  assets/
    newsletter.css                   # Newsletter styles (appended to site's styles.css by install)
  # content/newsletter/ does not exist — stubs created programmatically by install
```

### Key Design Decisions

- **Single script** — `patr.py` is self-contained with uv inline deps; no package install needed
- **`PATR_ROOT`** — path to patr's own repo (layouts, assets, stubs)
- **`REPO_ROOT`** — path to the target Hugo site, set from `--repo` arg (defaults to cwd)
- **`CONTENT_DIR`** — `REPO_ROOT / "content" / "newsletter"`
- **`CONFIG_DIR`** — `~/.config/patr/` — credentials and local config, never in any repo
- Hugo auto-detected via `shutil.which()`: checks `hugo.sh` in repo root first, then `hugo` in PATH

### Install Command

`patr.py install --repo <path>` does:
1. Copies `layouts/newsletter/` → `{repo}/layouts/newsletter/`
2. Appends `assets/newsletter.css` to `{repo}/assets/styles.css` (idempotent via `/* patr:newsletter */` sentinel)
3. Creates `content/newsletter/_index.md` and `footer.md` if not present

### Flask App

- Normal mode: random free port via `socket.bind(("127.0.0.1", 0))`; auto-opens browser
- Debug mode: fixed port 5000, Flask reloader enabled, no browser open
- Port stored in `app.config['PORT']` (not a global)
- `OAUTHLIB_INSECURE_TRANSPORT=1` and `OAUTHLIB_RELAX_TOKEN_SCOPE=1` set at startup (localhost OAuth)

### OAuth / Auth

- Desktop app credentials (GCP) — allows any `http://127.0.0.1:*` redirect without pre-registration
- PKCE implemented manually (`secrets.token_urlsafe` + SHA256 challenge)
- State + verifier stored in `_oauth_state_store` dict (not Flask session) — works from both `localhost` and `127.0.0.1`
- After callback, redirects back to originating host (preserves localhost vs 127.0.0.1)
- Credentials: `~/.config/newsletter/credentials.json` (GCP Desktop app JSON)
- Token: `~/.config/newsletter/token.json` (auto-written on connect)
- Scopes: `gmail.send`, `userinfo.email`, `spreadsheets`

### Config Split

| Location | Contents |
|---|---|
| `{hugo-site}/hugo.toml` → `[params.newsletter]` | `name` and other non-sensitive settings |
| `~/.config/newsletter/config.toml` | `sheet_id` (sensitive — contacts exposure risk) |
| `~/.config/newsletter/credentials.json` | GCP OAuth client credentials |
| `~/.config/newsletter/token.json` | OAuth access/refresh token |

`load_newsletter_config()` merges both sources. `save_hugo_newsletter_params()` surgically patches `hugo.toml` without round-tripping through a TOML serializer (preserves key order, block scalars, comments).

### Content Format

Editions are regular `.md` files in `content/newsletter/` (NOT page bundles). Frontmatter:

```yaml
---
title: "Edition title"
date: 2024-03-15
draft: true
intro: |
  Optional intro paragraph shown separately in italic/bordered style.
---

Body content here.
```

- `_index.md` and `footer.md` are excluded from the editions list
- Draft toggle uses surgical regex on the frontmatter block only (preserves block scalars, key order)
- `footer.md` has `_build: render:never, list:never` so Hugo doesn't give it its own URL

### Hugo Templates

- `layouts/newsletter/single.html` — includes footer via `.Site.GetPage "/newsletter/footer"`
- `layouts/newsletter/_markup/render-image.html` — **newsletter-scoped render hook**, wraps images in `<figure>/<figcaption>`. Lives in `layouts/newsletter/_markup/` intentionally — do NOT move to `layouts/_default/_markup/` as it would affect all pages.

### Email Rendering

- Python `markdown` library with `extra` and `smarty` extensions
- `render_md()` mirrors Hugo's render hook: post-processes `<img>` → `<figure>/<figcaption>` when alt text is non-empty
- CSS inlined via `premailer` before sending
- Sender address fetched from OAuth2 userinfo API (not hardcoded)

### Contacts (Google Sheets)

- Sheet columns: `Name`, `Email`, `Send` (opt-out with `n`/`no`; blank = include by default)
- Sent Log tab: append-only rows of `(email, slug, sent_at)` — created automatically on first send
- `get_already_sent()` checks Sent Log to skip contacts already sent a given slug
- Rate limit: `time.sleep(0.9)` between sends
- Per-contact error handling: failures collected and reported; successful sends logged immediately

### Web Preview

Runs `hugo -D --baseURL=http://127.0.0.1:{PORT}/` and redirects iframe to the built output. Serves `public/` via catch-all Flask route. Serves `static/images/` at `/images/`.

## Pending Work

- [ ] New edition button — create `.md` with pre-filled frontmatter, open in editor
- [ ] Edit in Obsidian link (already in UI as placeholder)
- [ ] Publish button — git commit + push (invisible to author; just "Published ✓")
- [ ] Extract into proper installable package (currently a single script)
