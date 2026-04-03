import argparse
import os
import re
import shutil
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None

import patr.state as state
from patr.config import load_newsletter_config


def cmd_install(args):
    repo = Path(args.repo).resolve()
    state.REPO_ROOT = repo
    if not (repo / "hugo.toml").exists() and not (repo / "config.toml").exists():
        print(f"Error: {repo} doesn't look like a Hugo site (no hugo.toml found).")
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
            f for f in content_dst.glob("*.md")
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
        print(f"  Content directory exists and uses page bundles, skipping stub creation.")
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
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])
        except Exception:
            desktop = Path.home()
        bat = desktop / f"start-patr-{repo.name}.bat"
        bat.write_text(f'@echo off\npatr serve --repo "{repo}"\npause\n')
        print(f"✓ Created launcher on Desktop → {bat}")

    print("\nPatr installed. Run: patr serve --repo", repo)
    print("Open the ⚙ settings panel to set your newsletter name and contacts sheet.")


def cmd_migrate(args):
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
            new_text = re.sub(r'/images/newsletter/([^\s)"\']+)', r'\1', text)
            (bundle_dir / "index.md").write_text(new_text)
            f.unlink()
            for img in images_to_move:
                shutil.move(str(static_images_dir / img), str(bundle_dir / img))

        editions_moved += 1

    print(f"\n{'Would move' if dry_run else 'Moved'} {editions_moved} edition(s), skipped {skipped}.")
    if dry_run and editions_moved:
        print("Run with --apply to move files.")


def cmd_serve(args):
    state.REPO_ROOT = Path(args.repo).resolve()
    state.CONTENT_DIR = state.REPO_ROOT / "content" / "newsletter"

    if not (state.REPO_ROOT / "hugo.toml").exists() and not (state.REPO_ROOT / "config.toml").exists():
        print(f"Error: {state.REPO_ROOT} doesn't look like a Hugo site (no hugo.toml found).")
        raise SystemExit(1)

    if not (state.REPO_ROOT / "layouts" / "newsletter").exists():
        print(f"Error: Patr layouts not found in {state.REPO_ROOT}.")
        print(f"Run first: patr install --repo {state.REPO_ROOT}")
        raise SystemExit(1)

    # Import server after state is configured
    from patr.server import app

    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", args.port))
        except OSError:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/editions", timeout=1)
                print(f"Patr is already running at http://127.0.0.1:{args.port}")
            except Exception:
                print(f"Error: port {args.port} is already in use by another process.")
            raise SystemExit(0)

    # Only open the browser on initial start, not on reloader restarts
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        def open_browser():
            time.sleep(1)
            webbrowser.open(f"http://127.0.0.1:{args.port}")

        threading.Thread(target=open_browser, daemon=True).start()

    app.config["PORT"] = args.port
    app.run(host="127.0.0.1", port=args.port, debug=True)


def main():
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    parser = argparse.ArgumentParser(prog="patr", description="Patr — Hugo newsletter tool")
    sub = parser.add_subparsers(dest="command")

    # serve
    serve_parser = sub.add_parser("serve", help="Start the Patr web UI")
    serve_parser.add_argument("--repo", default=".", help="Path to Hugo site root (default: cwd)")
    serve_parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")

    # install
    install_parser = sub.add_parser("install", help="Install Patr layouts/CSS into a Hugo site")
    install_parser.add_argument("--repo", required=True, help="Path to Hugo site root")

    # migrate
    migrate_parser = sub.add_parser("migrate", help="Convert flat .md editions to page bundles")
    migrate_parser.add_argument("--repo", required=True, help="Path to Hugo site root")
    migrate_parser.add_argument("--apply", action="store_true", help="Actually move files (default: dry run)")

    args = parser.parse_args()

    if args.command == "install":
        cmd_install(args)
    elif args.command == "migrate":
        cmd_migrate(args)
    else:
        # Default to serve (also handles no subcommand for backwards compat)
        cmd_serve(args)
