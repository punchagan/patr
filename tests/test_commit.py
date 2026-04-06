"""Tests for the auto-commit endpoint."""

import textwrap
import time
from unittest.mock import MagicMock, patch

import pytest
from patr import server, state


@pytest.fixture
def repo(tmp_path):
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    (tmp_path / "hugo.toml").write_text("[params]\n")
    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with patch("patr.server.git_mode", return_value=True):
        with server.app.test_client() as c:
            yield c


def make_edition(repo, slug, title="Test Edition") -> None:
    d = repo / "content" / "newsletter" / slug
    d.mkdir()
    (d / "index.md").write_text(
        textwrap.dedent(f"""\
        ---
        title: {title}
        date: 2024-01-01
        draft: true
        ---

        Body.
    """)
    )


def make_run(responses):
    calls = iter(responses)

    def _run(cmd, **kwargs):
        r = MagicMock()
        r.returncode, r.stdout, r.stderr = next(calls)
        return r

    return _run


SMALL_DIFF = (0, "+one line\n", "")
LARGE_DIFF = (0, "+" + "x" * 600 + "\n", "")
STAGED = (1, "", "")  # returncode 1 = something staged
NOTHING = (0, "", "")  # returncode 0 = nothing staged


def recent_wip(title="Test Edition"):
    """Simulate git log -1 output for a wip commit made moments ago."""
    return (0, f"{int(time.time())}\nwip: {title}", "")


def old_wip(title="Test Edition"):
    """Simulate git log -1 output for a wip commit made 10 minutes ago."""
    return (0, f"{int(time.time()) - 600}\nwip: {title}", "")


def test_commit_404_for_missing_edition(client) -> None:
    r = client.post("/api/edition/no-such/commit")
    assert r.status_code == 404


def test_commit_nothing_staged_is_noop(client, repo) -> None:
    make_edition(repo, "my-ed")
    with patch(
        "subprocess.run",
        side_effect=make_run(
            [
                SMALL_DIFF,  # git diff HEAD
                NOTHING,  # git add (ignored)
                NOTHING,  # git diff --cached → nothing staged
            ]
        ),
    ) as mock_run:
        r = client.post("/api/edition/my-ed/commit")
    assert r.status_code == 200
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert not any("commit" in cmd for cmd in cmds)


def test_commit_small_diff_with_wip_amends(client, repo) -> None:
    make_edition(repo, "my-ed")
    with patch(
        "subprocess.run",
        side_effect=make_run(
            [
                SMALL_DIFF,  # git diff HEAD
                NOTHING,  # git add
                STAGED,  # git diff --cached → staged
                recent_wip(),  # git log -1
                NOTHING,  # git commit --amend
            ]
        ),
    ) as mock_run:
        r = client.post("/api/edition/my-ed/commit")
    assert r.status_code == 200
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert any("--amend" in cmd for cmd in cmds)
    assert not any(("commit" in cmd and "-m" in cmd) for cmd in cmds)


def test_commit_large_diff_creates_new_commit(client, repo) -> None:
    """Large diff skips git log entirely and goes straight to a new commit."""
    make_edition(repo, "my-ed", title="My Edition")
    with patch(
        "subprocess.run",
        side_effect=make_run(
            [
                LARGE_DIFF,  # git diff HEAD
                NOTHING,  # git add
                STAGED,  # git diff --cached → staged
                NOTHING,  # git commit -m (no git log call)
            ]
        ),
    ) as mock_run:
        r = client.post("/api/edition/my-ed/commit")
    assert r.status_code == 200
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert not any("--amend" in cmd for cmd in cmds)
    assert not any("log" in cmd for cmd in cmds)
    assert any(("commit" in cmd and "wip: My Edition" in cmd) for cmd in cmds)


def test_commit_failure_returns_500(client, repo) -> None:
    """If git commit fails, the endpoint should return an error, not ok=True."""
    make_edition(repo, "my-ed")
    with patch(
        "subprocess.run",
        side_effect=make_run(
            [
                SMALL_DIFF,  # git diff HEAD
                NOTHING,  # git add
                STAGED,  # git diff --cached → staged
                recent_wip(),  # git log -1
                (1, "", "error: cannot commit"),  # git commit --amend → FAILS
            ]
        ),
    ):
        r = client.post("/api/edition/my-ed/commit")
    assert r.status_code == 500
    assert "error" in r.get_json()


def test_commit_non_wip_last_commit_creates_new_commit(client, repo) -> None:
    make_edition(repo, "my-ed")
    with patch(
        "subprocess.run",
        side_effect=make_run(
            [
                SMALL_DIFF,  # git diff HEAD
                NOTHING,  # git add
                STAGED,  # git diff --cached → staged
                (
                    0,
                    f"{int(time.time())}\nPublish: Test Edition",
                    "",
                ),  # git log -1 — not a wip commit
                NOTHING,  # git commit -m
            ]
        ),
    ) as mock_run:
        r = client.post("/api/edition/my-ed/commit")
    assert r.status_code == 200
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert not any("--amend" in cmd for cmd in cmds)
    assert any("commit" in cmd for cmd in cmds)


def test_commit_small_diff_old_wip_creates_new_commit(client, repo) -> None:
    """Small diff but wip commit is older than threshold → new commit, not amend."""
    make_edition(repo, "my-ed", title="My Edition")
    with patch(
        "subprocess.run",
        side_effect=make_run(
            [
                SMALL_DIFF,  # git diff HEAD
                NOTHING,  # git add
                STAGED,  # git diff --cached → staged
                old_wip("My Edition"),  # git log -1 — old wip commit
                NOTHING,  # git commit -m
            ]
        ),
    ) as mock_run:
        r = client.post("/api/edition/my-ed/commit")
    assert r.status_code == 200
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert not any("--amend" in cmd for cmd in cmds)
    assert any(("commit" in cmd and "wip: My Edition" in cmd) for cmd in cmds)
