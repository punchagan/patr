"""Tests for `patr squash-drafts` — a one-off, repo-wide cleanup of each
edition's local-only wip: commits, using real git repos (see
git_sync.squash_edition_commits, which this CLI command is a thin wrapper
around for a batch of editions rather than one at publish/send time)."""

import argparse
import subprocess
import textwrap

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


def test_apply_skips_flat_file_editions(tmp_path, monkeypatch, capsys) -> None:
    remote = tmp_path / "remote.git"
    local = tmp_path / "local"
    run(["git", "init", "--bare", str(remote)], cwd=tmp_path)
    local.mkdir()
    run(["git", "init", str(local)], cwd=local)
    run(["git", "config", "user.email", "test@example.com"], cwd=local)
    run(["git", "config", "user.name", "Test"], cwd=local)
    run(["git", "remote", "add", "origin", str(remote)], cwd=local)
    run(["git", "commit", "--allow-empty", "-m", "init"], cwd=local)
    run(["git", "branch", "-M", "main"], cwd=local)
    run(["git", "push", "-u", "origin", "main"], cwd=local)

    (local / "my-ed.md").write_text(
        textwrap.dedent("""\
        ---
        title: Test Edition
        date: 2024-01-01
        draft: true
        ---

        Body.
    """)
    )
    run(["git", "add", "-A"], cwd=local)
    run(["git", "commit", "-m", "wip: my-ed"], cwd=local)

    monkeypatch.setattr(state, "REPO_ROOT", local)
    monkeypatch.setattr(state, "CONTENT_DIR", local)

    args = argparse.Namespace(repo=str(local), apply=True)
    cli.cmd_squash_drafts(args)

    assert len(log_subjects(local)) == 2  # untouched
    out = capsys.readouterr().out
    assert "flat .md edition" in out


def test_no_editions_prints_message(repo, capsys) -> None:
    args = argparse.Namespace(repo=str(repo), apply=True)
    cli.cmd_squash_drafts(args)
    assert "No editions found." in capsys.readouterr().out
