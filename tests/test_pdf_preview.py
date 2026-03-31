"""Tests for /preview/<slug>/email.pdf."""
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


@pytest.fixture
def edition(repo):
    d = repo / "content" / "newsletter" / "my-ed"
    d.mkdir()
    (d / "index.md").write_text(textwrap.dedent("""\
        ---
        title: My Edition
        date: 2024-01-01
        draft: false
        ---

        Hello world.
    """))
    return d


def _mock_playwright(pdf_bytes=b"%PDF-fake"):
    mock_pw = MagicMock()
    mock_pw.return_value.__enter__.return_value.chromium.launch.return_value \
        .new_page.return_value.pdf.return_value = pdf_bytes
    return mock_pw


def test_pdf_endpoint_returns_pdf(client, edition):
    mock_pw = _mock_playwright(b"%PDF-fake")
    with patch("patr.server.sync_playwright", mock_pw):
        r = client.get("/preview/my-ed/email.pdf")
    assert r.status_code == 200
    assert r.content_type == "application/pdf"
    assert r.data == b"%PDF-fake"


def test_pdf_endpoint_404_for_missing_edition(client, repo):
    r = client.get("/preview/no-such-edition/email.pdf")
    assert r.status_code == 404


def test_pdf_navigates_to_email_preview_url(client, edition):
    """Playwright must load the email preview URL so images serve over HTTP."""
    mock_pw = _mock_playwright()
    with patch("patr.server.sync_playwright", mock_pw):
        client.get("/preview/my-ed/email.pdf")
    page = mock_pw.return_value.__enter__.return_value.chromium.launch.return_value.new_page.return_value
    page.goto.assert_called_once()
    url = page.goto.call_args[0][0]
    assert url == "http://127.0.0.1:5000/preview/my-ed/email"


def test_pdf_returns_501_when_no_browser(client, edition):
    """501 if no system browser is available."""
    mock_pw = MagicMock()
    mock_pw.return_value.__enter__.return_value.chromium.launch.side_effect = Exception("not found")
    with patch("patr.server.sync_playwright", mock_pw):
        r = client.get("/preview/my-ed/email.pdf")
    assert r.status_code == 501
