"""Tests for `patr squash-drafts` — a one-off, repo-wide cleanup of each
edition's local-only wip: commits, using real git repos (see
git_sync.squash_edition_commits, which this CLI command is a thin wrapper
around for a batch of editions rather than one at publish/send time)."""

import argparse
import subprocess
import textwrap
from unittest.mock import patch

import pytest
from patr import cli, state


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
    (local / "content" / "newsletter").mkdir(parents=True)
    run(["git", "init", str(local)], cwd=local)
    run(["git", "config", "user.email", "test@example.com"], cwd=local)
    run(["git", "config", "user.name", "Test"], cwd=local)
    run(["git", "remote", "add", "origin", str(remote)], cwd=local)
    (local / "hugo.toml").write_text("[params]\n")
    run(["git", "add", "-A"], cwd=local)
    run(["git", "commit", "-m", "init"], cwd=local)
    run(["git", "branch", "-M", "main"], cwd=local)
    run(["git", "push", "-u", "origin", "main"], cwd=local)

    monkeypatch.setattr(state, "REPO_ROOT", local)
    monkeypatch.setattr(state, "CONTENT_DIR", local / "content" / "newsletter")
    return local


def make_commit(repo, slug, body, message) -> None:
    d = repo / "content" / "newsletter" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(
        textwrap.dedent(f"""\
        ---
        title: Test Edition
        date: 2024-01-01
        draft: true
        ---

        {body}
    """)
    )
    run(["git", "add", f"content/newsletter/{slug}"], cwd=repo)
    run(["git", "commit", "-m", message], cwd=repo)


def make_multi_edition_commit(repo, slugs_and_bodies, message) -> None:
    paths = []
    for slug, body in slugs_and_bodies:
        d = repo / "content" / "newsletter" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.md").write_text(body)
        paths.append(f"content/newsletter/{slug}")
    run(["git", "add", *paths], cwd=repo)
    run(["git", "commit", "-m", message], cwd=repo)


def test_dry_run_reports_commits_blocking_multiple_editions(repo, capsys) -> None:
    make_commit(repo, "a", "v1", "wip: A")
    make_multi_edition_commit(
        repo, [("a", "shared"), ("b", "b-v1")], "manual: touches a and b"
    )

    args = argparse.Namespace(repo=str(repo), apply=False)
    cli.cmd_squash_drafts(args)

    out = capsys.readouterr().out
    assert "commit(s) touch more than one edition" in out
    assert "manual: touches a and b" in out
    assert "a, b" in out
    assert "--split <sha>" in out


def test_dry_run_reports_none_when_nothing_blocking(repo, capsys) -> None:
    make_commit(repo, "a", "v1", "wip: A")
    make_commit(repo, "a", "v2", "wip: A")

    args = argparse.Namespace(repo=str(repo), apply=False)
    cli.cmd_squash_drafts(args)

    out = capsys.readouterr().out
    assert "touch more than one edition" not in out


def test_split_unblocks_the_edition_for_a_later_dry_run(repo, capsys) -> None:
    make_commit(repo, "a", "v1", "wip: A")
    make_multi_edition_commit(
        repo, [("a", "shared"), ("b", "b-v1")], "manual: touches a and b"
    )
    make_commit(repo, "a", "v3", "wip: A")

    dry_run_args = argparse.Namespace(repo=str(repo), apply=False)
    cli.cmd_squash_drafts(dry_run_args)
    blocking_line = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if "manual: touches a and b" in line
    )
    sha = blocking_line.split()[0]

    split_args = argparse.Namespace(repo=str(repo), apply=False, split=sha)
    cli.cmd_squash_drafts(split_args)
    out = capsys.readouterr().out
    assert f"Split {sha}" in out
    assert "into 2 commit(s)" in out
    assert "(content/newsletter/a)" in out
    assert "(content/newsletter/b)" in out

    cli.cmd_squash_drafts(dry_run_args)
    out = capsys.readouterr().out
    assert "touch more than one edition" not in out
    assert "would squash  a" in out


def test_split_reports_error_for_an_already_pushed_commit(repo, capsys) -> None:
    make_commit(repo, "a", "v1", "wip: A")
    pushed_sha = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    run(["git", "push", "origin", "HEAD:main"], cwd=repo)

    args = argparse.Namespace(repo=str(repo), apply=False, split=pushed_sha)
    cli.cmd_squash_drafts(args)

    out = capsys.readouterr().out
    assert "Error:" in out
    assert "not a local-only" in out


def test_dry_run_reports_without_squashing(repo, capsys) -> None:
    make_commit(repo, "a", "v1", "wip: A")
    make_commit(repo, "b", "v1", "wip: B")
    make_commit(repo, "a", "v2", "wip: A")

    args = argparse.Namespace(repo=str(repo), apply=False)
    cli.cmd_squash_drafts(args)

    assert len(log_subjects(repo)) == 4  # untouched
    out = capsys.readouterr().out
    assert "would squash  a (2 commits → 1)" in out
    assert "Would squash 1 of 2 edition(s)." in out
    assert "Run with --apply to squash." in out


def test_missing_upstream_reports_actionable_error(repo, capsys) -> None:
    """Regression: without an upstream tracking branch,
    squash_edition_commits() silently no-ops for every edition — this
    command must catch that upfront and say so, not just report every
    edition as "nothing to squash" with no explanation."""
    run(["git", "branch", "--unset-upstream"], cwd=repo)
    make_commit(repo, "a", "v1", "wip: A")
    make_commit(repo, "a", "v2", "wip: A")

    args = argparse.Namespace(repo=str(repo), apply=False)
    cli.cmd_squash_drafts(args)

    out = capsys.readouterr().out
    assert "no upstream tracking branch configured" in out
    assert "git branch --set-upstream-to" in out
    # Returns before ever scanning editions — no per-edition report at all.
    assert "would squash" not in out
    assert "skip" not in out


def test_dirty_working_tree_reports_actionable_error(repo, capsys) -> None:
    make_commit(repo, "a", "v1", "wip: A")
    make_commit(repo, "a", "v2", "wip: A")
    (repo / "content" / "newsletter" / "a" / "index.md").write_text("uncommitted")

    args = argparse.Namespace(repo=str(repo), apply=False)
    cli.cmd_squash_drafts(args)

    out = capsys.readouterr().out
    assert "uncommitted changes" in out
    assert "would squash" not in out
    assert "skip" not in out


def test_apply_squashes_each_edition_independently(repo, capsys) -> None:
    make_commit(repo, "a", "v1", "wip: A")
    make_commit(repo, "b", "v1", "wip: B")
    make_commit(repo, "a", "v2", "wip: A")
    make_commit(repo, "b", "v2", "wip: B")

    args = argparse.Namespace(repo=str(repo), apply=True)
    cli.cmd_squash_drafts(args)

    subjects = log_subjects(repo)
    assert subjects.count("wip: A") == 1
    assert subjects.count("wip: B") == 1
    assert len(subjects) == 3  # init + one squashed commit per edition

    out = capsys.readouterr().out
    assert "squashed  a" in out
    assert "squashed  b" in out
    assert "Squashed 2 of 2 edition(s)." in out


def test_apply_stops_loudly_if_tree_becomes_dirty_mid_run(repo, capsys) -> None:
    """Regression: reported by a real user running --apply across many
    editions — once the tree goes dirty partway through (e.g. a repo hook
    creating a stray file — see git_sync's core.hooksPath fix), every
    remaining edition used to silently print "nothing to squash",
    indistinguishable from a legitimate no-op. Must instead stop the loop
    with a clear error, leaving already-squashed editions intact."""
    make_commit(repo, "a", "v1", "wip: A")
    make_commit(repo, "a", "v2", "wip: A")
    make_commit(repo, "b", "v1", "wip: B")
    make_commit(repo, "b", "v2", "wip: B")

    from patr.git_sync import squash_edition_commits as real_squash

    def fake_squash(edition_relpath):
        ok = real_squash(edition_relpath)
        if ok and edition_relpath.endswith("/a"):
            # Simulate something (e.g. a hook) dirtying the tree right
            # after "a" is squashed.
            (repo / "content" / "newsletter" / "a" / "stray.png").write_bytes(b"x")
        return ok

    with patch("patr.cli.squash_edition_commits", side_effect=fake_squash):
        args = argparse.Namespace(repo=str(repo), apply=True)
        cli.cmd_squash_drafts(args)

    out = capsys.readouterr().out
    assert "squashed  a" in out
    assert "squashed  b" not in out
    assert "Error: working tree has uncommitted changes (before b)" in out

    subjects = log_subjects(repo)
    assert subjects.count("wip: A") == 1  # a's squash was not undone
    assert subjects.count("wip: B") == 2  # b was never touched


def test_no_editions_prints_message(repo, capsys) -> None:
    args = argparse.Namespace(repo=str(repo), apply=True)
    cli.cmd_squash_drafts(args)
    assert "No editions found." in capsys.readouterr().out
