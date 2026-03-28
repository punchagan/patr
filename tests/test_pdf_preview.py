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


def test_pdf_endpoint_returns_pdf(client, edition):
    fake_pdf = b"%PDF-fake"
    mock_html_cls = MagicMock()
    mock_html_cls.return_value.write_pdf.return_value = fake_pdf
    with patch("patr.server.HTML", mock_html_cls):
        r = client.get("/preview/my-ed/email.pdf")
    assert r.status_code == 200
    assert r.content_type == "application/pdf"
    assert r.data == fake_pdf


def test_pdf_endpoint_404_for_missing_edition(client, repo):
    r = client.get("/preview/no-such-edition/email.pdf")
    assert r.status_code == 404


def test_pdf_image_srcs_are_file_not_http(client, edition):
    """Image src attributes passed to WeasyPrint must be file:// not http://
    to avoid WeasyPrint making HTTP requests back to the running Flask server."""
    img_dir = edition.parent.parent.parent / "static" / "images"
    img_dir.mkdir(parents=True)
    (img_dir / "logo.png").write_bytes(b"\x89PNG")
    (edition / "photo.jpg").write_bytes(b"\xff\xd8")
    # Re-write the edition to include both image types
    (edition / "index.md").write_text(
        "---\ntitle: My Edition\ndate: 2024-01-01\ndraft: false\n---\n\n"
        "![photo](photo.jpg)\n\n![logo](/images/logo.png)\n"
    )
    mock_html_cls = MagicMock()
    mock_html_cls.return_value.write_pdf.return_value = b"%PDF"
    with patch("patr.server.HTML", mock_html_cls):
        client.get("/preview/my-ed/email.pdf")
    _, kwargs = mock_html_cls.call_args
    html_string = kwargs.get("string", "")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_string, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        assert not src.startswith("http://127.0.0.1"), f"img src must not be localhost: {src}"
        assert src.startswith("file://"), f"img src must be file://: {src}"


def test_pdf_html_has_no_base_tag(client, edition):
    """<base> tag must be stripped before passing to WeasyPrint."""
    mock_html_cls = MagicMock()
    mock_html_cls.return_value.write_pdf.return_value = b"%PDF"
    with patch("patr.server.HTML", mock_html_cls):
        client.get("/preview/my-ed/email.pdf")
    _, kwargs = mock_html_cls.call_args
    html_string = kwargs.get("string", "")
    assert "<base" not in html_string



def test_pdf_img_width_px_attribute_converted_to_inline_style(client, repo, edition):
    """width="180px" HTML attributes must become style="width:180px".

    WeasyPrint ignores the px suffix on HTML width attributes (not valid HTML),
    so the image renders at full/natural size instead of the intended 180px.
    Converting to an inline style guarantees WeasyPrint applies the constraint.
    """
    footer_dir = repo / "content" / "newsletter" / "footer"
    footer_dir.mkdir()
    (footer_dir / "index.md").write_text(
        '---\ntitle: Footer\n---\n\n<img src="/images/newsletter/upi-qr.png" width="180px">\n'
    )
    img_dir = repo / "static" / "images" / "newsletter"
    img_dir.mkdir(parents=True)
    (img_dir / "upi-qr.png").write_bytes(b"\x89PNG")

    mock_html_cls = MagicMock()
    mock_html_cls.return_value.write_pdf.return_value = b"%PDF"
    with patch("patr.server.HTML", mock_html_cls):
        client.get("/preview/my-ed/email.pdf")

    _, kwargs = mock_html_cls.call_args
    html_string = kwargs.get("string", "")
    assert 'width="180px"' not in html_string, "raw width='180px' must be converted"
    assert "width:180px" in html_string or "width: 180px" in html_string


def test_pdf_footer_root_relative_images_are_absolutified(client, repo, edition):
    """Root-relative footer images (/images/...) must be rewritten to file:// paths.

    Without this, WeasyPrint resolves /images/logo.png as file:///images/logo.png
    which doesn't exist — the image silently disappears from the PDF.
    """
    # Create a footer with a root-relative image
    footer_dir = repo / "content" / "newsletter" / "footer"
    footer_dir.mkdir()
    (footer_dir / "index.md").write_text("---\ntitle: Footer\n---\n\n![logo](/images/newsletter/logo.png)\n")

    # Create the image on disk where Flask would serve it from
    img_dir = repo / "static" / "images" / "newsletter"
    img_dir.mkdir(parents=True)
    (img_dir / "logo.png").write_bytes(b"\x89PNG")

    mock_html_cls = MagicMock()
    mock_html_cls.return_value.write_pdf.return_value = b"%PDF"
    with patch("patr.server.HTML", mock_html_cls):
        client.get("/preview/my-ed/email.pdf")

    _, kwargs = mock_html_cls.call_args
    html_string = kwargs.get("string", "")
    # Root-relative path must NOT appear raw
    assert 'src="/images/' not in html_string
    # Must be replaced with a file:// path pointing into static/
    assert "file://" in html_string
    assert "logo.png" in html_string
