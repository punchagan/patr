"""Tests for `patr import-sent-log` — backfills local `sent: full` metadata
for editions that were sent before the local sent-status feature existed."""

import argparse

import pytest
from patr.cli import cmd_import_sent_log


def import_args(repo, apply=False):
    return argparse.Namespace(repo=str(repo), apply=apply)


@pytest.fixture(autouse=True)
def fake_auth_and_config(monkeypatch):
    """Stub out Google auth and config so no network/creds are needed."""
    from patr import cli

    monkeypatch.setattr(cli, "get_auth", lambda: "fake-creds")
    monkeypatch.setattr(
        cli,
        "load_newsletter_config",
        lambda: {"sheet_id": "fake-sheet-id"},
    )


def make_edition(repo, slug, sent=None):
    hugo_toml = repo / "hugo.toml"
    if not hugo_toml.exists():
        hugo_toml.write_text("baseURL = 'http://example.com'\n")
    content_dir = repo / "content" / "newsletter"
    edition_dir = content_dir / slug
    edition_dir.mkdir(parents=True)
    fm = f"sent: {sent}\n" if sent else ""
    (edition_dir / "index.md").write_text(f"---\ntitle: {slug}\n{fm}---\n\nBody\n")
    return edition_dir / "index.md"


def test_dry_run_reports_without_writing(tmp_path, monkeypatch):
    """Dry run should report which editions would be marked sent, without
    touching any files."""
    f = make_edition(tmp_path, "already-sent")
    from patr import cli

    monkeypatch.setattr(
        cli, "get_all_sent_slugs", lambda sheet_id, creds: {"already-sent"}
    )

    cmd_import_sent_log(import_args(tmp_path, apply=False))

    assert "sent: None" not in f.read_text()
    import frontmatter

    post = frontmatter.load(f)
    assert post.get("sent") is None


def test_apply_marks_matching_editions_full(tmp_path, monkeypatch):
    """--apply should set sent: full on editions found in the sheet's log."""
    f = make_edition(tmp_path, "already-sent")
    make_edition(tmp_path, "never-sent")
    from patr import cli

    monkeypatch.setattr(
        cli, "get_all_sent_slugs", lambda sheet_id, creds: {"already-sent"}
    )

    cmd_import_sent_log(import_args(tmp_path, apply=True))

    import frontmatter

    assert frontmatter.load(f).get("sent") == "full"
    other = tmp_path / "content" / "newsletter" / "never-sent" / "index.md"
    assert frontmatter.load(other).get("sent") is None


def test_apply_does_not_overwrite_existing_sent_status(tmp_path, monkeypatch):
    """An edition already marked 'partial' locally should not be downgraded
    or needlessly rewritten by the backfill."""
    f = make_edition(tmp_path, "partial-edition", sent="partial")
    from patr import cli

    monkeypatch.setattr(
        cli, "get_all_sent_slugs", lambda sheet_id, creds: {"partial-edition"}
    )

    cmd_import_sent_log(import_args(tmp_path, apply=True))

    import frontmatter

    assert frontmatter.load(f).get("sent") == "partial"


def test_missing_sheet_id_errors_without_writing(tmp_path, monkeypatch, capsys):
    """Should print an error and not write anything when sheet_id is unset."""
    make_edition(tmp_path, "already-sent")
    from patr import cli

    monkeypatch.setattr(cli, "load_newsletter_config", dict)

    cmd_import_sent_log(import_args(tmp_path, apply=True))

    out = capsys.readouterr().out
    assert "sheet_id" in out
