# CLAUDE.md

This file provides guidance to Claude Code when working with the Patr repository.

## Overview

**Patr** is a local Flask web app for managing and sending Hugo-based newsletters. It runs on the author's machine, points at a Hugo site repo, and provides a browser UI for previewing, toggling draft/live status, and sending editions via Gmail.

The name comes from पत्र/పత్రం (Sanskrit/Telugu for "letter/document"). Spiritual successor to Inkling (which used Google Docs + GAS + Netlify).

## Running Patr

```bash
# Install into a Hugo site (one-time setup)
patr install --repo /path/to/hugo-site

# Start the UI
patr serve --repo /path/to/hugo-site

# Debug mode: fixed port 5000, Flask reloader enabled, no browser auto-open
patr serve --repo /path/to/hugo-site --debug

# Migrate existing flat .md editions to page bundles (dry run first)
patr migrate --repo /path/to/hugo-site
patr migrate --repo /path/to/hugo-site --apply
```

Install with `uv pip install -e .` or `pip install -e .`. Requires Python 3.11+.

## Architecture

### Repo Structure

```
patr/
  pyproject.toml
  src/patr/
    __main__.py          # python -m patr entry point
    cli.py               # argparse, cmd_serve, cmd_install, cmd_migrate
    server.py            # Flask app + all routes
    config.py            # load/save hugo config, find_hugo, build_hugo
    auth.py              # OAuth flow, PKCE, get_auth, auth_status
    content.py           # editions, markdown rendering, email/web HTML builders
    contacts.py          # Google Sheets fetch, sent log
    gmail.py             # send_email
    state.py             # mutable globals: PATR_ROOT, REPO_ROOT, CONTENT_DIR, etc.
    templates/
      index.html         # Jinja2 template for the UI
    static/
      app.css            # UI styles
      app.js             # UI logic
    data/
      layouts/           # Hugo templates (copied to {repo}/layouts/newsletter/ by install)
      assets/
        newsletter.css   # Newsletter styles (copied to {repo}/assets/ by install)
```

### Key Design Decisions

- **`state.py`** — mutable globals set at startup by `cli.py`. All modules import `from patr import state` and use `state.REPO_ROOT` etc.
- **`REPO_ROOT`** — path to the target Hugo site, set from `--repo` arg
- **`CONTENT_DIR`** — `REPO_ROOT / "content" / "newsletter"`
- **`CONFIG_DIR`** — `~/.config/patr/` — credentials and local config, never in any repo
- **`DATA_DIR`** — `src/patr/data/` — layouts and assets bundled with the package
- Hugo auto-detected via `shutil.which()`: checks `hugo.sh` in repo root first, then `hugo` in PATH
- Server imports deferred in `cmd_serve` so `state` is configured before Flask routes load

### Install Command

`patr install --repo <path>` does:
1. Copies `data/layouts/` → `{repo}/layouts/newsletter/`
2. Copies `data/assets/newsletter.css` → `{repo}/assets/newsletter.css`
3. Creates `content/newsletter/_index.md` and `content/newsletter/footer/index.md`
4. Optionally adds a `[[menus.main]]` entry to `hugo.toml`

Fails if flat `.md` edition files exist in `content/newsletter/` — run `patr migrate` first.

### Migrate Command

`patr migrate --repo <path>` (dry run) / `--apply` (execute):
- Moves each `slug.md` → `slug/index.md` (page bundle)
- Finds `/images/newsletter/foo.jpg` references in each edition, moves those image files into the bundle, rewrites paths to relative (`foo.jpg`)
- Footer images in `static/images/newsletter/` are left alone (shared, referenced via absolute path)

### Flask App

- Normal mode: random free port via `socket.bind(("127.0.0.1", 0))`; auto-opens browser
- Debug mode: fixed port 5000, Flask reloader enabled, no browser open
- Port stored in `app.config['PORT']`
- `OAUTHLIB_INSECURE_TRANSPORT=1` and `OAUTHLIB_RELAX_TOKEN_SCOPE=1` set at startup (localhost OAuth)

### OAuth / Auth

- Desktop app credentials (GCP) — allows any `http://127.0.0.1:*` redirect without pre-registration
- PKCE implemented manually (`secrets.token_urlsafe` + SHA256 challenge)
- State + verifier stored in `_oauth_state_store` dict (not Flask session) — works from both `localhost` and `127.0.0.1`
- After callback, redirects back to originating host (preserves localhost vs 127.0.0.1)
- Credentials: `~/.config/patr/credentials.json` (GCP Desktop app JSON)
- Token: `~/.config/patr/token.json` (auto-written on connect)
- Scopes: `gmail.send`, `userinfo.email`, `spreadsheets`

### Config Split

| Location | Contents |
|---|---|
| `{hugo-site}/hugo.toml` → `[params.patr]` | `name` and other non-sensitive settings |
| `~/.config/patr/config.toml` | `sheet_id` (sensitive — contacts exposure risk) |
| `~/.config/patr/credentials.json` | GCP OAuth client credentials |
| `~/.config/patr/token.json` | OAuth access/refresh token |

`load_newsletter_config()` merges both sources. `save_hugo_patr_params()` surgically patches `hugo.toml` without round-tripping through a TOML serializer (preserves key order, block scalars, comments).

### Content Format

Editions are **page bundles** — directories in `content/newsletter/` containing `index.md` plus any images:

```
content/newsletter/
  _index.md                    # section index
  footer/
    index.md                   # footer included in every edition (_build: render/list: never)
  my-edition/
    index.md                   # edition content
    photo.jpg                  # images live alongside content
```

Frontmatter:

```yaml
---
title: "Edition title"
date: 2024-03-15
draft: true
intro: |
  Optional intro paragraph shown in italic/bordered style.
---

Body content here. Reference images relatively: ![alt](photo.jpg)
```

- Draft toggle uses surgical regex on the frontmatter block only (preserves block scalars, key order)
- `footer/index.md` has `_build: render:never, list:never` so Hugo doesn't give it its own URL

### Hugo Templates

- `layouts/newsletter/single.html` — includes footer via `.Site.GetPage "/newsletter/footer"`; inlines `newsletter.css` via `resources.Get`
- `layouts/newsletter/list.html` — archive page; inlines `newsletter.css`
- `layouts/newsletter/_markup/render-image.html` — **newsletter-scoped render hook**, wraps images in `<figure>/<figcaption>`. Lives in `layouts/newsletter/_markup/` intentionally — do NOT move to `layouts/_default/_markup/` as it would affect all pages.

### Email Rendering

- Python `markdown` library with `extra` and `smarty` extensions
- `render_md()` mirrors Hugo's render hook: post-processes `<img>` → `<figure>/<figcaption>` when alt text is non-empty
- `absolutify_urls()` rewrites relative and root-relative image src paths to absolute URLs before sending
- CSS inlined via `premailer` before sending
- Flask email preview uses `build_web_html()` with `<base href="/newsletter/{slug}/">` so relative image paths resolve; served by `/newsletter/<slug>/<filename>` route
- Sender address fetched from OAuth2 userinfo API (not hardcoded)

### Contacts (Google Sheets)

- Sheet columns: `Name`, `Email`, `Send` (opt-out with `n`/`no`; blank = include by default)
- Sent Log tab: append-only rows of `(email, slug, sent_at)` — created automatically on first send
- `get_already_sent()` checks Sent Log to skip contacts already sent a given slug
- Rate limit: `time.sleep(0.9)` between sends
- Per-contact error handling: failures collected and reported; successful sends logged immediately

### Web Preview

Runs `hugo -D --baseURL=http://127.0.0.1:{PORT}/` and redirects iframe to the built output. Serves `public/` via catch-all Flask route. Serves `static/images/` at `/images/`.
