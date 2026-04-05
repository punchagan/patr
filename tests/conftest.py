"""Shared pytest fixtures.

IMPORTANT: the autouse fixture below ensures tests never read real credentials
or config from ~/.config/patr/. All tests run with an empty, temporary config
directory so that get_auth(), load_newsletter_config(), and auth_status() cannot
accidentally use real tokens, sheet IDs, or trigger real API calls.
"""

import pytest
from patr import state


@pytest.fixture(autouse=True)
def isolate_patr_config(tmp_path, monkeypatch) -> None:
    """Redirect CONFIG_DIR to a per-test temp directory."""
    config_dir = tmp_path / "patr_config"
    config_dir.mkdir()
    monkeypatch.setattr(state, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(state, "TOKEN_FILE", config_dir / "token.json")
    monkeypatch.setattr(state, "CREDENTIALS_FILE", config_dir / "credentials.json")
    monkeypatch.setattr(state, "SENDER_EMAIL_FILE", config_dir / "sender_email.txt")
