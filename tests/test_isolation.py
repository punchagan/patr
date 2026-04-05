"""Tests that verify no test can accidentally read real credentials or config.

These document and enforce the isolation guarantee provided by the
isolate_patr_config autouse fixture in conftest.py.
"""

from pathlib import Path

import pytest
from patr import state


def test_config_dir_is_not_real_home(tmp_path) -> None:
    """CONFIG_DIR must point to the test temp dir, never ~/.config/patr."""
    real_config = Path.home() / ".config" / "patr"
    assert real_config != state.CONFIG_DIR
    assert str(tmp_path) in str(state.CONFIG_DIR)


def test_token_file_is_not_real_home() -> None:
    """TOKEN_FILE must not point at the real token."""
    real_token = Path.home() / ".config" / "patr" / "token.json"
    assert real_token != state.TOKEN_FILE


def test_get_auth_raises_without_real_token() -> None:
    """get_auth() must raise, not silently use real credentials."""
    from patr.auth import get_auth

    with pytest.raises(RuntimeError, match="not_authenticated"):
        get_auth()


def test_load_newsletter_config_reads_from_isolated_config_dir(tmp_path, monkeypatch):
    """load_newsletter_config() reads sheet_id from CONFIG_DIR, not ~/.config/patr."""
    from patr.config import load_newsletter_config

    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    (tmp_path / "hugo.toml").write_text("[params]\n")

    # Nothing in isolated CONFIG_DIR yet — sheet_id must be absent
    cfg = load_newsletter_config()
    assert cfg.get("sheet_id") is None

    # Write a fake config.toml into the isolated CONFIG_DIR
    (state.CONFIG_DIR / "config.toml").write_text('sheet_id = "fake-sheet-123"\n')
    cfg = load_newsletter_config()
    assert cfg["sheet_id"] == "fake-sheet-123"
