"""Tests for patr install command."""

from pathlib import Path

import pytest
from patr import state
from patr.cli import cmd_install


@pytest.fixture
def hugo_repo(tmp_path, monkeypatch):
    """Minimal Hugo site repo for install tests."""
    repo = tmp_path / "site"
    repo.mkdir()
    (repo / "assets").mkdir()
    monkeypatch.setattr(
        state, "DATA_DIR", Path(__file__).parent.parent / "src/patr/data"
    )
    return repo


def _make_args(repo, add_menu=False, weight="10"):
    class Args:
        pass

    args = Args()
    args.repo = str(repo)
    return args


def test_index_md_uses_configured_name(hugo_repo, monkeypatch) -> None:
    (hugo_repo / "hugo.toml").write_text(
        'baseURL = "https://example.com"\n\n[params.patr]\n  name = "Leaf Dispatch"\n'
    )
    monkeypatch.setattr("builtins.input", lambda _: "n")
    cmd_install(_make_args(hugo_repo))
    text = (hugo_repo / "content/newsletter/_index.md").read_text()
    assert 'title: "Leaf Dispatch"' in text
    assert "Newsletter" not in text


def test_index_md_falls_back_to_newsletter(hugo_repo, monkeypatch) -> None:
    (hugo_repo / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    monkeypatch.setattr("builtins.input", lambda _: "n")
    cmd_install(_make_args(hugo_repo))
    text = (hugo_repo / "content/newsletter/_index.md").read_text()
    assert 'title: "Newsletter"' in text


def test_menu_entry_uses_configured_name(hugo_repo, monkeypatch) -> None:
    (hugo_repo / "hugo.toml").write_text(
        'baseURL = "https://example.com"\n\n[params.patr]\n  name = "Leaf Dispatch"\n'
    )
    inputs = iter(["y", "10"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    cmd_install(_make_args(hugo_repo))
    text = (hugo_repo / "hugo.toml").read_text()
    assert 'name = "Leaf Dispatch"' in text
    assert 'url = "/newsletter/"' in text


def test_menu_entry_falls_back_to_newsletter(hugo_repo, monkeypatch) -> None:
    (hugo_repo / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    inputs = iter(["y", "10"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    cmd_install(_make_args(hugo_repo))
    text = (hugo_repo / "hugo.toml").read_text()
    assert 'name = "Newsletter"' in text
    assert 'url = "/newsletter/"' in text
