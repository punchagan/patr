"""Tests for publish_edition git flow."""

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
    with server.app.test_client() as c:
        yield c


def make_edition(repo, slug, draft=False):
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


def test_publish_runs_add_commit_push(client, repo):
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


def test_publish_still_pushes_when_nothing_to_commit(client, repo):
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
