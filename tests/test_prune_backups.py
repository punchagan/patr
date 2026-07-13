"""Tests for backup pruning: a "checkpoint compaction" that drops backups
which drifted only a little from the last *kept* backup, while always
keeping the very first and last backup for each edition. Explicitly not a
storage-driven rotation (text files are cheap) — this is about decluttering
the History list with a manual, dry-run-by-default command.
"""

import argparse
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from patr import cli, state
from patr.content import plan_backup_pruning

CONTENT = textwrap.dedent("""\
    ---
    title: Test Edition
    date: 2024-01-01
    draft: true
    ---

    Body text here.
""")


def _write_backup_at(ed_dir: Path, minutes_ago: int, content: str) -> Path:
    ts = (datetime.now(tz=UTC) - timedelta(minutes=minutes_ago)).strftime(
        "%Y%m%dT%H%M%S"
    )
    path = ed_dir / f"{ts}.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def backups_root(tmp_path):
    return tmp_path / "backups"


# ── plan_backup_pruning ──────────────────────────────────────────────────────


def test_single_backup_is_never_pruned(backups_root) -> None:
    ed_dir = backups_root / "my-ed"
    ed_dir.mkdir(parents=True)
    _write_backup_at(ed_dir, 100, CONTENT)

    plan = plan_backup_pruning(backups_root, diff_threshold=500)
    assert plan["my-ed"] == []


def test_small_diff_sequence_prunes_middle_keeps_ends(backups_root) -> None:
    ed_dir = backups_root / "my-ed"
    ed_dir.mkdir(parents=True)
    first = _write_backup_at(ed_dir, 300, CONTENT)
    middle = _write_backup_at(ed_dir, 200, CONTENT + "tiny edit\n")
    last = _write_backup_at(ed_dir, 100, CONTENT + "tiny edit two\n")

    plan = plan_backup_pruning(backups_root, diff_threshold=500)
    assert plan["my-ed"] == [middle]
    assert first not in plan["my-ed"]
    assert last not in plan["my-ed"]


def test_large_diff_keeps_all_as_checkpoints(backups_root) -> None:
    ed_dir = backups_root / "my-ed"
    ed_dir.mkdir(parents=True)
    _write_backup_at(ed_dir, 300, CONTENT)
    _write_backup_at(ed_dir, 200, CONTENT + "x" * 600 + "\n")
    _write_backup_at(ed_dir, 100, CONTENT + "y" * 600 + "z" * 600 + "\n")

    plan = plan_backup_pruning(backups_root, diff_threshold=500)
    assert plan["my-ed"] == []


def test_gradual_drift_accumulates_against_last_kept_not_immediate_predecessor(
    backups_root,
) -> None:
    """Three small steps, each individually under the threshold vs. its
    immediate predecessor, but the third has drifted far enough from the
    last *kept* checkpoint (the first file) that it must survive as a new
    checkpoint — not be silently dropped as part of a "small diff" chain."""
    ed_dir = backups_root / "my-ed"
    ed_dir.mkdir(parents=True)
    step0 = CONTENT
    step1 = step0 + "a" * 50 + "\n"
    step2 = step1 + "b" * 50 + "\n"
    step3 = step2 + "c" * 450 + "\n"  # small vs step2, but big vs step0

    first = _write_backup_at(ed_dir, 400, step0)
    _write_backup_at(ed_dir, 300, step1)
    checkpoint = _write_backup_at(ed_dir, 200, step3)
    last = _write_backup_at(ed_dir, 100, step3 + "final tweak\n")

    plan = plan_backup_pruning(backups_root, diff_threshold=500)
    assert checkpoint not in plan["my-ed"]
    assert first not in plan["my-ed"]
    assert last not in plan["my-ed"]


def test_multiple_editions_pruned_independently(backups_root) -> None:
    a_dir = backups_root / "edition-a"
    b_dir = backups_root / "edition-b"
    a_dir.mkdir(parents=True)
    b_dir.mkdir(parents=True)
    _write_backup_at(a_dir, 300, CONTENT)
    a_mid = _write_backup_at(a_dir, 200, CONTENT + "x\n")
    _write_backup_at(a_dir, 100, CONTENT + "y\n")
    _write_backup_at(b_dir, 100, CONTENT)

    plan = plan_backup_pruning(backups_root, diff_threshold=500)
    assert plan["edition-a"] == [a_mid]
    assert plan["edition-b"] == []


def test_unparseable_filename_is_skipped_not_crashed(backups_root) -> None:
    ed_dir = backups_root / "my-ed"
    ed_dir.mkdir(parents=True)
    (ed_dir / "not-a-timestamp.md").write_text(CONTENT, encoding="utf-8")
    _write_backup_at(ed_dir, 100, CONTENT)

    plan = plan_backup_pruning(backups_root, diff_threshold=500)
    assert plan["my-ed"] == []


# ── cmd_prune_backups CLI ────────────────────────────────────────────────────


@pytest.fixture
def repo_with_backups(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    backups_root = tmp_path / "backups"
    monkeypatch.setattr(state, "BACKUPS_DIR", backups_root)
    monkeypatch.setattr(state, "REPO_ROOT", repo)
    return repo, backups_root


def test_dry_run_reports_without_deleting(repo_with_backups, capsys) -> None:
    repo, backups_root = repo_with_backups
    ed_dir = backups_root / cli.repo_slug() / "my-ed"
    ed_dir.mkdir(parents=True)
    _write_backup_at(ed_dir, 300, CONTENT)
    middle = _write_backup_at(ed_dir, 200, CONTENT + "tiny\n")
    _write_backup_at(ed_dir, 100, CONTENT + "tiny two\n")

    args = argparse.Namespace(repo=str(repo), apply=False)
    cli.cmd_prune_backups(args)

    assert middle.exists()
    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "1 backup" in out


def test_apply_deletes_prunable_backups(repo_with_backups) -> None:
    repo, backups_root = repo_with_backups
    ed_dir = backups_root / cli.repo_slug() / "my-ed"
    ed_dir.mkdir(parents=True)
    first = _write_backup_at(ed_dir, 300, CONTENT)
    middle = _write_backup_at(ed_dir, 200, CONTENT + "tiny\n")
    last = _write_backup_at(ed_dir, 100, CONTENT + "tiny two\n")

    args = argparse.Namespace(repo=str(repo), apply=True)
    cli.cmd_prune_backups(args)

    assert not middle.exists()
    assert first.exists()
    assert last.exists()


def test_no_backups_dir_prints_message_without_crashing(
    repo_with_backups, capsys
) -> None:
    repo, _backups_root = repo_with_backups
    args = argparse.Namespace(repo=str(repo), apply=False)
    cli.cmd_prune_backups(args)
    assert "No backups found" in capsys.readouterr().out
