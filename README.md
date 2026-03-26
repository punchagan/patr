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

- [Hugo](https://gohugo.io/installation/) — to build and preview the site
- [Git](https://git-scm.com/downloads) — to publish editions
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — to install Patr (manages Python automatically)
- A GCP project with Gmail API, Google Sheets API, and OAuth 2.0 Desktop credentials (see below)

### GCP credentials setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project.
2. Enable the **Gmail API** and **Google Sheets API**:
   - Navigate to **APIs & Services → Library**
   - Search for and enable each API.
3. Configure the OAuth consent screen:
   - Go to **APIs & Services → OAuth consent screen**
   - Choose **External**, fill in an app name and your email, and save.
   - Under **Test users**, add the Gmail address(es) that will use Patr.
4. Create OAuth 2.0 credentials:
   - Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Choose **Desktop app**, give it a name, and click Create.
   - Download the JSON file.
5. Save the downloaded file as `~/.config/patr/credentials.json` (Linux/macOS) or `%USERPROFILE%\.config\patr\credentials.json` (Windows).

## Installation

```bash
uv tool install git+https://github.com/punchagan/patr
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

## Development

Clone the repo and install in editable mode:

```bash
git clone https://github.com/punchagan/patr
cd patr
uv pip install -e .
```

Run in debug mode (fixed port 5000, Flask reloader enabled, no browser auto-open):

```bash
patr serve --repo /path/to/hugo-site --debug
```

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
