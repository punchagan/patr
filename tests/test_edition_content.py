"""Tests for edition content read/write and image upload endpoints."""
import io
import textwrap
import pytest
from patr import state, server


@pytest.fixture
def repo(tmp_path):
    """Set up a minimal fake Hugo repo with one edition."""
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)

    edition = newsletter / "test-edition"
    edition.mkdir()
    (edition / "index.md").write_text(textwrap.dedent("""\
        ---
        title: "Test Edition"
        date: 2024-01-01
        draft: true
        intro: |
          Hello intro.
        ---

        Body content here.
    """))

    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with server.app.test_client() as c:
        yield c


# GET /api/edition/<slug>/content

def test_get_content_returns_fields(client):
    r = client.get("/api/edition/test-edition/content")
    assert r.status_code == 200
    d = r.get_json()
    assert d["title"] == "Test Edition"
    assert "Hello intro." in d["intro"]
    assert d["body"].strip() == "Body content here."


def test_get_content_404(client):
    r = client.get("/api/edition/no-such-edition/content")
    assert r.status_code == 404


# POST /api/edition/<slug>/content

def test_save_content_updates_body(client, repo):
    r = client.post(
        "/api/edition/test-edition/content",
        json={"body": "Updated body."},
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "Updated body." in text


def test_save_content_updates_title(client, repo):
    client.post("/api/edition/test-edition/content", json={"title": "New Title"})
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert 'title: "New Title"' in text


def test_save_content_preserves_other_frontmatter(client, repo):
    client.post("/api/edition/test-edition/content", json={"title": "Changed"})
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "date: 2024-01-01" in text
    assert "draft: true" in text


def test_save_content_multiline_intro(client, repo):
    intro = "Line one.\nLine two.\n  Indented line."
    client.post("/api/edition/test-edition/content", json={"intro": intro})
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "intro: |" in text
    assert "  Line one." in text
    assert "  Line two." in text
    assert "    Indented line." in text  # original 2-space indent + 2-space yaml indent


def test_save_content_clears_intro(client, repo):
    client.post("/api/edition/test-edition/content", json={"intro": ""})
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "intro:" not in text


def test_save_content_404(client):
    r = client.post("/api/edition/missing/content", json={"body": "x"})
    assert r.status_code == 404


# POST /api/edition/<slug>/upload-image

def test_upload_image(client, repo):
    data = {"file": (io.BytesIO(b"fake png data"), "photo.png")}
    r = client.post(
        "/api/edition/test-edition/upload-image",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    d = r.get_json()
    assert d["path"] == "photo.png"
    assert (repo / "content" / "newsletter" / "test-edition" / "photo.png").exists()


def test_upload_image_disallows_bad_extension(client):
    data = {"file": (io.BytesIO(b"evil"), "shell.sh")}
    r = client.post(
        "/api/edition/test-edition/upload-image",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_upload_image_deduplicates_filename(client, repo):
    edition_dir = repo / "content" / "newsletter" / "test-edition"
    (edition_dir / "photo.png").write_bytes(b"existing")
    data = {"file": (io.BytesIO(b"new data"), "photo.png")}
    r = client.post(
        "/api/edition/test-edition/upload-image",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert r.get_json()["path"] != "photo.png"


def test_upload_image_404(client):
    data = {"file": (io.BytesIO(b"data"), "photo.png")}
    r = client.post(
        "/api/edition/missing/upload-image",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 404
