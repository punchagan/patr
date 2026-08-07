"""Tests for cmd_migrate — converting flat .md editions to page bundles."""

import argparse
import textwrap

from patr.cli import cmd_migrate


def migrate_args(repo, apply=False):
    return argparse.Namespace(repo=str(repo), apply=apply)


def test_migrate_hugo_free_moves_flat_file_into_bundle(tmp_path, capsys):
    """In hugo-free mode (no hugo.toml), a flat slug.md directly in the repo
    root must become slug/index.md."""
    (tmp_path / "my-post.md").write_text(
        textwrap.dedent("""\
        ---
        title: My Post
        date: 2024-01-01
        draft: false
        ---

        Body.
    """)
    )
    cmd_migrate(migrate_args(tmp_path, apply=True))

    assert not (tmp_path / "my-post.md").exists()
    assert (tmp_path / "my-post" / "index.md").exists()
    out = capsys.readouterr().out
    assert "Moved 1 edition" in out


def test_migrate_hugo_free_dry_run_does_not_move_files(tmp_path, capsys):
    (tmp_path / "my-post.md").write_text(
        "---\ntitle: My Post\ndate: 2024-01-01\ndraft: false\n---\nBody.\n"
    )
    cmd_migrate(migrate_args(tmp_path, apply=False))

    assert (tmp_path / "my-post.md").exists()
    assert not (tmp_path / "my-post").exists()
    out = capsys.readouterr().out
    assert "Would move 1 edition" in out


def test_migrate_hugo_free_reuses_existing_sibling_image_dir(tmp_path):
    """A flat edition whose images already live in a sibling slug/ directory
    (the hugo-free flat-file image convention) must reuse that directory as
    the new bundle dir rather than treating it as an existing bundle to skip."""
    (tmp_path / "my-post.md").write_text(
        "---\ntitle: My Post\ndate: 2024-01-01\ndraft: false\n---\n![alt](photo.jpg)\n"
    )
    sibling = tmp_path / "my-post"
    sibling.mkdir()
    (sibling / "photo.jpg").write_bytes(b"img")

    cmd_migrate(migrate_args(tmp_path, apply=True))

    assert not (tmp_path / "my-post.md").exists()
    assert (sibling / "index.md").exists()
    assert (sibling / "photo.jpg").exists()


def test_migrate_hugo_free_skips_existing_bundle(tmp_path, capsys):
    (tmp_path / "my-post.md").write_text(
        "---\ntitle: My Post\ndate: 2024-01-01\ndraft: false\n---\nFlat body.\n"
    )
    bundle = tmp_path / "my-post"
    bundle.mkdir()
    (bundle / "index.md").write_text(
        "---\ntitle: My Post\ndate: 2024-01-01\ndraft: false\n---\nBundle body.\n"
    )

    cmd_migrate(migrate_args(tmp_path, apply=True))

    assert (tmp_path / "my-post.md").exists()  # untouched
    assert "Bundle body." in (bundle / "index.md").read_text()  # untouched
    out = capsys.readouterr().out
    assert "skip" in out


def test_migrate_hugo_mode_rewrites_image_refs_and_moves_files(tmp_path):
    (tmp_path / "hugo.toml").write_text('baseURL = "https://example.com/"\n')
    content_dir = tmp_path / "content" / "newsletter"
    content_dir.mkdir(parents=True)
    static_images = tmp_path / "static" / "images" / "newsletter"
    static_images.mkdir(parents=True)
    (static_images / "photo.jpg").write_bytes(b"img")

    (content_dir / "my-post.md").write_text(
        "---\ntitle: My Post\ndate: 2024-01-01\ndraft: false\n---\n"
        "![alt](/images/newsletter/photo.jpg)\n"
    )

    cmd_migrate(migrate_args(tmp_path, apply=True))

    bundle = content_dir / "my-post"
    assert not (content_dir / "my-post.md").exists()
    assert (bundle / "index.md").exists()
    assert (bundle / "photo.jpg").exists()
    assert not (static_images / "photo.jpg").exists()
    text = (bundle / "index.md").read_text()
    assert "/images/newsletter/photo.jpg" not in text
    assert "photo.jpg" in text
