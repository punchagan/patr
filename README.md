# Patr

A local web UI for writing and sending Hugo-based newsletters via Gmail.

The name comes from पत्र/పత్రం (Sanskrit/Telugu for "letter/document").

> **Note:** This project was largely written with [Claude Code](https://claude.ai/code). The code has been tested and verified, but use at your own discretion.

## What it does

- Browse and preview newsletter editions (email and web views)
- Toggle draft/live status
- Send test emails to selected contacts
- Send to your full mailing list (Google Sheets)
- Create new editions from the UI

## Prerequisites

- A Hugo site
- Python 3.11+
- A GCP project with Gmail API, Google Sheets API, and OAuth 2.0 Desktop credentials
- `credentials.json` saved to `~/.config/patr/credentials.json`

## Installation

```bash
pip install -e .
# or
uv pip install -e .
```

Then install Patr's layouts and assets into your Hugo site:

```bash
patr install --repo /path/to/hugo-site
```

This copies Hugo templates and CSS into the site, creates `content/newsletter/` stubs, and optionally adds a nav menu entry.

If you have existing flat `.md` newsletter editions, migrate them to page bundles first:

```bash
patr migrate --repo /path/to/hugo-site          # dry run
patr migrate --repo /path/to/hugo-site --apply  # apply
```

## Usage

```bash
patr serve --repo /path/to/hugo-site
```

Opens a browser UI at a random local port. Connect Gmail via the ⚙ settings panel on first use.

```bash
patr serve --repo /path/to/hugo-site --debug    # fixed port 5000, Flask reloader
```

## Configuration

| Location | Contents |
|---|---|
| `{hugo-site}/hugo.toml` → `[params.patr]` | `name` — newsletter display name |
| `~/.config/patr/config.toml` | `sheet_id` — Google Sheets contacts sheet |
| `~/.config/patr/credentials.json` | GCP OAuth client credentials (Desktop app) |

### Contacts sheet format

Columns: `Name`, `Email`, `Send` (leave blank or set to `y` to include; `n`/`no` to opt out).

A "Sent Log" tab is created automatically on first send.

## Content format

Editions are Hugo page bundles:

```
content/newsletter/
  my-edition/
    index.md      # frontmatter + body
    photo.jpg     # images alongside content
```

Frontmatter:

```yaml
---
title: "Edition title"
date: 2024-03-15
draft: true
intro: |
  Optional intro shown in italic/bordered style.
---

Body content. Reference images relatively: ![alt](photo.jpg)
```
