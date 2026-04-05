"""Tests for edition content read/write, toggle-draft, and image upload endpoints."""

import io
import textwrap

import pytest
from patr import server, state


@pytest.fixture
def repo(tmp_path):
    """Set up a minimal fake Hugo repo with one edition."""
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)

    edition = newsletter / "test-edition"
    edition.mkdir()
    (edition / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: "Test Edition"
        date: 2024-01-01
        draft: true
        intro: |
          Hello intro.
        ---

        Body content here.
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


# GET /api/edition/<slug>/content


def test_get_content_returns_fields(client) -> None:
    r = client.get("/api/edition/test-edition/content")
    assert r.status_code == 200
    d = r.get_json()
    assert d["title"] == "Test Edition"
    assert "Hello intro." in d["intro"]
    assert d["body"].strip() == "Body content here."


def test_get_content_returns_mtime(client) -> None:
    r = client.get("/api/edition/test-edition/content")
    assert r.status_code == 200
    assert "mtime" in r.get_json()


def test_get_content_404(client) -> None:
    r = client.get("/api/edition/no-such-edition/content")
    assert r.status_code == 404


# POST /api/edition/<slug>/content


def test_save_returns_updated_mtime(client) -> None:
    r = client.post("/api/edition/test-edition/content", json={"body": "New body."})
    assert r.status_code == 200
    assert "mtime" in r.get_json()


def test_save_with_correct_mtime_succeeds(client, repo) -> None:
    mtime = client.get("/api/edition/test-edition/content").get_json()["mtime"]
    r = client.post(
        "/api/edition/test-edition/content", json={"body": "Updated.", "mtime": mtime}
    )
    assert r.status_code == 200


def test_save_with_stale_mtime_returns_409(client, repo) -> None:
    r = client.post(
        "/api/edition/test-edition/content", json={"body": "Updated.", "mtime": 0}
    )
    assert r.status_code == 409
    d = r.get_json()
    assert "body" in d
    assert "mtime" in d


def test_save_without_mtime_succeeds(client, repo) -> None:
    """No mtime sent — backward-compatible, always saves."""
    r = client.post("/api/edition/test-edition/content", json={"body": "Updated body."})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "Updated body." in text


def test_save_content_updates_title(client, repo) -> None:
    client.post("/api/edition/test-edition/content", json={"title": "New Title"})
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "title: New Title" in text


def test_save_content_preserves_other_frontmatter(client, repo) -> None:
    client.post("/api/edition/test-edition/content", json={"title": "Changed"})
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "date: 2024-01-01" in text
    assert "draft: true" in text


def test_save_content_multiline_intro(client, repo) -> None:
    intro = "Line one.\nLine two.\n  Indented line."
    client.post("/api/edition/test-edition/content", json={"intro": intro})
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "intro: |" in text
    assert "  Line one." in text
    assert "  Line two." in text
    assert "    Indented line." in text  # original 2-space indent + 2-space yaml indent


def test_save_content_clears_intro(client, repo) -> None:
    client.post("/api/edition/test-edition/content", json={"intro": ""})
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "intro:" not in text


def test_save_content_unicode(client, repo) -> None:
    """Unicode characters (e.g. emoji, non-ASCII) must be saved without wiping the file."""
    index = repo / "content" / "newsletter" / "test-edition" / "index.md"
    original = index.read_text()
    body = "Hello 🌍 — café, naïve, 日本語"
    r = client.post("/api/edition/test-edition/content", json={"body": body})
    assert r.status_code == 200
    saved = index.read_text()
    assert body in saved
    assert "title:" in saved  # frontmatter preserved


def test_save_content_404(client) -> None:
    r = client.post("/api/edition/missing/content", json={"body": "x"})
    assert r.status_code == 404


# POST /api/toggle-draft/<slug>


def test_toggle_draft_false_to_true(client, repo) -> None:
    # edition starts as draft: true, toggling should make it false
    r = client.post("/api/toggle-draft/test-edition")
    assert r.status_code == 200
    assert r.get_json()["draft"] is False
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "draft: false" in text


def test_toggle_draft_true_to_false(client, repo) -> None:
    # toggle twice — should end up back at draft: true
    client.post("/api/toggle-draft/test-edition")
    r = client.post("/api/toggle-draft/test-edition")
    assert r.get_json()["draft"] is True
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "draft: true" in text


def test_toggle_draft_preserves_other_frontmatter(client, repo) -> None:
    client.post("/api/toggle-draft/test-edition")
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "title: Test Edition" in text
    assert "date: 2024-01-01" in text


def test_toggle_draft_preserves_body(client, repo) -> None:
    client.post("/api/toggle-draft/test-edition")
    text = (repo / "content" / "newsletter" / "test-edition" / "index.md").read_text()
    assert "Body content here." in text


def test_toggle_draft_404(client) -> None:
    r = client.post("/api/toggle-draft/no-such-edition")
    assert r.status_code == 404


# Content round-trip


def test_intro_with_blank_lines_round_trips(client, repo) -> None:
    intro = "First paragraph.\n\nSecond paragraph."
    client.post("/api/edition/test-edition/content", json={"intro": intro})
    r = client.get("/api/edition/test-edition/content")
    assert r.get_json()["intro"].strip() == intro


# POST /api/edition/<slug>/upload-image


def test_upload_image(client, repo) -> None:
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


def test_upload_image_disallows_bad_extension(client) -> None:
    data = {"file": (io.BytesIO(b"evil"), "shell.sh")}
    r = client.post(
        "/api/edition/test-edition/upload-image",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_upload_image_deduplicates_filename(client, repo) -> None:
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


def test_upload_image_404(client) -> None:
    data = {"file": (io.BytesIO(b"data"), "photo.png")}
    r = client.post(
        "/api/edition/missing/upload-image",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 404


# GET /api/edition/<slug>/check-images


def test_check_images_all_present(client, repo) -> None:
    edition_dir = repo / "content" / "newsletter" / "test-edition"
    (edition_dir / "my photo.png").write_bytes(b"img")
    # Rewrite body to reference the image
    (edition_dir / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: "Test Edition"
        date: 2024-01-01
        draft: true
        ---

        ![A photo](my photo.png)
    """)
    )
    r = client.get("/api/edition/test-edition/check-images")
    assert r.status_code == 200
    assert r.get_json()["missing"] == []


def test_check_images_missing_file(client, repo) -> None:
    edition_dir = repo / "content" / "newsletter" / "test-edition"
    (edition_dir / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: "Test Edition"
        date: 2024-01-01
        draft: true
        ---

        ![Missing](ghost.png)
    """)
    )
    r = client.get("/api/edition/test-edition/check-images")
    assert r.status_code == 200
    assert r.get_json()["missing"] == ["ghost.png"]


def test_check_images_skips_external_and_absolute(client, repo) -> None:
    edition_dir = repo / "content" / "newsletter" / "test-edition"
    (edition_dir / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: "Test Edition"
        date: 2024-01-01
        draft: true
        ---

        ![External](https://example.com/img.png)
        ![Absolute](/images/newsletter/logo.png)
    """)
    )
    r = client.get("/api/edition/test-edition/check-images")
    assert r.status_code == 200
    assert r.get_json()["missing"] == []


def test_check_images_intro_images(client, repo) -> None:
    """Images referenced in the intro frontmatter field are also checked."""
    edition_dir = repo / "content" / "newsletter" / "test-edition"
    (edition_dir / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: "Test Edition"
        date: 2024-01-01
        draft: true
        intro: |
          ![Intro image](intro-missing.png)
        ---

        Body.
    """)
    )
    r = client.get("/api/edition/test-edition/check-images")
    assert r.status_code == 200
    assert "intro-missing.png" in r.get_json()["missing"]


def test_check_images_404(client) -> None:
    r = client.get("/api/edition/no-such-edition/check-images")
    assert r.status_code == 404
