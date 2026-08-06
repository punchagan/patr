"""Tests for git_sync — squashing an edition's local wip commits and
fetch/rebase/push, against real git repos (not mocked subprocess)."""

import subprocess
from unittest.mock import patch

import pytest
from patr import state
from patr.git_sync import (
    fetch_rebase_and_push,
    squash_edition_commits,
    squashable_commit_count,
)


def run(args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if check:
        assert r.returncode == 0, r.stderr
    return r


def log_subjects(repo):
    return run(["git", "log", "--format=%s", "--reverse"], cwd=repo).stdout.splitlines()


def commit_edition(repo, slug, body, message):
    d = repo / "content" / "newsletter" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(body)
    run(["git", "add", f"content/newsletter/{slug}"], cwd=repo)
    run(["git", "commit", "-m", message], cwd=repo)


def commit_multiple_editions(repo, slugs_and_bodies, message):
    """Commit changes to several editions' directories in one commit —
    something Patr's own auto-commit never does (it always `git add`s
    exactly one edition's directory), but possible via manual git usage."""
    paths = []
    for slug, body in slugs_and_bodies:
        d = repo / "content" / "newsletter" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.md").write_text(body)
        paths.append(f"content/newsletter/{slug}")
    run(["git", "add", *paths], cwd=repo)
    run(["git", "commit", "-m", message], cwd=repo)


@pytest.fixture
def remote(tmp_path):
    r = tmp_path / "remote.git"
    run(["git", "init", "--bare", str(r)], cwd=tmp_path)
    return r


def _init_local(path, remote, monkeypatch, push_upstream=True):
    path.mkdir()
    run(["git", "init", str(path)], cwd=path)
    run(["git", "config", "user.email", "test@example.com"], cwd=path)
    run(["git", "config", "user.name", "Test"], cwd=path)
    run(["git", "remote", "add", "origin", str(remote)], cwd=path)
    (path / "README.md").write_text("init\n")
    run(["git", "add", "README.md"], cwd=path)
    run(["git", "commit", "-m", "init"], cwd=path)
    run(["git", "branch", "-M", "main"], cwd=path)
    if push_upstream:
        run(["git", "push", "-u", "origin", "main"], cwd=path)
    monkeypatch.setattr(state, "REPO_ROOT", path)
    return path


@pytest.fixture
def repo(tmp_path, remote, monkeypatch):
    return _init_local(tmp_path / "local", remote, monkeypatch)


# squash_edition_commits


def test_squash_collapses_one_editions_commits(repo) -> None:
    commit_edition(repo, "a", "v1", "wip: A")
    commit_edition(repo, "b", "v1", "wip: B")
    commit_edition(repo, "a", "v2", "wip: A")
    commit_edition(repo, "b", "v2", "wip: B")
    commit_edition(repo, "a", "v3", "Publish: A")

    assert squash_edition_commits("content/newsletter/a") is True

    assert log_subjects(repo) == ["init", "wip: B", "wip: B", "Publish: A"]
    assert (repo / "content" / "newsletter" / "a" / "index.md").read_text() == "v3"
    assert (repo / "content" / "newsletter" / "b" / "index.md").read_text() == "v2"


def test_squash_keeps_final_matching_commits_message(repo) -> None:
    commit_edition(repo, "a", "v1", "wip: A")
    commit_edition(repo, "a", "v2", "wip: A checkpoint 2")

    assert squash_edition_commits("content/newsletter/a") is True
    assert log_subjects(repo) == ["init", "wip: A checkpoint 2"]


def test_squash_noop_without_upstream(tmp_path, remote, monkeypatch) -> None:
    local = _init_local(tmp_path / "local", remote, monkeypatch, push_upstream=False)
    commit_edition(local, "a", "v1", "wip: A")
    commit_edition(local, "a", "v2", "wip: A")

    assert squash_edition_commits("content/newsletter/a") is False
    assert len(log_subjects(local)) == 3  # nothing collapsed


def test_squash_noop_with_fewer_than_two_matching_commits(repo) -> None:
    commit_edition(repo, "a", "v1", "wip: A")
    commit_edition(repo, "b", "v1", "wip: B")

    assert squash_edition_commits("content/newsletter/a") is False
    assert len(log_subjects(repo)) == 3


def test_squash_noop_with_dirty_working_tree(repo) -> None:
    commit_edition(repo, "a", "v1", "wip: A")
    commit_edition(repo, "a", "v2", "wip: A")
    (repo / "content" / "newsletter" / "a" / "index.md").write_text("uncommitted")

    assert squash_edition_commits("content/newsletter/a") is False
    assert len(log_subjects(repo)) == 3


def test_squash_noop_when_edition_created_and_deleted_before_ever_pushed(repo) -> None:
    """Create + modify + delete, all unpushed, nets to zero diff from the
    upstream base — nothing to commit, so squash safely no-ops rather than
    force an empty commit. (Unreachable via the actual server routes, which
    only ever call squash for editions confirmed to still exist — this just
    documents the module's behavior in isolation.)"""
    commit_edition(repo, "a", "v1", "wip: A")
    commit_edition(repo, "a", "v2", "wip: A")
    run(["git", "rm", "-r", "content/newsletter/a"], cwd=repo)
    run(["git", "commit", "-m", "Delete A"], cwd=repo)

    assert squash_edition_commits("content/newsletter/a") is False
    assert len(log_subjects(repo)) == 4  # original history untouched


def test_squash_refuses_when_a_commit_touches_multiple_editions(repo) -> None:
    """A commit touching edition A *and* edition B (e.g. a manual
    `git add -A`, never produced by Patr's own auto-commit) must block
    squashing A outright — not get silently dropped (losing its B changes)
    or replayed onto the wrong pre-image (risking a conflict or, worse,
    resolving to the wrong content without any error)."""
    commit_edition(repo, "a", "v1", "wip: A")
    commit_multiple_editions(
        repo, [("a", "v2-shared"), ("b", "b-v1")], "wip: touches a and b"
    )
    commit_edition(repo, "a", "v3", "wip: A")

    assert squash_edition_commits("content/newsletter/a") is False
    # Nothing rewritten — including B's content, which a naive "exclude
    # mixed commits from mine, replay as others" fix would have corrupted.
    assert len(log_subjects(repo)) == 4
    assert (repo / "content" / "newsletter" / "a" / "index.md").read_text() == "v3"
    assert (repo / "content" / "newsletter" / "b" / "index.md").read_text() == "b-v1"


def test_squash_still_works_for_editions_the_mixed_commit_does_not_touch(repo) -> None:
    """The mixed commit only blocks squashing for the edition(s) it
    actually touches — an unrelated edition's own squash proceeds fine."""
    commit_edition(repo, "a", "v1", "wip: A")
    commit_multiple_editions(
        repo, [("a", "v2-shared"), ("b", "b-v1")], "wip: touches a and b"
    )
    commit_edition(repo, "c", "c-v1", "wip: C")
    commit_edition(repo, "c", "c-v2", "wip: C")

    assert squash_edition_commits("content/newsletter/c") is True
    subjects = log_subjects(repo)
    assert "wip: touches a and b" in subjects  # untouched
    assert subjects.count("wip: C") == 1


# squashable_commit_count — read-only preview, must not mutate anything


def test_squashable_commit_count_matches_and_does_not_mutate(repo) -> None:
    commit_edition(repo, "a", "v1", "wip: A")
    commit_edition(repo, "b", "v1", "wip: B")
    commit_edition(repo, "a", "v2", "wip: A")

    assert squashable_commit_count("content/newsletter/a") == 2
    assert squashable_commit_count("content/newsletter/b") == 1
    assert len(log_subjects(repo)) == 4  # untouched — this is a preview only


def test_squashable_commit_count_reports_zero_when_blocked_by_mixed_commit(
    repo,
) -> None:
    """Preview must agree with what squash_edition_commits() would actually
    do — reporting a nonzero count here when the real squash would refuse
    outright would be misleading."""
    commit_edition(repo, "a", "v1", "wip: A")
    commit_multiple_editions(
        repo, [("a", "v2-shared"), ("b", "b-v1")], "wip: touches a and b"
    )
    commit_edition(repo, "a", "v3", "wip: A")

    assert squashable_commit_count("content/newsletter/a") == 0


def test_squashable_commit_count_uses_a_bounded_number_of_git_calls(repo) -> None:
    """Regression: the original implementation ran one `git diff-tree` per
    local-only commit, so a repo with thousands of unpushed commits made
    even the dry-run report (patr squash-drafts) take forever. Assert the
    number of subprocess calls stays small regardless of commit count,
    rather than only checking wall-clock time (flaky under CI load)."""
    for i in range(60):
        commit_edition(repo, "a", f"v{i}", "wip: A")

    real_run = subprocess.run
    calls = []

    def counting_run(*args, **kwargs):
        calls.append(args)
        return real_run(*args, **kwargs)

    with patch("patr.git_sync.subprocess.run", side_effect=counting_run):
        count = squashable_commit_count("content/newsletter/a")

    assert count == 60
    # A handful of calls (upstream lookup, status, rev-list, one log
    # --name-only dump) — not one per commit.
    assert len(calls) < 10, f"expected O(1) git calls, got {len(calls)}"


# fetch_rebase_and_push


def test_push_succeeds_when_remote_unchanged(repo) -> None:
    commit_edition(repo, "a", "v1", "wip: A")
    ok, error = fetch_rebase_and_push()
    assert ok is True
    assert error == ""
    remote_log = run(
        ["git", "log", "--format=%s", "origin/main"], cwd=repo
    ).stdout.splitlines()
    assert "wip: A" in remote_log


def test_push_rebases_on_top_of_remote_changes(tmp_path, remote, monkeypatch) -> None:
    other = _init_local(tmp_path / "other", remote, monkeypatch)
    commit_edition(other, "b", "v1", "wip: B")
    fetch_rebase_and_push()  # pushes from `other`, becomes state.REPO_ROOT temporarily

    local = _init_local(tmp_path / "local2", remote, monkeypatch, push_upstream=False)
    run(["git", "fetch", "origin"], cwd=local)
    run(["git", "checkout", "-B", "main", "origin/main"], cwd=local)
    run(["git", "branch", "--set-upstream-to=origin/main", "main"], cwd=local)
    commit_edition(local, "a", "v1", "wip: A")

    monkeypatch.setattr(state, "REPO_ROOT", local)
    ok, error = fetch_rebase_and_push()
    assert ok is True, error
    subjects = run(["git", "log", "--format=%s", "origin/main"], cwd=local).stdout
    assert "wip: A" in subjects
    assert "wip: B" in subjects


def test_push_conflict_aborts_and_reports_error(tmp_path, remote, monkeypatch) -> None:
    other = _init_local(tmp_path / "other", remote, monkeypatch)
    commit_edition(other, "a", "conflicting-remote-version", "wip: A remote")
    monkeypatch.setattr(state, "REPO_ROOT", other)
    fetch_rebase_and_push()

    local = _init_local(tmp_path / "local2", remote, monkeypatch, push_upstream=False)
    run(["git", "fetch", "origin"], cwd=local)
    run(["git", "checkout", "-B", "main", "origin/main~1"], cwd=local)
    run(["git", "branch", "--set-upstream-to=origin/main", "main"], cwd=local)
    commit_edition(local, "a", "conflicting-local-version", "wip: A local")
    local_head_before = run(["git", "rev-parse", "HEAD"], cwd=local).stdout.strip()

    monkeypatch.setattr(state, "REPO_ROOT", local)
    ok, error = fetch_rebase_and_push()

    assert ok is False
    assert "resolve manually" in error
    # Nothing lost, no rebase left in progress.
    assert (
        run(["git", "rev-parse", "HEAD"], cwd=local).stdout.strip() == local_head_before
    )
    status = run(["git", "status", "--porcelain=2", "--branch"], cwd=local).stdout
    assert "rebase" not in status.lower()
