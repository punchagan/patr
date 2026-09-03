"""Tests for resolving the built frontend's hashed asset URLs from Vite's manifest."""

import json

from patr import server, state


def test_index_html_references_hashed_urls_from_manifest():
    """index.html's script/link tags must point at whatever filenames the
    current build actually produced, not a fixed URL — see
    _frontend_assets()'s docstring for why a fixed URL is a caching bug."""
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        html = client.get("/").get_data(as_text=True)

    assets = server._frontend_assets()
    assert f'src="{assets["app_js_url"]}"' in html
    assert f'href="{assets["main_css_url"]}"' in html


def test_frontend_assets_reads_manifest(tmp_path, monkeypatch):
    """_frontend_assets() must resolve URLs from the manifest's recorded
    filenames, not any fixed/guessed name."""
    dist_dir = tmp_path / "static" / "dist"
    manifest_dir = dist_dir / ".vite"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps(
            {
                "main.jsx": {
                    "file": "assets/main-abc123.js",
                    "css": ["assets/main-def456.css"],
                }
            }
        )
    )
    monkeypatch.setattr(state, "PATR_ROOT", tmp_path)

    assets = server._frontend_assets()

    assert assets["app_js_url"] == "/static/dist/assets/main-abc123.js"
    assert assets["main_css_url"] == "/static/dist/assets/main-def456.css"
