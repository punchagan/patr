"""Tests for footer editing via the edition content endpoints."""

import textwrap
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


@pytest.fixture
def footer(repo):
    d = repo / "content" / "newsletter" / "footer"
    d.mkdir()
    (d / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: Footer
        _build:
          render: never
          list: never
        ---

        Unsubscribe [here](https://example.com/unsub).
    """)
    )
    return d


def test_get_footer_content_returns_body(client, footer):
    r = client.get("/api/edition/footer/content")
    assert r.status_code == 200
    assert "Unsubscribe" in r.get_json()["body"]


def test_save_footer_content(client, footer):
    r = client.post("/api/edition/footer/content", json={"body": "New footer content."})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert "New footer content." in (footer / "index.md").read_text()


def test_save_footer_preserves_frontmatter(client, footer):
    r = client.post("/api/edition/footer/content", json={"body": "Updated."})
    assert r.status_code == 200
    text = (footer / "index.md").read_text()
    assert "_build" in text
    assert "render: never" in text


def test_save_footer_ignores_empty_title(client, footer):
    client.post("/api/edition/footer/content", json={"title": "", "body": "Hi."})
    text = (footer / "index.md").read_text()
    assert "title: Footer" in text
