"""Tests for GET /newsletter/<slug>/<filename> — serves an edition's own
resources (images), but `slug` was previously handed straight into
send_from_directory()'s directory argument unsanitized.

send_from_directory()'s safe_join() protects the filename argument against
".." — it does nothing for the directory argument, and slug becomes part of
that here. A request with slug="..", crafted so the literal ".." reaches
Werkzeug's routing (real HTTP clients vary in whether they normalize ".."
out of a URL before sending — some don't), let this read any file one
directory level up from CONTENT_DIR and downward from there (slug is a
single Flask route segment, so it can only ever be exactly "..", not
"../.." or deeper; and safe_join() rejects any ".." in the filename part
outright, confirmed separately) — e.g. sibling repos/directories next to
the Hugo site in hugo-free mode, where CONTENT_DIR == REPO_ROOT. Confirmed
against a real running server via a raw socket request (bypassing any
client-library-side URL normalization) before this fix landed.

EnvironBuilder + a manually-set PATH_INFO reproduces the same thing here
without needing a real socket — it hands Werkzeug's routing the literal,
unnormalized path a raw request would deliver.
"""

from pathlib import Path

import pytest
from patr import server, state
from werkzeug.test import EnvironBuilder


@pytest.fixture
def repo(tmp_path):
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    edition = newsletter / "test-edition"
    edition.mkdir()
    (edition / "photo.jpg").write_bytes(b"real image bytes")

    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


def _get_raw_path(raw_path: str):
    """Dispatch a request with an unnormalized PATH_INFO, the way a raw
    socket request (curl, browser with encoded dots, etc.) can deliver —
    Flask's test client and most HTTP client libraries normalize ".." out
    of a path string before it ever reaches routing, which would hide this
    bug rather than reproduce it."""
    builder = EnvironBuilder(path="/newsletter/x/y")
    env = builder.get_environ()
    env["PATH_INFO"] = raw_path
    with server.app.request_context(env):
        return server.app.full_dispatch_request()


def test_edition_resource_serves_a_real_edition_file(client, repo) -> None:
    r = client.get("/newsletter/test-edition/photo.jpg")
    assert r.status_code == 200
    assert r.data == b"real image bytes"


def test_edition_resource_blocks_path_traversal_via_slug(repo, tmp_path) -> None:
    secret = tmp_path / "content" / "secret.txt"
    secret.write_text("LEAKED-SECRET-CONTENT")

    resp = _get_raw_path("/newsletter/../secret.txt")
    assert resp.status_code == 404
    assert b"LEAKED-SECRET-CONTENT" not in resp.get_data()


def test_edition_resource_blocks_traversal_to_a_nested_sibling_path(
    repo, tmp_path
) -> None:
    """slug can only ever be exactly ".." (a single Flask route segment
    can't contain "/"), but filename (the <path:...> part) can still
    navigate downward from there — must still be blocked."""
    sibling_dir = tmp_path / "content" / "sibling-project"
    sibling_dir.mkdir()
    (sibling_dir / "secret.txt").write_text("LEAKED-SIBLING-CONTENT")

    resp = _get_raw_path("/newsletter/../sibling-project/secret.txt")
    assert resp.status_code == 404
    assert b"LEAKED-SIBLING-CONTENT" not in resp.get_data()


def test_edition_resource_still_serves_normal_nested_paths(client, repo) -> None:
    """The fix must not break legitimate access, including slugs that
    happen to contain dots elsewhere in the name."""
    edition = Path(state.CONTENT_DIR) / "v2.final-edition"
    edition.mkdir()
    (edition / "photo.jpg").write_bytes(b"other bytes")
    r = client.get("/newsletter/v2.final-edition/photo.jpg")
    assert r.status_code == 200
    assert r.data == b"other bytes"
