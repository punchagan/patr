"""Tests for send_all draft guard and test_send behaviour."""

import textwrap
from unittest.mock import MagicMock, patch
import pytest
from patr import state, server


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


def make_edition(repo, slug, draft):
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


def test_send_all_draft_returns_400(client, repo):
    make_edition(repo, "my-ed", draft=True)
    r = client.post("/api/send/my-ed")
    assert r.status_code == 400
    assert "draft" in r.get_json()["error"].lower()


def test_send_all_non_draft_passes_draft_check(client, repo):
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text(
        "[params]\n"
    )  # minimal config so load_hugo_config doesn't crash
    # Will fail further in (no sheet_id configured), but must not fail on draft check
    r = client.post("/api/send/my-ed")
    assert "draft" not in (r.get_json().get("error") or "").lower()


def test_send_all_without_base_url_returns_400(client, repo):
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text("[params]\n")  # no baseURL
    r = client.post("/api/send/my-ed")
    assert r.status_code == 400
    assert "baseurl" in r.get_json()["error"].lower()


# test_send — no sheet_id configured


def test_test_send_succeeds_without_sheet_id(client, repo):
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
