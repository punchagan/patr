"""Tests for GET /api/edition/<slug>/sent-log."""

import textwrap
from unittest.mock import MagicMock, patch

import pytest
from patr import server, state


@pytest.fixture
def repo(tmp_path):
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    edition = newsletter / "my-ed"
    edition.mkdir()
    (edition / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: Test Edition
        date: 2024-01-01
        draft: false
        ---

        Body.
    """)
    )
    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with server.app.test_client() as c:
        yield c


def test_sent_log_404_for_unknown_edition(client) -> None:
    r = client.get("/api/edition/no-such/sent-log")
    assert r.status_code == 404


def test_sent_log_400_without_sheet_id(client) -> None:
    with patch("patr.server.load_newsletter_config", return_value={}):
        r = client.get("/api/edition/my-ed/sent-log")
    assert r.status_code == 400
    assert "sheet_id" in r.get_json()["error"].lower()


def test_sent_log_returns_entries(client) -> None:
    with (
        patch(
            "patr.server.load_newsletter_config",
            return_value={"sheet_id": "sheet123"},
        ),
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch(
            "patr.server.get_sent_log_entries",
            return_value=[{"email": "alice@example.com", "sent_at": "2024-01-01"}],
        ) as mock_entries,
    ):
        r = client.get("/api/edition/my-ed/sent-log")
    assert r.status_code == 200
    assert r.get_json() == {
        "entries": [{"email": "alice@example.com", "sent_at": "2024-01-01"}]
    }
    mock_entries.assert_called_once_with(
        "sheet123", mock_entries.call_args[0][1], "my-ed"
    )


def test_sent_log_500_on_error(client) -> None:
    with (
        patch(
            "patr.server.load_newsletter_config",
            return_value={"sheet_id": "sheet123"},
        ),
        patch("patr.server.get_auth", side_effect=RuntimeError("not_authenticated")),
    ):
        r = client.get("/api/edition/my-ed/sent-log")
    assert r.status_code == 500
