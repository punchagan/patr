"""Tests for patr install command."""

import subprocess
from pathlib import Path
from unittest.mock import patch

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
    inputs = iter(["n", "y", "10"])  # n=skip git init, y=add menu, weight=10
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    cmd_install(_make_args(hugo_repo))
    text = (hugo_repo / "hugo.toml").read_text()
    assert 'name = "Leaf Dispatch"' in text
    assert 'url = "/newsletter/"' in text


def test_install_hugo_free_mode_prints_message_and_skips_copy(
    tmp_path, monkeypatch, capsys
) -> None:
    """In hugo-free mode, install should print a message and not copy any files."""
    monkeypatch.setattr(
        state, "DATA_DIR", Path(__file__).parent.parent / "src/patr/data"
    )
    cmd_install(_make_args(tmp_path))
    out = capsys.readouterr().out
    assert "Hugo-free mode" in out
    assert not (tmp_path / "layouts").exists()
    assert not (tmp_path / "assets" / "newsletter.css").exists()


def test_git_init_prompt_shown_when_git_available_and_not_a_repo(
    hugo_repo, monkeypatch, capsys
) -> None:
    """When git is installed but dir is not a repo, user is prompted to init."""
    (hugo_repo / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    inputs = iter(["n", "n"])  # n=skip git init, n=skip menu
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    with patch("shutil.which", return_value="/usr/bin/git"):
        cmd_install(_make_args(hugo_repo))
    out = capsys.readouterr().out
    assert "git" in out.lower()
    assert "not a git repo" in out.lower() or "initialize" in out.lower()


def test_git_init_runs_when_user_confirms(hugo_repo, monkeypatch) -> None:
    """When user answers y to git init prompt, git init is run."""
    (hugo_repo / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    inputs = iter(["y", "n"])  # y=init git, n=skip menu
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    with patch("shutil.which", return_value="/usr/bin/git"):
        cmd_install(_make_args(hugo_repo))
    assert (hugo_repo / ".git").is_dir()


def test_git_init_prompt_not_shown_when_already_a_repo(
    hugo_repo, monkeypatch, capsys
) -> None:
    """No git init prompt when the directory is already a git repo."""
    (hugo_repo / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    subprocess.run(["git", "init"], cwd=hugo_repo, capture_output=True, check=True)
    monkeypatch.setattr("builtins.input", lambda _: "n")  # only menu prompt
    with patch("shutil.which", return_value="/usr/bin/git"):
        cmd_install(_make_args(hugo_repo))
    out = capsys.readouterr().out
    assert "initialize" not in out.lower()


def test_git_init_prompt_not_shown_when_git_unavailable(
    hugo_repo, monkeypatch, capsys
) -> None:
    """No git init prompt when git is not installed."""
    (hugo_repo / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    monkeypatch.setattr("builtins.input", lambda _: "n")  # only menu prompt
    with patch("shutil.which", return_value=None):
        cmd_install(_make_args(hugo_repo))
    out = capsys.readouterr().out
    assert "initialize" not in out.lower()


def test_menu_entry_falls_back_to_newsletter(hugo_repo, monkeypatch) -> None:
    (hugo_repo / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    inputs = iter(["n", "y", "10"])  # n=skip git init, y=add menu, weight=10
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    cmd_install(_make_args(hugo_repo))
    text = (hugo_repo / "hugo.toml").read_text()
    assert 'name = "Newsletter"' in text
    assert 'url = "/newsletter/"' in text
