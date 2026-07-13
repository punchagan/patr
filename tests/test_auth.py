"""Tests for get_auth()'s error messages — both "never connected" and
"connection expired" cases should raise a RuntimeError whose message is
already friendly/actionable, so callers can just show str(e) as-is without
needing to special-case or pattern-match the exception."""

from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError
from patr.auth import get_auth


def test_get_auth_raises_friendly_message_when_never_connected() -> None:
    with pytest.raises(RuntimeError, match="Gmail isn't connected"):
        get_auth()


def test_get_auth_raises_friendly_message_when_refresh_fails(
    tmp_path, monkeypatch
) -> None:
    """A dead refresh token (expired via Google's 7-day Testing-mode policy,
    or manually revoked) must not surface Google's raw RefreshError text."""
    from patr import state

    token_file = tmp_path / "token.json"
    token_file.write_text("{}")
    monkeypatch.setattr(state, "TOKEN_FILE", token_file)

    fake_creds = MagicMock()
    fake_creds.valid = False
    fake_creds.expired = True
    fake_creds.refresh_token = "some-refresh-token"
    fake_creds.refresh.side_effect = RefreshError(
        "invalid_grant: Token has been expired or revoked."
    )

    with patch(
        "patr.auth.Credentials.from_authorized_user_file", return_value=fake_creds
    ):
        with pytest.raises(RuntimeError, match="Gmail connection has expired"):
            get_auth()
