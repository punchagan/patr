"""Tests for GET /api/edition/<slug>/versions and GET /api/edition/<slug>/versions/<version_id>."""

import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from patr import server, state

CONTENT_V1 = textwrap.dedent("""\
    ---
    title: Test
    date: 2024-01-01
    draft: true
    ---

    First version.
""")

CONTENT_V2 = CONTENT_V1.replace("First version.", "Second version.")


@pytest.fixture
def repo(tmp_path):
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def backup_root(tmp_path, repo, monkeypatch):
    monkeypatch.setattr(state, "BACKUPS_DIR", tmp_path / "backups")
    return tmp_path / "backups"


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with server.app.test_client() as c:
        yield c


def make_edition(repo, slug, content=CONTENT_V1):
    d = repo / "content" / "newsletter" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(content, encoding="utf-8")


def make_backup(backup_root, repo_root, slug, content, age_seconds=10):
    repo_slug = str(repo_root).lstrip("/").replace("/", "-")
    ed = backup_root / repo_slug / slug
    ed.mkdir(parents=True, exist_ok=True)
    ts = (datetime.now(tz=UTC) - timedelta(seconds=age_seconds)).strftime("%Y%m%dT%H%M%S")
    path = ed / f"{ts}.md"
    path.write_text(content, encoding="utf-8")
    return ts


# --- /api/edition/<slug>/versions (list) ---


def test_versions_404_for_unknown_edition(client, repo) -> None:
    r = client.get("/api/edition/no-such/versions")
    assert r.status_code == 404


def test_versions_empty_without_git_or_backups(client, repo, backup_root) -> None:
    make_edition(repo, "my-ed")
    with patch("patr.server.git_mode", return_value=False):
        r = client.get("/api/edition/my-ed/versions")
    assert r.status_code == 200
    assert r.get_json()["versions"] == []


def test_versions_lists_backups_in_git_free_mode(client, repo, backup_root) -> None:
    make_edition(repo, "my-ed")
    ts1 = make_backup(backup_root, repo, "my-ed", CONTENT_V1, age_seconds=120)
    ts2 = make_backup(backup_root, repo, "my-ed", CONTENT_V2, age_seconds=10)
    with patch("patr.server.git_mode", return_value=False):
        r = client.get("/api/edition/my-ed/versions")
    d = r.get_json()
    assert r.status_code == 200
    ids = [v["id"] for v in d["versions"]]
    # Newest first
    assert ids[0] == ts2
    assert ids[1] == ts1
    assert all("label" in v for v in d["versions"])


def test_versions_lists_git_commits_in_git_mode(client, repo, backup_root) -> None:
    make_edition(repo, "my-ed")
    edition_path = repo / "content" / "newsletter" / "my-ed" / "index.md"
    fake_log = f"abc123 1712345678\nwip: save\ndef456 1712340000\nwip: save\n"
    mock_run = MagicMock(return_value=MagicMock(stdout=fake_log, returncode=0))
    with patch("patr.server.git_mode", return_value=True), patch("subprocess.run", mock_run):
        r = client.get("/api/edition/my-ed/versions")
    d = r.get_json()
    assert r.status_code == 200
    assert len(d["versions"]) == 2
    assert d["versions"][0]["id"] == "abc123"
    assert d["versions"][1]["id"] == "def456"


# --- /api/edition/<slug>/versions/<version_id> (fetch content) ---


def test_version_content_404_for_unknown_edition(client, repo) -> None:
    r = client.get("/api/edition/no-such/versions/someid")
    assert r.status_code == 404


def test_version_content_returns_backup_in_git_free_mode(client, repo, backup_root) -> None:
    make_edition(repo, "my-ed")
    ts = make_backup(backup_root, repo, "my-ed", CONTENT_V1, age_seconds=30)
    with patch("patr.server.git_mode", return_value=False):
        r = client.get(f"/api/edition/my-ed/versions/{ts}")
    assert r.status_code == 200
    assert r.get_json()["content"] == CONTENT_V1


def test_version_content_404_for_missing_backup(client, repo, backup_root) -> None:
    make_edition(repo, "my-ed")
    with patch("patr.server.git_mode", return_value=False):
        r = client.get("/api/edition/my-ed/versions/20240101T000000")
    assert r.status_code == 404


def test_version_content_returns_git_content(client, repo, backup_root) -> None:
    make_edition(repo, "my-ed")
    mock_run = MagicMock(return_value=MagicMock(stdout=CONTENT_V1, returncode=0))
    with patch("patr.server.git_mode", return_value=True), patch("subprocess.run", mock_run):
        r = client.get("/api/edition/my-ed/versions/abc123")
    assert r.status_code == 200
    assert r.get_json()["content"] == CONTENT_V1


def test_version_content_404_when_git_show_fails(client, repo, backup_root) -> None:
    make_edition(repo, "my-ed")
    mock_run = MagicMock(return_value=MagicMock(stdout="", returncode=128))
    with patch("patr.server.git_mode", return_value=True), patch("subprocess.run", mock_run):
        r = client.get("/api/edition/my-ed/versions/badref")
    assert r.status_code == 404
