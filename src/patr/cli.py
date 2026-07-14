import argparse
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None

from patr import state
from patr.auth import get_auth
from patr.config import git_mode, hugo_mode, load_newsletter_config
from patr.contacts import get_all_sent_slugs
from patr.content import (
    get_editions,
    load_edition,
    plan_backup_pruning,
    repo_slug,
    write_edition_frontmatter,
)


def cmd_install(args) -> None:
    repo = Path(args.repo).resolve()
    state.REPO_ROOT = repo
    if not hugo_mode():
        print("Hugo-free mode: no installation needed.")
        print(f"Run: patr serve --repo {repo}")
        return

    # Copy layouts
    src_layouts = state.DATA_DIR / "layouts"
    dst_layouts = repo / "layouts" / "newsletter"
    if dst_layouts.exists():
        shutil.rmtree(dst_layouts)
    shutil.copytree(src_layouts, dst_layouts)
    print(f"✓ Layouts installed → {dst_layouts}")

    # Copy newsletter CSS (loaded inline by templates via resources.Get)
    src_css = state.DATA_DIR / "assets" / "newsletter.css"
    dst_css = repo / "assets" / "newsletter.css"
    shutil.copy(src_css, dst_css)
    print(f"✓ Newsletter CSS installed → {dst_css}")

    # Check for flat .md editions — patr requires page bundles
    content_dst = repo / "content" / "newsletter"
    if content_dst.exists():
        flat_editions = [
            f
            for f in content_dst.glob("*.md")
            if f.name not in ("_index.md", "footer.md")
        ]
        if flat_editions:
            print(f"Error: flat edition files found in {content_dst}:")
            for f in flat_editions:
                print(f"  {f.name}")
            print("\nPatr uses page bundles (content/newsletter/slug/index.md).")
            print("Preview what will change:")
            print(f"  patr migrate --repo {repo}")
            print("Then apply the migration:")
            print(f"  patr migrate --repo {repo} --apply")
            return
        print(
            "  Content directory exists and uses page bundles, skipping stub creation."
        )
    else:
        content_dst.mkdir(parents=True)

        index_md = content_dst / "_index.md"
        nl_name = load_newsletter_config().get("name", "Newsletter")
        index_md.write_text(f'---\ntitle: "{nl_name}"\ndescription: ""\n---\n')
        print(f"✓ Created {index_md}")

        footer_dir = content_dst / "footer"
        footer_dir.mkdir()
        (footer_dir / "index.md").write_text(
            '---\ntitle: "Footer"\n_build:\n  render: never\n  list: never\n---\n'
        )
        print(f"✓ Created {footer_dir / 'index.md'}")

    # Offer to initialize a git repo if git is available but dir isn't one
    if shutil.which("git") and not git_mode():
        print(
            "\nThis directory is not a git repo. Initialize one for"
            " auto-commit and version history?"
        )
        if input("[y/N] ").strip().lower() == "y":
            subprocess.run(["git", "init"], cwd=repo, check=False)
            print("✓ Git repository initialized")

    # Ask about menu entry
    add_menu = input("\nAdd newsletter to site menu? [y/N] ").strip().lower()
    if add_menu == "y":
        weight = input("Menu weight (default 10): ").strip() or "10"
        try:
            weight = int(weight)
        except ValueError:
            weight = 10
        hugo_toml = repo / "hugo.toml"
        text = hugo_toml.read_text()
        nl_name = load_newsletter_config().get("name", "Newsletter")
        menu_entry = f'\n[[menus.main]]\n  name = "{nl_name}"\n  url = "/newsletter/"\n  weight = {weight}\n'
        if "[[menus.main]]" in text and "/newsletter/" in text:
            print("  Menu entry already exists (skipped)")
        else:
            hugo_toml.write_text(text + menu_entry)
            print(f"✓ Menu entry added (weight={weight})")

    # Create a launcher on the Desktop on Windows
    if os.name == "nt":
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            )
            desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])
        except Exception:
            desktop = Path.home()
        bat = desktop / f"start-patr-{repo.name}.bat"
        bat.write_text(
            f'@echo off\nset PYTHONUTF8=1\npatr serve --repo "{repo}"\npause\n'
        )
        print(f"✓ Created launcher on Desktop → {bat}")

    print("\nPatr installed. Run: patr serve --repo", repo)
    print("Open the ⚙ settings panel to set your newsletter name and contacts sheet.")


def cmd_migrate(args) -> None:
    repo = Path(args.repo).resolve()
    content_dir = repo / "content" / "newsletter"
    static_images_dir = repo / "static" / "images" / "newsletter"
    dry_run = not args.apply

    if not content_dir.exists():
        print(f"Error: {content_dir} does not exist.")
        return

    if dry_run:
        print("Dry run — pass --apply to move files.\n")

    editions_moved = 0
    skipped = 0
    for f in sorted(content_dir.glob("*.md")):
        if f.name == "_index.md":
            continue
        slug = f.stem
        bundle_dir = content_dir / slug
        if bundle_dir.exists():
            print(f"  skip  {f.name} (bundle already exists)")
            skipped += 1
            continue

        text = f.read_text()

        # Find /images/newsletter/foo.jpg references (not footer images)
        image_refs = re.findall(r'/images/newsletter/([^\s)"\']+)', text)
        images_to_move = []
        for img in image_refs:
            src = static_images_dir / img
            if src.exists():
                images_to_move.append(img)

        verb = "move" if not dry_run else "would move"
        print(f"  {verb}  {f.name} → {slug}/index.md")
        for img in images_to_move:
            print(f"          static/images/newsletter/{img} → {slug}/{img}")

        if not dry_run:
            bundle_dir.mkdir()
            # Rewrite image paths before writing index.md
            new_text = re.sub(r'/images/newsletter/([^\s)"\']+)', r"\1", text)
            (bundle_dir / "index.md").write_text(new_text)
            f.unlink()
            for img in images_to_move:
                shutil.move(str(static_images_dir / img), str(bundle_dir / img))

        editions_moved += 1

    print(
        f"\n{'Would move' if dry_run else 'Moved'} {editions_moved} edition(s), skipped {skipped}."
    )
    if dry_run and editions_moved:
        print("Run with --apply to move files.")


def cmd_import_sent_log(args) -> None:
    """Backfill local `sent: full` metadata for editions that appear in the
    Google Sheet's Sent Log tab but have no local sent status yet.

    Historical sends can't be reconstructed as partial vs. full (the
    contact list may have changed since), so any match is marked "full".
    Editions that already have a local sent status (e.g. "partial") are
    left untouched.
    """
    state.REPO_ROOT = Path(args.repo).resolve()
    state.CONTENT_DIR = (
        state.REPO_ROOT / "content" / "newsletter" if hugo_mode() else state.REPO_ROOT
    )
    dry_run = not args.apply

    newsletter_config = load_newsletter_config()
    sheet_id = newsletter_config.get("sheet_id")
    if not sheet_id:
        print(f"Error: sheet_id not configured in {state.CONFIG_DIR / 'config.toml'}")
        return

    creds = get_auth()
    sent_slugs = get_all_sent_slugs(sheet_id, creds)

    if dry_run:
        print("Dry run — pass --apply to write changes.\n")

    marked = 0
    skipped = 0
    for edition in get_editions():
        slug = edition["slug"]
        if slug not in sent_slugs:
            continue
        if edition.get("sent"):
            print(f"  skip  {slug} (already marked {edition['sent']!r})")
            skipped += 1
            continue

        verb = "mark" if not dry_run else "would mark"
        print(f"  {verb}  {slug} → sent: full")
        if not dry_run:
            f, post = load_edition(slug)
            post.metadata["sent"] = "full"
            write_edition_frontmatter(f, post)
        marked += 1

    print(
        f"\n{'Would mark' if dry_run else 'Marked'} {marked} edition(s) as sent, skipped {skipped}."
    )
    if dry_run and marked:
        print("Run with --apply to write changes.")


def cmd_prune_backups(args) -> None:
    """Thin out closely-timestamped edition backups.

    Text backups are cheap, so this isn't storage-driven rotation — it's a
    manual, dry-run-by-default declutter of the History list: for each
    edition, always keeps the first and last backup, and drops any backup
    in between whose diff from the last *kept* checkpoint is smaller than
    COMMIT_DIFF_THRESHOLD (i.e. it didn't represent much real change).
    Idempotent: re-running after an --apply finds nothing left to prune,
    since only first/last and real checkpoints survive.
    """
    state.REPO_ROOT = Path(args.repo).resolve()
    dry_run = not args.apply
    backups_root = state.BACKUPS_DIR / repo_slug()

    if not backups_root.exists():
        print(f"No backups found at {backups_root}")
        return

    plan = plan_backup_pruning(backups_root)
    total = sum(len(paths) for paths in plan.values())

    if dry_run:
        print("Dry run — pass --apply to delete files.\n")

    for slug, paths in plan.items():
        if not paths:
            continue
        verb = "would delete" if dry_run else "deleting"
        print(f"  {slug}: {verb} {len(paths)} backup(s)")
        for path in paths:
            print(f"    {path.name}")
        if not dry_run:
            for path in paths:
                path.unlink()

    print(f"\n{'Would delete' if dry_run else 'Deleted'} {total} backup file(s).")
    if dry_run and total:
        print("Run with --apply to delete.")


def cmd_serve(args) -> None:
    state.REPO_ROOT = Path(args.repo).resolve()
    if hugo_mode():
        state.CONTENT_DIR = state.REPO_ROOT / "content" / "newsletter"
        if not (state.REPO_ROOT / "layouts" / "newsletter").exists():
            print(f"Error: Patr layouts not found in {state.REPO_ROOT}.")
            print(f"Run first: patr install --repo {state.REPO_ROOT}")
            raise SystemExit(1)
    else:
        state.CONTENT_DIR = state.REPO_ROOT

    # Import server after state is configured
    from patr.server import app

    # Only check free port, open browser on initial start, not on reloader restarts
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", args.port))
            except OSError as e:
                print(e)
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{args.port}/api/editions", timeout=1
                    )
                    print(f"Patr is already running at http://127.0.0.1:{args.port}")
                except Exception:
                    print(
                        f"Error: port {args.port} is already in use by another process."
                    )
                raise SystemExit(0)

        def open_browser() -> None:
            time.sleep(1)
            webbrowser.open(f"http://127.0.0.1:{args.port}")

        threading.Thread(target=open_browser, daemon=True).start()

    app.config["PORT"] = args.port
    app.run(host="127.0.0.1", port=args.port, debug=True)


def _require_pythonutf8_on_windows() -> None:
    """On Windows, refuse to run without PYTHONUTF8 set, rather than
    silently mis-encoding (or crashing on) non-ASCII content later.

    PYTHONUTF8 must be set before the interpreter starts — Python reads it
    at startup, so there's no way to fix this from within already-running
    code. Without it, open()/Path.write_text()/read_text() calls with no
    explicit encoding= fall back to the Windows system codepage instead of
    UTF-8. The desktop launcher `patr install` creates sets this
    automatically; anyone running `patr` directly from a terminal needs to
    set it themselves, once per session.
    """
    if os.name == "nt" and not os.environ.get("PYTHONUTF8"):
        print(
            "Error: the PYTHONUTF8 environment variable is not set.\n\n"
            "Patr needs this on Windows to correctly save/read non-ASCII\n"
            "text (accented characters, emoji, etc.) — without it, Python\n"
            "falls back to the Windows system codepage instead of UTF-8.\n\n"
            "Set it once for this terminal session, then re-run:\n"
            '  PowerShell:  $env:PYTHONUTF8 = "1"\n'
            "  cmd.exe:     set PYTHONUTF8=1\n\n"
            "(The desktop launcher created by `patr install` sets this\n"
            "automatically for future runs.)"
        )
        raise SystemExit(1)


def main() -> None:
    _require_pythonutf8_on_windows()
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    parser = argparse.ArgumentParser(
        prog="patr", description="Patr — Hugo newsletter tool"
    )
    sub = parser.add_subparsers(dest="command")

    # serve
    serve_parser = sub.add_parser("serve", help="Start the Patr web UI")
    serve_parser.add_argument(
        "--repo", default=".", help="Path to Hugo site root (default: cwd)"
    )
    serve_parser.add_argument(
        "--port", type=int, default=5000, help="Port to listen on (default: 5000)"
    )

    # install
    install_parser = sub.add_parser(
        "install", help="Install Patr layouts/CSS into a Hugo site"
    )
    install_parser.add_argument("--repo", required=True, help="Path to Hugo site root")

    # migrate
    migrate_parser = sub.add_parser(
        "migrate", help="Convert flat .md editions to page bundles"
    )
    migrate_parser.add_argument("--repo", required=True, help="Path to Hugo site root")
    migrate_parser.add_argument(
        "--apply", action="store_true", help="Actually move files (default: dry run)"
    )

    # import-sent-log
    import_sent_log_parser = sub.add_parser(
        "import-sent-log",
        help="Backfill local sent metadata from the Google Sheet's Sent Log",
    )
    import_sent_log_parser.add_argument(
        "--repo", required=True, help="Path to Hugo site root"
    )
    import_sent_log_parser.add_argument(
        "--apply", action="store_true", help="Actually write changes (default: dry run)"
    )

    # prune-backups
    prune_backups_parser = sub.add_parser(
        "prune-backups",
        help="Thin out closely-timestamped edition backups",
    )
    prune_backups_parser.add_argument(
        "--repo", required=True, help="Path to Hugo site root"
    )
    prune_backups_parser.add_argument(
        "--apply", action="store_true", help="Actually delete files (default: dry run)"
    )

    args = parser.parse_args()

    if args.command == "install":
        cmd_install(args)
    elif args.command == "migrate":
        cmd_migrate(args)
    elif args.command == "import-sent-log":
        cmd_import_sent_log(args)
    elif args.command == "prune-backups":
        cmd_prune_backups(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()
