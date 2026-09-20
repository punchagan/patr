"""Pruning images that nothing in an edition refers to.

Only editions that are sent or published are pruned: an unsent draft is work
in progress, so an image with no reference yet may simply not be used yet.
"Referenced" is decided conservatively — an image's path appearing anywhere in
index.md (body, intro, other front matter) protects it — because wrongly
keeping a file costs nothing, and wrongly removing one loses work. Applying
moves files into the backups folder rather than deleting them.
"""

import argparse
from pathlib import Path

import pytest
from patr import cli, state
from patr.content import plan_image_pruning, repo_slug


@pytest.fixture
def repo(tmp_path, monkeypatch):
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    (tmp_path / "hugo.toml").write_text('baseURL = "https://example.com"\n')
    monkeypatch.setattr(state, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(state, "CONTENT_DIR", newsletter)
    monkeypatch.setattr(state, "BACKUPS_DIR", tmp_path / "backups")
    return newsletter


def make_edition(
    repo: Path,
    slug: str,
    body: str = "Body.",
    files=(),
    draft: bool = False,
    sent: str | None = None,
    intro: str = "",
    extra_front_matter: str = "",
) -> Path:
    bundle = repo / slug
    bundle.mkdir()
    front = f"title: {slug}\ndate: 2024-01-01\ndraft: {str(draft).lower()}\n"
    if sent:
        front += f"sent: {sent}\n"
    if intro:
        front += f'intro: "{intro}"\n'
    front += extra_front_matter
    (bundle / "index.md").write_text(f"---\n{front}---\n\n{body}\n", encoding="utf-8")
    for name in files:
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"IMG")
    return bundle


def planned(repo, slug):
    plan, _ = plan_image_pruning()
    return sorted(p.relative_to(repo / slug).as_posix() for p in plan.get(slug, []))


# ── which editions are considered ────────────────────────────────────────────


def test_unreferenced_image_in_a_published_edition_is_planned(repo) -> None:
    make_edition(repo, "ed", body="![kept](a.png)", files=["a.png", "b.png"])
    assert planned(repo, "ed") == ["b.png"]


def test_drafts_are_never_touched(repo) -> None:
    make_edition(repo, "wip", draft=True, files=["unused-yet.png"])
    plan, skipped = plan_image_pruning()
    assert "wip" not in plan
    assert "wip" in skipped


@pytest.mark.parametrize("sent", ["full", "partial"])
def test_a_sent_edition_counts_even_if_still_marked_draft(repo, sent) -> None:
    """In email-only mode nothing ever un-drafts an edition; sent is the signal."""
    make_edition(repo, "ed", draft=True, sent=sent, files=["b.png"])
    assert planned(repo, "ed") == ["b.png"]


def test_footer_and_index_directories_are_ignored(repo) -> None:
    make_edition(repo, "footer", files=["qr.png"])
    (repo / "_index.md").write_text("---\ntitle: N\n---\n")
    plan, skipped = plan_image_pruning()
    assert plan == {} and "footer" not in skipped


def test_an_edition_with_unreadable_front_matter_is_skipped_not_fatal(repo) -> None:
    bundle = repo / "broken"
    bundle.mkdir()
    (bundle / "index.md").write_text("---\ntitle: [unclosed\n---\n\nBody\n")
    (bundle / "a.png").write_bytes(b"IMG")
    plan, skipped = plan_image_pruning()
    assert "broken" not in plan
    assert "broken" in skipped


# ── what counts as a reference ───────────────────────────────────────────────


def test_an_image_linked_but_not_embedded_is_kept(repo) -> None:
    make_edition(repo, "ed", body="[full size](big.png)", files=["big.png"])
    assert planned(repo, "ed") == []


def test_an_image_in_raw_html_is_kept(repo) -> None:
    make_edition(repo, "ed", body='<img src="raw.png" width="50">', files=["raw.png"])
    assert planned(repo, "ed") == []


def test_an_image_used_only_in_the_intro_is_kept(repo) -> None:
    make_edition(repo, "ed", intro="![x](intro.png)", files=["intro.png"])
    assert planned(repo, "ed") == []


def test_an_image_named_in_other_front_matter_is_kept(repo) -> None:
    make_edition(
        repo, "ed", files=["cover.jpg"], extra_front_matter="cover: cover.jpg\n"
    )
    assert planned(repo, "ed") == []


def test_a_url_encoded_reference_protects_a_name_with_spaces(repo) -> None:
    make_edition(repo, "ed", body="![](my%20photo.png)", files=["my photo.png"])
    assert planned(repo, "ed") == []


def test_references_are_compared_ignoring_case(repo) -> None:
    make_edition(repo, "ed", body="![](PHOTO.PNG)", files=["photo.png"])
    assert planned(repo, "ed") == []


def test_images_in_subdirectories_are_handled_by_their_relative_path(repo) -> None:
    make_edition(
        repo,
        "ed",
        body="![](images/used.png)",
        files=["images/used.png", "images/stale.png"],
    )
    assert planned(repo, "ed") == ["images/stale.png"]


# ── what can be a candidate ──────────────────────────────────────────────────


def test_only_image_files_are_candidates(repo) -> None:
    make_edition(
        repo, "ed", files=["notes.txt", "data.csv", "draft.pdf", "stale.PNG", "s.webp"]
    )
    assert planned(repo, "ed") == ["s.webp", "stale.PNG"]


def test_index_md_is_never_a_candidate(repo) -> None:
    make_edition(repo, "ed", files=[])
    assert planned(repo, "ed") == []


# ── the command ──────────────────────────────────────────────────────────────


def run(repo, apply=False):
    cli.cmd_prune_images(argparse.Namespace(repo=str(repo.parent.parent), apply=apply))


def test_dry_run_reports_and_changes_nothing(repo, capsys) -> None:
    bundle = make_edition(repo, "ed", files=["stale.png"])
    run(repo)
    out = capsys.readouterr().out
    assert "stale.png" in out and "--apply" in out
    assert (bundle / "stale.png").exists()
    assert not state.BACKUPS_DIR.exists()


def test_apply_moves_unreferenced_images_into_backups(repo) -> None:
    bundle = make_edition(
        repo, "ed", body="![](keep.png)", files=["keep.png", "images/stale.png"]
    )
    run(repo, apply=True)
    saved = (
        state.BACKUPS_DIR
        / repo_slug()
        / "ed"
        / "pruned-images"
        / "images"
        / "stale.png"
    )
    assert saved.read_bytes() == b"IMG"
    assert not (bundle / "images" / "stale.png").exists()
    assert (bundle / "keep.png").exists()


def test_apply_is_idempotent(repo, capsys) -> None:
    make_edition(repo, "ed", files=["stale.png"])
    run(repo, apply=True)
    capsys.readouterr()
    run(repo, apply=True)
    assert "Nothing to prune" in capsys.readouterr().out


def test_apply_leaves_draft_editions_alone(repo, capsys) -> None:
    bundle = make_edition(repo, "wip", draft=True, files=["a.png"])
    run(repo, apply=True)
    assert (bundle / "a.png").exists()
    assert "wip" in capsys.readouterr().out  # reported as skipped


def test_apply_does_not_overwrite_an_earlier_saved_copy(repo) -> None:
    saved_dir = state.BACKUPS_DIR / repo_slug() / "ed" / "pruned-images"
    saved_dir.mkdir(parents=True)
    (saved_dir / "stale.png").write_bytes(b"OLDER")
    make_edition(repo, "ed", files=["stale.png"])
    run(repo, apply=True)
    assert (saved_dir / "stale.png").read_bytes() == b"OLDER"
    copies = [p for p in saved_dir.iterdir() if p.name != "stale.png"]
    assert len(copies) == 1 and copies[0].read_bytes() == b"IMG"
