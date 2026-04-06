"""Tests for cli.py — cmd_serve CONTENT_DIR and guard logic."""

import argparse

import pytest
from patr import state
from patr.cli import cmd_serve


def serve_args(repo, port=5000):
    return argparse.Namespace(repo=str(repo), port=port)


@pytest.fixture(autouse=True)
def no_flask(monkeypatch):
    """Prevent Flask from actually starting."""
    from patr import server

    monkeypatch.setattr(server.app, "run", lambda **kw: None)


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    """Prevent browser open and port check side effects."""
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")


def test_cmd_serve_hugo_free_sets_content_dir_to_repo_root(tmp_path, monkeypatch):
    """In hugo-free mode, CONTENT_DIR should be REPO_ROOT directly."""
    cmd_serve(serve_args(tmp_path))
    assert tmp_path == state.CONTENT_DIR


def test_cmd_serve_hugo_mode_sets_content_dir_to_newsletter(tmp_path, monkeypatch):
    """In Hugo mode, CONTENT_DIR should be REPO_ROOT/content/newsletter."""
    (tmp_path / "hugo.toml").write_text("[params]\n")
    (tmp_path / "layouts" / "newsletter").mkdir(parents=True)
    cmd_serve(serve_args(tmp_path))
    assert tmp_path / "content" / "newsletter" == state.CONTENT_DIR


def test_cmd_serve_hugo_free_does_not_require_hugo_toml(tmp_path):
    """cmd_serve must not raise SystemExit when hugo.toml is absent."""
    cmd_serve(serve_args(tmp_path))  # should not raise


def test_cmd_serve_hugo_mode_requires_layouts(tmp_path):
    """In Hugo mode, missing layouts should exit with code 1."""
    (tmp_path / "hugo.toml").write_text("[params]\n")
    with pytest.raises(SystemExit) as exc:
        cmd_serve(serve_args(tmp_path))
    assert exc.value.code == 1
