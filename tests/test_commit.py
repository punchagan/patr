"""Tests for the auto-commit endpoint."""

import subprocess
import textwrap
import time
from unittest.mock import MagicMock, patch

import pytest
from patr import server, state


def run(args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if check:
        assert r.returncode == 0, r.stderr
    return r


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


@pytest.fixture
def real_git_repo(tmp_path):
    """A real git repo (not mocked subprocess) — used to verify the actual
    commit's contents, not just the argv Patr constructs."""
    run(["git", "init"], cwd=tmp_path)
    run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    run(["git", "config", "user.name", "Test"], cwd=tmp_path)
    (tmp_path / "hugo.toml").write_text("[params]\n")
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    run(["git", "add", "-A"], cwd=tmp_path)
    run(["git", "commit", "-m", "init"], cwd=tmp_path)
    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def real_git_client(real_git_repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with patch("patr.server.git_mode", return_value=True):
        with server.app.test_client() as c:
            yield c


def test_commit_does_not_absorb_unrelated_staged_changes(
    real_git_client, real_git_repo
) -> None:
    """git commit with no pathspec commits the whole index, not just what was
    just `git add`ed — if something else is already staged (e.g. the user is
    mid-edit on a Hugo layout in a terminal), an edition's auto-commit must
    not sweep it in."""
    make_edition(real_git_repo, "my-ed")

    unrelated = real_git_repo / "layouts" / "unrelated.html"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("<html>unrelated change</html>")
    run(["git", "add", str(unrelated)], cwd=real_git_repo)

    r = real_git_client.post("/api/edition/my-ed/commit")
    assert r.status_code == 200
    assert r.get_json()["committed"] is True

    committed_files = run(
        ["git", "show", "--name-only", "--format=", "HEAD"], cwd=real_git_repo
    ).stdout.split()
    assert "layouts/unrelated.html" not in committed_files
    assert any("my-ed" in f for f in committed_files)

    # The unrelated change must still be staged, untouched, for the user's
    # own commit later.
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=real_git_repo).stdout
    assert "layouts/unrelated.html" in staged


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
