"""Tests for GET /api/check-deployment/<slug>."""

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


def make_edition(repo, slug) -> None:
    d = repo / "content" / "newsletter" / slug
    d.mkdir()
    (d / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: Test
        date: 2024-01-01
        draft: false
        ---

        Body.
    """)
    )


def git_run(uncommitted="", ahead=False):
    """Return a subprocess.run mock for git status --porcelain=v1 -b -- <edition_dir>."""
    branch_line = (
        "## main...origin/main [ahead 1]" if ahead else "## main...origin/main"
    )
    stdout = branch_line + ("\n" + uncommitted if uncommitted else "") + "\n"
    return MagicMock(return_value=MagicMock(stdout=stdout, returncode=0))


# baseURL not configured


def test_no_base_url_returns_not_live(client, repo) -> None:
    (repo / "hugo.toml").write_text("[params]\n")
    make_edition(repo, "my-ed")
    r = client.get("/api/check-deployment/my-ed")
    assert r.status_code == 200
    d = r.get_json()
    assert d["live"] is False
    assert "reason" in d


def test_example_com_base_url_returns_not_live(client, repo) -> None:
    (repo / "hugo.toml").write_text('baseURL = "https://example.com/"\n')
    make_edition(repo, "my-ed")
    r = client.get("/api/check-deployment/my-ed")
    d = r.get_json()
    assert d["live"] is False


# git status checks (no HTTP — baseURL present but we mock urlopen as unreachable)


def test_uncommitted_changes_reported(client, repo) -> None:
    (repo / "hugo.toml").write_text('baseURL = "https://myblog.com/"\n')
    make_edition(repo, "my-ed")
    with (
        patch(
            "subprocess.run",
            git_run(uncommitted=" M content/newsletter/my-ed/index.md", ahead=False),
        ),
        patch("urllib.request.urlopen", side_effect=Exception("offline")),
    ):
        r = client.get("/api/check-deployment/my-ed")
    d = r.get_json()
    assert d["uncommitted"] is True
    assert d["live"] is False


def test_no_uncommitted_changes(client, repo) -> None:
    (repo / "hugo.toml").write_text('baseURL = "https://myblog.com/"\n')
    make_edition(repo, "my-ed")
    with patch("subprocess.run", git_run(uncommitted="")):
        with patch("urllib.request.urlopen", side_effect=Exception("offline")):
            r = client.get("/api/check-deployment/my-ed")
    d = r.get_json()
    assert d["uncommitted"] is False


def test_unpushed_commits_reported(client, repo) -> None:
    (repo / "hugo.toml").write_text('baseURL = "https://myblog.com/"\n')
    make_edition(repo, "my-ed")
    with patch("subprocess.run", git_run(ahead=True)):
        with patch("urllib.request.urlopen", side_effect=Exception("offline")):
            r = client.get("/api/check-deployment/my-ed")
    d = r.get_json()
    assert d["unpushed"] is True


def test_no_unpushed_commits(client, repo) -> None:
    (repo / "hugo.toml").write_text('baseURL = "https://myblog.com/"\n')
    make_edition(repo, "my-ed")
    with patch("subprocess.run", git_run(ahead=False)):
        with patch("urllib.request.urlopen", side_effect=Exception("offline")):
            r = client.get("/api/check-deployment/my-ed")
    d = r.get_json()
    assert d["unpushed"] is False


# HTTP live check


def test_live_url_reachable(client, repo) -> None:
    (repo / "hugo.toml").write_text('baseURL = "https://myblog.com/"\n')
    make_edition(repo, "my-ed")
    mock_resp = MagicMock()
    mock_resp.status = 200
    with patch("subprocess.run", git_run()):
        with patch("urllib.request.urlopen", return_value=mock_resp):
            r = client.get("/api/check-deployment/my-ed")
    d = r.get_json()
    assert d["live"] is True
    assert "myblog.com" in d["url"]


def test_live_url_unreachable(client, repo) -> None:
    (repo / "hugo.toml").write_text('baseURL = "https://myblog.com/"\n')
    make_edition(repo, "my-ed")
    with (
        patch("subprocess.run", git_run()),
        patch("urllib.request.urlopen", side_effect=Exception("connection refused")),
    ):
        r = client.get("/api/check-deployment/my-ed")
    d = r.get_json()
    assert d["live"] is False


def test_check_deployment_404(client, repo) -> None:
    (repo / "hugo.toml").write_text('baseURL = "https://myblog.com/"\n')
    r = client.get("/api/check-deployment/no-such-edition")
    assert r.status_code == 404
