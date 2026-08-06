"""Tests for publish_edition and unpublish_edition git flow.

Uses real git repos (init + a bare "remote") rather than mocking
subprocess.run — the flow now runs a variable number of git commands
(squash_edition_commits + fetch_rebase_and_push, see git_sync.py), so
asserting on a fixed call sequence would be too brittle to internal
implementation details.
"""

import subprocess
import textwrap

import pytest
from patr import server, state


def run(args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if check:
        assert r.returncode == 0, r.stderr
    return r


def log_subjects(repo):
    return run(["git", "log", "--format=%s", "--reverse"], cwd=repo).stdout.splitlines()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    local = tmp_path / "local"
    run(["git", "init", "--bare", str(remote)], cwd=tmp_path)
    local.mkdir()
    run(["git", "init", str(local)], cwd=local)
    run(["git", "config", "user.email", "test@example.com"], cwd=local)
    run(["git", "config", "user.name", "Test"], cwd=local)
    run(["git", "remote", "add", "origin", str(remote)], cwd=local)

    (local / "content" / "newsletter").mkdir(parents=True)
    (local / "hugo.toml").write_text("[params]\n")
    run(["git", "add", "-A"], cwd=local)
    run(["git", "commit", "-m", "init"], cwd=local)
    run(["git", "branch", "-M", "main"], cwd=local)
    run(["git", "push", "-u", "origin", "main"], cwd=local)

    monkeypatch.setattr(state, "REPO_ROOT", local)
    monkeypatch.setattr(state, "CONTENT_DIR", local / "content" / "newsletter")
    return local


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with server.app.test_client() as c:
        yield c


def make_edition(repo, slug, draft=False) -> None:
    d = repo / "content" / "newsletter" / slug
    d.mkdir()
    (d / "index.md").write_text(
        textwrap.dedent(f"""\
        ---
        title: Test Edition
        date: 2024-01-01
        draft: {str(draft).lower()}
        ---

        Body.
    """)
    )
    run(["git", "add", f"content/newsletter/{slug}"], cwd=repo)
    run(["git", "commit", "-m", f"wip: {slug}"], cwd=repo)


# Normal happy path — commit gets made and pushed to the remote


def test_publish_commits_and_pushes(client, repo) -> None:
    make_edition(repo, "my-ed", draft=True)
    r = client.post("/api/publish/my-ed")
    assert r.status_code == 200
    remote_subjects = run(["git", "log", "--format=%s", "origin/main"], cwd=repo).stdout
    assert "Publish: Test Edition" in remote_subjects


def test_publish_squashes_prior_wip_commits(client, repo) -> None:
    """Multiple autosave checkpoints for the edition collapse into the one
    final Publish commit — no wip: trail left on the branch."""
    make_edition(repo, "my-ed", draft=True)
    d = repo / "content" / "newsletter" / "my-ed"
    (d / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: Test Edition
        date: 2024-01-01
        draft: true
        ---

        Body v2.
    """)
    )
    run(["git", "add", "content/newsletter/my-ed"], cwd=repo)
    run(["git", "commit", "-m", "wip: Test Edition"], cwd=repo)

    r = client.post("/api/publish/my-ed")
    assert r.status_code == 200
    subjects = log_subjects(repo)
    assert subjects == ["init", "Publish: Test Edition"]


def test_publish_still_pushes_when_nothing_to_commit(client, repo) -> None:
    """Regression: e.g. retrying after a previous failed push, where the
    frontmatter is already draft: false locally (so the commit step no-ops)
    but the earlier commit still needs to reach the remote."""
    make_edition(repo, "my-ed", draft=False)  # commits locally, unpushed
    r = client.post("/api/publish/my-ed")
    assert r.status_code == 200
    remote_subjects = run(["git", "log", "--format=%s", "origin/main"], cwd=repo).stdout
    assert "wip: my-ed" in remote_subjects


# Publish marks draft editions as live before pushing


def test_publish_marks_draft_as_live(client, repo) -> None:
    make_edition(repo, "my-ed", draft=True)
    r = client.post("/api/publish/my-ed")
    assert r.status_code == 200
    text = (repo / "content" / "newsletter" / "my-ed" / "index.md").read_text()
    assert "draft: false" in text


def test_publish_draft_true_was_previously_rejected(client, repo) -> None:
    """Publish should no longer reject draft editions — it marks them live."""
    make_edition(repo, "my-ed", draft=True)
    r = client.post("/api/publish/my-ed")
    assert r.status_code == 200, "draft editions should now be publishable"


# Unpublish sets draft: true and pushes


def test_unpublish_marks_as_draft_and_pushes(client, repo) -> None:
    make_edition(repo, "my-ed", draft=False)
    r = client.post("/api/unpublish/my-ed")
    assert r.status_code == 200
    text = (repo / "content" / "newsletter" / "my-ed" / "index.md").read_text()
    assert "draft: true" in text
    remote_subjects = run(["git", "log", "--format=%s", "origin/main"], cwd=repo).stdout
    assert "Unpublish: Test Edition" in remote_subjects


def test_unpublish_404_for_missing_edition(client, repo) -> None:
    r = client.post("/api/unpublish/no-such-edition")
    assert r.status_code == 404


# Push failure (e.g. rebase conflict) is surfaced as an error, not silently
# swallowed — Publish/Unpublish are explicit user actions, unlike Send.


def test_publish_reports_error_on_rebase_conflict(client, repo, tmp_path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    run(["git", "init", str(other)], cwd=other)
    run(["git", "config", "user.email", "other@example.com"], cwd=other)
    run(["git", "config", "user.name", "Other"], cwd=other)
    run(["git", "remote", "add", "origin", str(tmp_path / "remote.git")], cwd=other)
    run(["git", "fetch", "origin"], cwd=other)
    # Explicit fetch + checkout onto a branch tracking origin/main, rather
    # than `git clone` — a plain clone's default branch depends on git's
    # (OS-dependent) init.defaultBranch, which can differ from the "main"
    # this repo actually uses, silently committing onto an unrelated branch.
    run(["git", "checkout", "-B", "main", "origin/main"], cwd=other)
    d = other / "content" / "newsletter" / "my-ed"
    d.mkdir(parents=True)
    (d / "index.md").write_text("conflicting remote content")
    run(["git", "add", "-A"], cwd=other)
    run(["git", "commit", "-m", "remote wip"], cwd=other)
    run(["git", "push", "origin", "HEAD:main"], cwd=other)

    make_edition(repo, "my-ed", draft=True)
    (repo / "content" / "newsletter" / "my-ed" / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: Test Edition
        date: 2024-01-01
        draft: true
        ---

        Conflicting local content.
    """)
    )
    run(["git", "add", "content/newsletter/my-ed"], cwd=repo)
    run(["git", "commit", "-m", "wip: Test Edition"], cwd=repo)

    r = client.post("/api/publish/my-ed")
    assert r.status_code == 500
    assert "resolve manually" in r.get_json()["error"]
