# CLAUDE.md

This file provides guidance to Claude Code when working with the Patr repository.

## Overview

**Patr** is a local Flask web app for writing and sending Hugo-based newsletters. It runs on the author's machine, points at a Hugo site repo, and provides a browser UI for editing editions, previewing them as email or web, toggling draft/live status, and sending via Gmail.

The name comes from पत्र/పత్రం (Sanskrit/Telugu for "letter/document"). Spiritual successor to Inkling (which used Google Docs + GAS + Netlify).

## Working style

- **Use red/green TDD wherever possible.** Write a failing test first, confirm
  it fails for the right reason, then fix the code, then confirm it passes. If
  you're about to skip this (e.g. a change seems obvious, or it's hard to
  test), explicitly say so and ask for confirmation before proceeding.
- **Always lint and format before committing.** Run `uv run ruff check
  --unsafe-fixes --fix` and `uv run ruff format` before committing. Use
  `prettier` to format JS and CSS files in the source.
- **Always run all tests before committing.** Run `uv run pytest` (includes E2E
  tests). If tests time out, re-run with `uv run pytest -x` to stop at the
  first failure and diagnose before retrying.
- **Update screenshots when the UI changes.** Screenshot tests are excluded
  from the default test run. Run them manually with `uv run pytest -m
  screenshots` when the UI changes, then commit the updated screenshots
  alongside the change that caused them to change.
- **Always update doc-strings.** Everytime a function is being changed or
  edited, make sure it's doc-string reflects what the function is doing.
- **Always update the README and CLAUDE.md.** With every change, check if the
  README and/CLAUDE.md need updating. New features need documentation in the
  README, etc.

## Coding style

- Define constants at the top of Python modules not in random places.
- Avoid using regexes if possible. They are brittle and can break easily. Parse
  HTML or markdown using appropriate tools, where possible.
- Import at the top of Python modules and avoid importing inside functions,
  unless there's no way out.
- Add docstrings to functions. Future readers of the code shouldn't need to dig
  their way through commit messages to figure out what functions are doing.

## Running Patr

```bash
# Install into a Hugo site (one-time setup)
patr install --repo /path/to/hugo-site

# Start the UI (always port 5000; use --port to override)
patr serve --repo /path/to/hugo-site
patr serve --repo /path/to/hugo-site --port 5001

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
      editor.css         # Editor-specific styles
      main.jsx           # React entry point
      App.jsx            # Root component: edition list, theme, modals
      components/
        Sidebar.jsx      # Edition list + auth bar
        MainPanel.jsx    # Write/Split/Preview modes, action bar
        EditorPanel.jsx  # CodeMirror markdown editor, auto-save, auto-commit, image upload
        modals/          # SettingsModal, NewEditionModal, TestSendModal, ConfirmModal
      dist/              # Built output (committed; npm not needed on install)
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

- Always binds to port 5000 (fixed, so `localStorage` origin is stable across restarts); `--port` overrides
- If port is busy: probes `/api/editions` to distinguish a running Patr instance from another process
- Port check and browser open only run in the initial process (`WERKZEUG_RUN_MAIN` guard), not on reloader restarts
- Flask reloader always enabled (restarts on Python file changes)
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

`load_newsletter_config()` merges both sources. `save_hugo_patr_params()` uses `tomlkit` to write `[params.patr]` keys into `hugo.toml` while preserving comments, key order, and formatting.

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

- Draft toggle and content saves use `python-frontmatter` + a custom PyYAML dumper (`_PatrYamlDumper`) that preserves key order and uses literal block scalars for multi-line strings
- `footer/index.md` has `_build: render:never, list:never` so Hugo doesn't give it its own URL

### Frontend

The UI is a React app (built with Vite, output committed to `static/dist/`). The editor uses **CodeMirror** (`@uiw/react-codemirror`) with the `@codemirror/lang-markdown` extension — raw markdown editing with syntax highlighting, no lossy AST round-trip.

- `EditorPanel` loads content via `GET /api/edition/<slug>/content`, auto-saves via `POST` with a 1-second debounce, and auto-commits via `POST /api/edition/<slug>/commit` with a 5-second debounce (amends previous `wip:` commit if diff < 500 bytes **and** author date < 5 min, else new commit)
- On every save, `write_backup()` writes a timestamped backup to `~/.local/share/patr/backups/<repo-slug>/<edition-slug>/` — always-on, regardless of git availability. Same amend-vs-new logic as git: overwrites the latest backup if the diff is small and it is recent, otherwise writes a new `<YYYYmmddTHHMMSS>.md` file. Backups accumulate indefinitely.
- Body content is kept in a ref (not React state) to avoid per-keystroke re-renders; `initialBody` state is only set on load
- Images are uploaded via `POST /api/edition/<slug>/upload-image`; stored alongside the edition (bundle dir for page bundles, sibling `slug/` dir for flat files); inserted as relative markdown `![](filename)`
- Toolbar buttons insert/wrap markdown syntax at the cursor (no WYSIWYG schema)
- Three editor modes in `MainPanel`: **Write** (full-width editor), **Split** (editor + preview side-by-side, refreshes on save), **Preview Email** / **Preview Web** (full-width iframe)
- Active mode is stored in the URL hash fragment: `#slug` (write), `#slug/split`, `#slug/email`, `#slug/web`
- **Preview Email** mode has a **Download PDF** button (`/preview/<slug>/email.pdf`) — rendered by Playwright (system Chromium/Chrome) as a single-page PDF
- To rebuild the frontend: `npm run build` in the repo root (requires Node + npm, one-time dev setup)

### Hugo Templates

- `layouts/newsletter/single.html` — includes footer via `.Site.GetPage "/newsletter/footer"`; inlines `newsletter.css` via `resources.Get`
- `layouts/newsletter/list.html` — archive page; inlines `newsletter.css`
- `layouts/newsletter/_markup/render-image.html` — **newsletter-scoped render hook**, wraps images in `<figure>/<figcaption>`. Lives in `layouts/newsletter/_markup/` intentionally — do NOT move to `layouts/_default/_markup/` as it would affect all pages.

### Email Rendering

- Python `markdown` library with `extra` and `smarty` extensions
- `render_md()` mirrors Hugo's render hook: post-processes `<img>` → `<figure>/<figcaption>` when alt text is non-empty
- `absolutify_urls()` rewrites relative and root-relative image src paths to absolute URLs before sending
- CSS inlined via `css-inline` before sending
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

### Backups

On every save, `write_backup()` writes a timestamped backup to
`~/.local/share/patr/backups/<repo-slug>/<edition-slug>/` — always-on,
regardless of git availability:

```
~/.local/share/patr/backups/
  home-punchagan-code-my-repos-newsletter/
    my-edition/
      20260405T142301.md
      20260405T142456.md
      ...
```

The repo slug is derived from `REPO_ROOT` with path separators replaced by
`-`. Backups use the same amend-vs-new logic as git auto-commit: overwrite the
latest if the diff is small (< `COMMIT_DIFF_THRESHOLD` bytes) and it is recent
(< `COMMIT_AGE_THRESHOLD` seconds), otherwise write a new timestamped file.
Backups accumulate indefinitely. When Git is also available, the existing
auto-commit path runs alongside — backups and git commits are independent.

## Known gaps / things to build

Features not yet in the UI that users currently have to do by editing files directly:

- **Edition deletion** — no delete button; user must remove the folder manually
- **Edition date editing** — date is set at creation and can't be changed from the UI; should be a field in EditorPanel
- **Git-free mode** — git auto-commit still requires Git; the goal is to make Git a fully optional prerequisite so Patr works as a pure email newsletter tool pointed at any plain directory

### Hugo-free mode

Patr can run against any plain directory — no `hugo.toml`, no Hugo installed.
Hugo is detected via `hugo_mode()` (checks for `hugo.toml` in `REPO_ROOT`).

**How it works:**

- `load_hugo_config()` — returns `{}` when `hugo.toml` is absent.
- `load_newsletter_config()` — defaults `email_only = True` automatically in
  hugo-free mode.
- `save_hugo_patr_params()` — falls back to `patr.toml` in `REPO_ROOT` when
  no `hugo.toml` exists.
- `patr install` — prints a friendly message and exits early in hugo-free mode.
- `CONTENT_DIR` — set to `REPO_ROOT` directly (no `content/newsletter/`
  subdirectory).
- `get_editions()` — picks up both page bundles (`slug/index.md`) and flat
  `.md` files in hugo-free mode. Hugo mode is bundles only.
- `load_edition()` — falls back to `slug.md` when no bundle exists in
  hugo-free mode.
- `edition_dir_for(f)` — resolves image directory: `f.parent` for bundles,
  `f.with_suffix('')` (sibling dir) for flat files.
- `/preview/<slug>/web` — returns 501 in hugo-free mode.
- `/preview/<slug>/email` — omits "View in browser" link in hugo-free mode.
- Flat-file warning in `/api/editions` — only shown in Hugo mode (flat files
  are valid editions in hugo-free mode).
- Images for flat file editions — stored in a sibling `slug/` directory,
  served via the existing `/newsletter/<slug>/<filename>` route.
