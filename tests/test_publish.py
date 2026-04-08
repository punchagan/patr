"""Tests for publish_edition and unpublish_edition git flow."""

import textwrap
from unittest.mock import MagicMock, patch

import pytest
from patr import server, state


@pytest.fixture
def repo(tmp_path):
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    (tmp_path / "hugo.toml").write_text("[params]\n")
    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with patch("patr.server.git_mode", return_value=True):
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


def make_run(responses):
    """Return a subprocess.run mock that cycles through the given responses."""
    calls = iter(responses)

    def _run(cmd, **kwargs):
        r = MagicMock()
        r.returncode, r.stdout, r.stderr = next(calls)
        return r

    return _run


# Normal happy path — all three git commands run


def test_publish_runs_add_commit_push(client, repo) -> None:
    make_edition(repo, "my-ed")
    ok = (0, "", "")
    with patch("subprocess.run", side_effect=make_run([ok, ok, ok])) as mock_run:
        r = client.post("/api/publish/my-ed")
    assert r.status_code == 200
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert any("add" in cmd for cmd in cmds)
    assert any("commit" in cmd for cmd in cmds)
    assert any("push" in cmd for cmd in cmds)


# Bug: when commit says "nothing to commit", push is skipped


def test_publish_still_pushes_when_nothing_to_commit(client, repo) -> None:
    """Regression: retry after a failed push must still run git push."""
    make_edition(repo, "my-ed")
    nothing_to_commit = (1, "nothing to commit, working tree clean", "")
    push_ok = (0, "", "")
    with patch(
        "subprocess.run",
        side_effect=make_run(
            [
                (0, "", ""),  # git add — ok
                nothing_to_commit,  # git commit — already committed
                push_ok,  # git push — should still run
            ]
        ),
    ) as mock_run:
        r = client.post("/api/publish/my-ed")
    assert r.status_code == 200
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert any("push" in cmd for cmd in cmds), "git push was never called"


# Publish marks draft editions as live before pushing


def test_publish_marks_draft_as_live(client, repo) -> None:
    """Publish should set draft: false in frontmatter even when edition is a draft."""
    make_edition(repo, "my-ed", draft=True)
    ok = (0, "", "")
    with patch("subprocess.run", side_effect=make_run([ok, ok, ok])):
        r = client.post("/api/publish/my-ed")
    assert r.status_code == 200
    text = (repo / "content" / "newsletter" / "my-ed" / "index.md").read_text()
    assert "draft: false" in text


def test_publish_draft_true_was_previously_rejected(client, repo) -> None:
    """Publish should no longer reject draft editions — it marks them live."""
    make_edition(repo, "my-ed", draft=True)
    ok = (0, "", "")
    with patch("subprocess.run", side_effect=make_run([ok, ok, ok])):
        r = client.post("/api/publish/my-ed")
    assert r.status_code == 200, "draft editions should now be publishable"


# Unpublish sets draft: true and pushes


def test_unpublish_marks_as_draft_and_pushes(client, repo) -> None:
    """Unpublish should set draft: true and run git add/commit/push."""
    make_edition(repo, "my-ed", draft=False)
    ok = (0, "", "")
    with patch("subprocess.run", side_effect=make_run([ok, ok, ok])) as mock_run:
        r = client.post("/api/unpublish/my-ed")
    assert r.status_code == 200
    text = (repo / "content" / "newsletter" / "my-ed" / "index.md").read_text()
    assert "draft: true" in text
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert any("push" in cmd for cmd in cmds)


def test_unpublish_404_for_missing_edition(client, repo) -> None:
    r = client.post("/api/unpublish/no-such-edition")
    assert r.status_code == 404
