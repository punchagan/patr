"""Tests for send_all draft guard and test_send behaviour."""

import json
import subprocess
import textwrap
from unittest.mock import MagicMock, patch

import pytest
from patr import server, state


@pytest.fixture
def repo(tmp_path):
    newsletter = tmp_path / "content" / "newsletter"
    newsletter.mkdir(parents=True)
    state.REPO_ROOT = tmp_path
    state.CONTENT_DIR = newsletter
    return tmp_path


@pytest.fixture
def client(repo):
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with server.app.test_client() as c:
        yield c


def make_edition(repo, slug, draft) -> None:
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


def test_send_all_draft_returns_400(client, repo) -> None:
    # Explicit non-email-only (Hugo/web-publish) mode: draft blocks sending
    # here, since "draft" means "not live on the site yet" — a concept that
    # exists in this mode. repo has no hugo.toml by default, which would
    # default email_only to True (hugo-free mode) and skip this check
    # entirely, so add one to pin the mode being tested.
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')
    make_edition(repo, "my-ed", draft=True)
    r = client.post("/api/send/my-ed")
    assert r.status_code == 400
    assert "draft" in r.get_json()["error"].lower()


def test_send_all_non_draft_passes_draft_check(client, repo) -> None:
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text(
        "[params]\n"
    )  # minimal config so load_hugo_config doesn't crash
    # Will fail further in (no sheet_id configured), but must not fail on draft check
    r = client.post("/api/send/my-ed")
    assert "draft" not in (r.get_json().get("error") or "").lower()


def test_send_all_draft_allowed_in_email_only_mode(client, repo) -> None:
    """ "draft" is a web-publish concept — irrelevant once email_only is on,
    so a draft edition must not be rejected for that reason in this mode."""
    make_edition(repo, "my-ed", draft=True)
    with patch(
        "patr.server.load_newsletter_config",
        return_value={"name": "My Letter", "email_only": True},
    ):
        r = client.post("/api/send/my-ed")
    assert "draft" not in (r.get_json().get("error") or "").lower()


def _parse_sse(data: bytes) -> list[dict]:
    """Parse SSE response body into a list of event dicts."""
    events = []
    for chunk in data.decode().split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return events


def test_send_all_streams_sse_on_success(client, repo) -> None:
    """A successful send_all returns a text/event-stream with progress + done events."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email"),
        patch("patr.server.log_sent"),
        patch(
            "patr.server.fetch_contacts",
            return_value=[{"name": "Alice", "email": "alice@example.com"}],
        ),
        patch("patr.server.get_already_sent", return_value=set()),
        patch(
            "patr.server.load_newsletter_config",
            return_value={"name": "My Letter", "sheet_id": "sheet123"},
        ),
        patch(
            "patr.server.load_hugo_config",
            return_value={"baseURL": "https://real-newsletter.com"},
        ),
        patch("patr.server.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com",
            "name": "Me",
        }
        r = client.post("/api/send/my-ed")

    assert r.status_code == 200
    assert "text/event-stream" in r.content_type
    events = _parse_sse(r.data)
    progress = [e for e in events if e["type"] == "progress"]
    done = next(e for e in events if e["type"] == "done")
    assert len(progress) == 1
    assert progress[0]["sent"] == 1
    assert progress[0]["total"] == 1
    assert done["sent"] == 1
    assert done["failed"] == []

    # A fully successful send (no failures) marks the edition sent: full in
    # its own frontmatter — local metadata so the UI can show a "Sent"
    # indicator without hitting the Sheets API just to know whether an
    # edition has gone out at all, and whether everyone got it.
    content = (repo / "content" / "newsletter" / "my-ed" / "index.md").read_text()
    assert "sent: full" in content


def test_send_all_marks_partial_when_some_contacts_fail(client, repo) -> None:
    """A batch with at least one success and one failure is sent: partial,
    not full — the edition isn't fully covered yet."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    def fake_send(gmail, sender, to, subject, html, plain):
        if "bob" in to:
            raise RuntimeError("boom")

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=fake_send),
        patch("patr.server.log_sent"),
        patch(
            "patr.server.fetch_contacts",
            return_value=[
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
        ),
        patch("patr.server.get_already_sent", return_value=set()),
        patch(
            "patr.server.load_newsletter_config",
            return_value={"name": "My Letter", "sheet_id": "sheet123"},
        ),
        patch(
            "patr.server.load_hugo_config",
            return_value={"baseURL": "https://real-newsletter.com"},
        ),
        patch("patr.server.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com",
            "name": "Me",
        }
        r = client.post("/api/send/my-ed")

    events = _parse_sse(r.data)
    done = next(e for e in events if e["type"] == "done")
    assert done["sent"] == 1
    assert len(done["failed"]) == 1

    content = (repo / "content" / "newsletter" / "my-ed" / "index.md").read_text()
    assert "sent: partial" in content


def test_send_all_does_not_mark_sent_when_all_contacts_fail(client, repo) -> None:
    """If every send fails, the edition must not be marked as sent."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=RuntimeError("boom")),
        patch("patr.server.log_sent"),
        patch(
            "patr.server.fetch_contacts",
            return_value=[{"name": "Alice", "email": "alice@example.com"}],
        ),
        patch("patr.server.get_already_sent", return_value=set()),
        patch(
            "patr.server.load_newsletter_config",
            return_value={"name": "My Letter", "sheet_id": "sheet123"},
        ),
        patch(
            "patr.server.load_hugo_config",
            return_value={"baseURL": "https://real-newsletter.com"},
        ),
        patch("patr.server.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com",
            "name": "Me",
        }
        r = client.post("/api/send/my-ed")

    events = _parse_sse(r.data)
    done = next(e for e in events if e["type"] == "done")
    assert done["sent"] == 0

    content = (repo / "content" / "newsletter" / "my-ed" / "index.md").read_text()
    assert "sent:" not in content


def test_send_all_without_base_url_returns_400(client, repo) -> None:
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text("[params]\n")  # no baseURL
    r = client.post("/api/send/my-ed")
    assert r.status_code == 400
    assert "baseurl" in r.get_json()["error"].lower()


# send_all — email-only mode pushes to git after sending (see git_sync.py).
# Send is the important activity here — a git problem must never block or
# roll back the send itself, only surface a non-fatal warning.


def run(args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if check:
        assert r.returncode == 0, r.stderr
    return r


@pytest.fixture
def git_client(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    local = tmp_path / "local"
    run(["git", "init", "--bare", str(remote)], cwd=tmp_path)
    (local / "content" / "newsletter").mkdir(parents=True)
    run(["git", "init", str(local)], cwd=local)
    run(["git", "config", "user.email", "test@example.com"], cwd=local)
    run(["git", "config", "user.name", "Test"], cwd=local)
    run(["git", "remote", "add", "origin", str(remote)], cwd=local)
    run(["git", "add", "-A"], cwd=local)
    run(["git", "commit", "--allow-empty", "-m", "init"], cwd=local)
    run(["git", "branch", "-M", "main"], cwd=local)
    run(["git", "push", "-u", "origin", "main"], cwd=local)

    monkeypatch.setattr(state, "REPO_ROOT", local)
    monkeypatch.setattr(state, "CONTENT_DIR", local / "content" / "newsletter")
    server.app.config["TESTING"] = True
    server.app.config["PORT"] = 5000
    with server.app.test_client() as c:
        yield c, local


def _do_send(client, extra_config=None):
    config = {"name": "My Letter", "sheet_id": "sheet123", "email_only": True}
    config.update(extra_config or {})
    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email"),
        patch("patr.server.log_sent"),
        patch(
            "patr.server.fetch_contacts",
            return_value=[{"name": "Alice", "email": "alice@example.com"}],
        ),
        patch("patr.server.get_already_sent", return_value=set()),
        patch("patr.server.load_newsletter_config", return_value=config),
        patch("patr.server.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com",
            "name": "Me",
        }
        r = client.post("/api/send/my-ed")
    return r


def test_send_all_pushes_in_email_only_mode(git_client) -> None:
    client, local = git_client
    make_edition(local, "my-ed", draft=True)
    run(["git", "add", "-A"], cwd=local)
    run(["git", "commit", "-m", "wip: Test Edition"], cwd=local)

    r = _do_send(client)

    events = _parse_sse(r.data)
    done = next(e for e in events if e["type"] == "done")
    assert done["sent"] == 1
    assert "git_warning" not in done

    remote_subjects = run(
        ["git", "log", "--format=%s", "origin/main"], cwd=local
    ).stdout
    assert "Send: Test Edition" in remote_subjects


def test_send_all_reports_git_warning_without_blocking_send(
    git_client, tmp_path
) -> None:
    """A git push failure (here: unresolvable rebase conflict) must not
    affect the send result — emails already went out."""
    client, local = git_client

    other = tmp_path / "other"
    other.mkdir()
    run(["git", "init", str(other)], cwd=other)
    run(["git", "config", "user.email", "other@example.com"], cwd=other)
    run(["git", "config", "user.name", "Other"], cwd=other)
    run(["git", "remote", "add", "origin", str(tmp_path / "remote.git")], cwd=other)
    run(["git", "fetch", "origin"], cwd=other)
    # Explicit fetch + checkout onto a branch tracking origin/main, rather
    # than `git clone` — a plain clone's default branch depends on git's
    # (OS-dependent) init.defaultBranch, which can differ from the "main"
    # this repo actually uses, silently committing onto an unrelated branch.
    run(["git", "checkout", "-B", "main", "origin/main"], cwd=other)
    d = other / "content" / "newsletter" / "my-ed"
    d.mkdir(parents=True)
    (d / "index.md").write_text("conflicting remote content")
    run(["git", "add", "-A"], cwd=other)
    run(["git", "commit", "-m", "remote wip"], cwd=other)
    run(["git", "push", "origin", "HEAD:main"], cwd=other)

    make_edition(local, "my-ed", draft=True)
    (local / "content" / "newsletter" / "my-ed" / "index.md").write_text(
        textwrap.dedent("""\
        ---
        title: Test Edition
        date: 2024-01-01
        draft: true
        ---

        Conflicting local content.
    """)
    )
    run(["git", "add", "-A"], cwd=local)
    run(["git", "commit", "-m", "wip: Test Edition"], cwd=local)

    r = _do_send(client)

    events = _parse_sse(r.data)
    done = next(e for e in events if e["type"] == "done")
    assert done["sent"] == 1  # send succeeded regardless
    assert "git_warning" in done
    assert "resolve manually" in done["git_warning"]


def test_send_all_does_not_push_when_not_email_only(git_client) -> None:
    client, local = git_client
    (local / "hugo.toml").write_text(
        'baseURL = "https://real-newsletter.com"\n[params]\n'
    )
    make_edition(local, "my-ed", draft=False)
    run(["git", "add", "-A"], cwd=local)
    run(["git", "commit", "-m", "wip: Test Edition"], cwd=local)

    r = _do_send(client, extra_config={"email_only": False})

    events = _parse_sse(r.data)
    done = next(e for e in events if e["type"] == "done")
    assert done["sent"] == 1
    assert "git_warning" not in done

    remote_subjects = run(
        ["git", "log", "--format=%s", "origin/main"], cwd=local
    ).stdout
    assert "Send: Test Edition" not in remote_subjects


# test_send — no sheet_id configured


def test_test_send_succeeds_without_sheet_id(client, repo) -> None:
    """Test send must return ok=True even when sheet_id is not configured.

    Previously: log_sent(None, ...) raised, the outer except caught it,
    and the route returned 500 — even though the email was delivered.
    """
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email"),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com"
        }
        r = client.post("/api/test-send/my-ed", json={})

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["ok"] is True


def test_test_send_includes_plain_text_part(client, repo) -> None:
    """Emails must include a text/plain part alongside the HTML part."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    captured = {}

    def fake_send(gmail, sender, to, subject, html, plain):
        captured["plain"] = plain

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=fake_send),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com"
        }
        client.post("/api/test-send/my-ed", json={})

    assert "plain" in captured, "send_email was not called with a plain argument"
    assert "Body." in captured["plain"]


def test_test_send_uses_name_email_format(client, repo) -> None:
    """To header should be formatted as 'Name <email>' not bare email."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    captured = {}

    def fake_send(gmail, sender, to, subject, html, plain):
        captured["to"] = to

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=fake_send),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com"
        }
        client.post(
            "/api/test-send/my-ed",
            json={"recipients": [{"name": "Alice", "email": "alice@example.com"}]},
        )

    assert captured["to"] == "Alice <alice@example.com>"


def test_test_send_uses_name_email_format_for_sender(client, repo) -> None:
    """From header should be 'Display Name <email>' using the Google account name."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    captured = {}

    def fake_send(gmail, sender, to, subject, html, plain):
        captured["sender"] = sender

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=fake_send),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com",
            "name": "My Name",
        }
        client.post("/api/test-send/my-ed", json={})

    assert captured["sender"] == "My Name <me@example.com>"


def test_test_send_self_recipient_resolves_to_sender_email(client, repo) -> None:
    """Selecting 'Myself' (__self__) must send to the OAuth email, not the literal string '__self__'."""
    make_edition(repo, "my-ed", draft=False)
    (repo / "hugo.toml").write_text('baseURL = "https://example.com"\n[params]\n')

    captured = {}

    def fake_send(gmail, sender, to, subject, html, plain):
        captured["to"] = to

    with (
        patch("patr.server.get_auth", return_value=MagicMock()),
        patch("patr.server.build") as mock_build,
        patch("patr.server.send_email", side_effect=fake_send),
        patch("patr.server.load_newsletter_config", return_value={"name": "My Letter"}),
    ):
        mock_build.return_value.userinfo().get().execute.return_value = {
            "email": "me@example.com",
            "name": "My Name",
        }
        client.post(
            "/api/test-send/my-ed",
            json={"recipients": [{"name": "You", "email": "__self__"}]},
        )

    assert captured["to"] == "You <me@example.com>"
