"""Tests for the always-on timestamped backup feature."""

import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from patr import server, state

CONTENT = textwrap.dedent("""\
    ---
    title: Test Edition
    date: 2024-01-01
    draft: true
    ---

    Body text here.
""")

SMALL_ADDITION = CONTENT + "One more line.\n"
LARGE_ADDITION = CONTENT + "x" * 600 + "\n"


@pytest.fixture
def backup_root(tmp_path, monkeypatch):
    """Point BACKUPS_DIR and REPO_ROOT at tmp paths for isolation."""
    monkeypatch.setattr(state, "BACKUPS_DIR", tmp_path / "backups")
    monkeypatch.setattr(state, "REPO_ROOT", Path("/home/user/my-newsletter"))
    return tmp_path / "backups"


def edition_dir(backup_root):
    return backup_root / "home-user-my-newsletter" / "my-ed"


def test_first_backup_creates_timestamped_file(backup_root) -> None:
    server.write_backup("my-ed", CONTENT)
    files = list(edition_dir(backup_root).glob("*.md"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == CONTENT


def test_backup_filename_is_iso_timestamp(backup_root) -> None:
    server.write_backup("my-ed", CONTENT)
    files = list(edition_dir(backup_root).glob("*.md"))
    stem = files[0].stem
    # Should parse as %Y%m%dT%H%M%S without raising
    datetime.strptime(stem, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)


def test_recent_small_diff_overwrites_latest(backup_root) -> None:
    """Second backup within threshold + small diff → overwrite, not a new file."""
    server.write_backup("my-ed", CONTENT)
    server.write_backup("my-ed", SMALL_ADDITION)
    files = list(edition_dir(backup_root).glob("*.md"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == SMALL_ADDITION


def test_old_backup_creates_new_file(backup_root) -> None:
    """Backup older than threshold → new file even for small diff."""
    server.write_backup("my-ed", CONTENT)
    ed = edition_dir(backup_root)
    latest = sorted(ed.glob("*.md"))[-1]
    old_ts = (datetime.now(tz=UTC) - timedelta(seconds=600)).strftime("%Y%m%dT%H%M%S")
    latest.rename(ed / f"{old_ts}.md")

    server.write_backup("my-ed", SMALL_ADDITION)
    assert len(list(ed.glob("*.md"))) == 2


def test_large_diff_creates_new_file_even_if_recent(backup_root) -> None:
    """Large diff → new file regardless of age."""
    ed = edition_dir(backup_root)
    ed.mkdir(parents=True)
    recent_ts = (datetime.now(tz=UTC) - timedelta(seconds=10)).strftime("%Y%m%dT%H%M%S")
    (ed / f"{recent_ts}.md").write_text(CONTENT, encoding="utf-8")

    server.write_backup("my-ed", LARGE_ADDITION)
    assert len(list(ed.glob("*.md"))) == 2


def test_backups_accumulate_without_limit(backup_root) -> None:
    """Backups are never deleted — they accumulate indefinitely."""
    ed = edition_dir(backup_root)
    ed.mkdir(parents=True)
    n = 25
    for i in range(n):
        ts = (datetime.now(tz=UTC) - timedelta(seconds=600 + i * 60)).strftime(
            "%Y%m%dT%H%M%S"
        )
        (ed / f"{ts}.md").write_text(CONTENT, encoding="utf-8")

    server.write_backup("my-ed", SMALL_ADDITION)
    assert len(list(ed.glob("*.md"))) == n + 1


def test_backup_dir_created_if_missing(backup_root) -> None:
    assert not (backup_root).exists()
    server.write_backup("my-ed", CONTENT)
    assert edition_dir(backup_root).is_dir()


def test_repo_slug_uses_path_separators(backup_root) -> None:
    """REPO_ROOT path separators become hyphens in backup dir name."""
    server.write_backup("my-ed", CONTENT)
    assert (backup_root / "home-user-my-newsletter").is_dir()
