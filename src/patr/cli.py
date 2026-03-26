import argparse
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

import patr.state as state


def cmd_install(args):
    import shutil
    repo = Path(args.repo).resolve()
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
            print("Patr uses page bundles (content/newsletter/slug/index.md).")
            print("Migrate each edition to its own directory before reinstalling.")
            return
        print(f"  Content directory exists and uses page bundles, skipping stub creation.")
    else:
        content_dst.mkdir(parents=True)

        index_md = content_dst / "_index.md"
        index_md.write_text('---\ntitle: "Newsletter"\ndescription: ""\n---\n')
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
        menu_entry = f'\n[[menus.main]]\n  name = "Newsletter"\n  url = "/newsletter/"\n  weight = {weight}\n'
        if "[[menus.main]]" in text and "/newsletter/" in text:
            print("  Menu entry already exists (skipped)")
        else:
            hugo_toml.write_text(text + menu_entry)
            print(f"✓ Menu entry added (weight={weight})")

    print("\nPatr installed. Run: patr serve --repo", repo)
    print("Open the ⚙ settings panel to set your newsletter name and contacts sheet.")


def cmd_serve(args):
    repo_arg = getattr(args, "repo", ".")
    debug_arg = getattr(args, "debug", False)

    state.REPO_ROOT = Path(repo_arg).resolve()
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


def main():
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

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
        cmd_serve(args)
