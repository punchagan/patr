"""Tests for edition creation and content-safety edge cases."""
import textwrap
import pytest
import frontmatter as fm
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


def edition_file(repo, slug):
    return repo / "content" / "newsletter" / slug / "index.md"


# New edition creation

def test_new_edition_creates_file(client, repo):
    r = client.post("/api/new-edition", json={"title": "My First Post"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["slug"] == "my-first-post"
    assert edition_file(repo, "my-first-post").exists()


def test_new_edition_file_is_valid_yaml(client, repo):
    client.post("/api/new-edition", json={"title": "My First Post"})
    post = fm.load(edition_file(repo, "my-first-post"))
    assert post["title"] == "My First Post"
    assert post["draft"] is True


def test_new_edition_title_with_quotes_is_valid_yaml(client, repo):
    client.post("/api/new-edition", json={"title": 'It\'s "complicated"'})
    post = fm.load(edition_file(repo, "it-s-complicated"))
    assert post["title"] == 'It\'s "complicated"'


def test_new_edition_title_with_colon_is_valid_yaml(client, repo):
    client.post("/api/new-edition", json={"title": "Part 1: The Beginning"})
    post = fm.load(edition_file(repo, "part-1-the-beginning"))
    assert post["title"] == "Part 1: The Beginning"


def test_new_edition_duplicate_slug_returns_400(client, repo):
    client.post("/api/new-edition", json={"title": "My Post"})
    r = client.post("/api/new-edition", json={"title": "My Post"})
    assert r.status_code == 400
    # Original file untouched
    post = fm.load(edition_file(repo, "my-post"))
    assert post["title"] == "My Post"


def test_new_edition_empty_title_returns_400(client):
    r = client.post("/api/new-edition", json={"title": ""})
    assert r.status_code == 400


# Content save edge cases

@pytest.fixture
def edition(repo):
    d = repo / "content" / "newsletter" / "test-ed"
    d.mkdir()
    (d / "index.md").write_text(textwrap.dedent("""\
        ---
        title: Original Title
        date: 2024-01-01
        draft: true
        intro: |
          Original intro.
        ---

        Original body.
    """))
    return d


def test_save_title_with_quotes(client, edition):
    client.post("/api/edition/test-ed/content", json={"title": 'He said "hello"'})
    post = fm.load(edition / "index.md")
    assert post["title"] == 'He said "hello"'


def test_save_title_with_colon(client, edition):
    client.post("/api/edition/test-ed/content", json={"title": "Chapter 1: Start"})
    post = fm.load(edition / "index.md")
    assert post["title"] == "Chapter 1: Start"


def test_save_body_only_preserves_title_and_intro(client, edition):
    client.post("/api/edition/test-ed/content", json={"body": "New body."})
    post = fm.load(edition / "index.md")
    assert post["title"] == "Original Title"
    assert "Original intro." in post.get("intro", "")
    assert "New body." in post.content


def test_save_body_with_yaml_fence_survives(client, edition):
    # A horizontal rule (---) in the body must not corrupt the frontmatter
    body = "Intro paragraph.\n\n---\n\nAfter the rule."
    client.post("/api/edition/test-ed/content", json={"body": body})
    post = fm.load(edition / "index.md")
    assert "After the rule." in post.content
    assert post["title"] == "Original Title"


# Content save: dangerous inputs

def test_save_empty_title_does_not_wipe_title(client, edition):
    client.post("/api/edition/test-ed/content", json={"title": ""})
    post = fm.load(edition / "index.md")
    assert post["title"] == "Original Title"


def test_save_null_intro_does_not_crash(client, edition):
    r = client.post("/api/edition/test-ed/content", json={"intro": None})
    assert r.status_code == 200
    post = fm.load(edition / "index.md")
    assert "intro" not in post.metadata  # null clears the intro


def test_upload_path_traversal_stays_in_edition_dir(client, repo, edition):
    import io
    data = {"file": (io.BytesIO(b"data"), "../escape.jpg")}
    r = client.post(
        "/api/edition/test-ed/upload-image",
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    # Must NOT have overwritten the newsletter section index
    section_index = repo / "content" / "newsletter" / "index.md"
    assert not section_index.exists()
    # File must land inside the edition directory
    saved_name = r.get_json()["path"]
    assert (edition / saved_name).exists()


# Unicode round-trips

def test_unicode_title_round_trips(client, repo):
    client.post("/api/new-edition", json={"title": "पत्र — Issue 1 🎉"})
    post = fm.load(edition_file(repo, "issue-1"))
    assert post["title"] == "पत्र — Issue 1 🎉"


def test_unicode_body_round_trips(client, edition):
    body = "Héllo wörld. 你好。🌍"
    client.post("/api/edition/test-ed/content", json={"body": body})
    post = fm.load(edition / "index.md")
    assert body in post.content


def test_unicode_intro_round_trips(client, edition):
    intro = "Bonjour à tous. Это тест. 🙏"
    client.post("/api/edition/test-ed/content", json={"intro": intro})
    r = client.get("/api/edition/test-ed/content")
    assert r.get_json()["intro"].strip() == intro


# Toggle draft edge cases

def test_toggle_draft_when_no_draft_field(client, repo):
    d = repo / "content" / "newsletter" / "no-draft"
    d.mkdir()
    (d / "index.md").write_text("---\ntitle: No Draft Field\ndate: 2024-01-01\n---\n\nBody.\n")
    r = client.post("/api/toggle-draft/no-draft")
    assert r.status_code == 200
    # No draft field defaults to False, so toggling gives True
    assert r.get_json()["draft"] is True
    post = fm.load(d / "index.md")
    assert post["draft"] is True
    assert post["title"] == "No Draft Field"
    assert "Body." in post.content
