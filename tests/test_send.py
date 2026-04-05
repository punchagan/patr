"""Tests for send_all draft guard and test_send behaviour."""

import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest
from patr import server, state


@pytest.fixture
def repo(tmp_path):
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with server.app.test_client() as c:
        yield c


def make_edition(repo, slug, draft) -> None:
    d = repo / "content" / "newsletter" / slug
    d.mkdir()
    (d / "index.md").write_text(
        textwrap.dedent(f"""\
        ---
        title: Test Edition
        date: 2024-01-01
        draft: {str(draft).lower()}
        ---

        Body.
    """)
    )


def test_send_all_draft_returns_400(client, repo) -> None:
    make_edition(repo, "my-ed", draft=True)
    r = client.post("/api/send/my-ed")
    assert r.status_code == 400
    assert "draft" in r.get_json()["error"].lower()


def test_send_all_non_draft_passes_draft_check(client, repo) -> None:
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text(
        "[params]\n"
    )  # minimal config so load_hugo_config doesn't crash
    # Will fail further in (no sheet_id configured), but must not fail on draft check
    r = client.post("/api/send/my-ed")
    assert "draft" not in (r.get_json().get("error") or "").lower()


def _parse_sse(data: bytes) -> list[dict]:
    """Parse SSE response body into a list of event dicts."""
    events = []
    for chunk in data.decode().split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return events


def test_send_all_streams_sse_on_success(client, repo) -> None:
    """A successful send_all returns a text/event-stream with progress + done events."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email"),
        patch("patr.server.log_sent"),
        patch(
            "patr.server.fetch_contacts",
            return_value=[{"name": "Alice", "email": "alice@example.com"}],
        ),
        patch("patr.server.get_already_sent", return_value=set()),
        patch(
            "patr.server.load_newsletter_config",
            return_value={"name": "My Letter", "sheet_id": "sheet123"},
        ),
        patch(
            "patr.server.load_hugo_config",
            return_value={"baseURL": "https://real-newsletter.com"},
        ),
        patch("patr.server.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com", "name": "Me"
        }
        r = client.post("/api/send/my-ed")

    assert r.status_code == 200
    assert "text/event-stream" in r.content_type
    events = _parse_sse(r.data)
    progress = [e for e in events if e["type"] == "progress"]
    done = next(e for e in events if e["type"] == "done")
    assert len(progress) == 1
    assert progress[0]["sent"] == 1
    assert progress[0]["total"] == 1
    assert done["sent"] == 1
    assert done["failed"] == []


def test_send_all_without_base_url_returns_400(client, repo) -> None:
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text("[params]\n")  # no baseURL
    r = client.post("/api/send/my-ed")
    assert r.status_code == 400
    assert "baseurl" in r.get_json()["error"].lower()


# test_send — no sheet_id configured


def test_test_send_succeeds_without_sheet_id(client, repo) -> None:
    """Test send must return ok=True even when sheet_id is not configured.

    Previously: log_sent(None, ...) raised, the outer except caught it,
    and the route returned 500 — even though the email was delivered.
    """
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email"),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com"
        }
        r = client.post("/api/test-send/my-ed", json={})

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["ok"] is True


def test_test_send_uses_name_email_format(client, repo) -> None:
    """To header should be formatted as 'Name <email>' not bare email."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    captured = {}

    def fake_send(gmail, sender, to, subject, html):
        captured["to"] = to

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=fake_send),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com"
        }
        client.post(
            "/api/test-send/my-ed",
            json={"recipients": [{"name": "Alice", "email": "alice@example.com"}]},
        )

    assert captured["to"] == "Alice <alice@example.com>"


def test_test_send_uses_name_email_format_for_sender(client, repo) -> None:
    """From header should be 'Display Name <email>' using the Google account name."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    captured = {}

    def fake_send(gmail, sender, to, subject, html):
        captured["sender"] = sender

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=fake_send),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com",
            "name": "My Name",
        }
        client.post("/api/test-send/my-ed", json={})

    assert captured["sender"] == "My Name <me@example.com>"


def test_test_send_self_recipient_resolves_to_sender_email(client, repo) -> None:
    """Selecting 'Myself' (__self__) must send to the OAuth email, not the literal string '__self__'."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    captured = {}

    def fake_send(gmail, sender, to, subject, html):
        captured["to"] = to

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=fake_send),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com",
            "name": "My Name",
        }
        client.post(
            "/api/test-send/my-ed",
            json={"recipients": [{"name": "You", "email": "__self__"}]},
        )

    assert captured["to"] == "You <me@example.com>"
