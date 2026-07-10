"""Tests for the "newer version available" nudge."""

import json
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import pytest
from patr import updates


@pytest.fixture(autouse=True)
def reset_cache():
    updates._cache["checked_at"] = 0
    updates._cache["result"] = None
    yield
    updates._cache["checked_at"] = 0
    updates._cache["result"] = None


# --- _local_commit ---


def test_local_commit_from_vcs_install() -> None:
    direct_url = json.dumps(
        {
            "url": "https://github.com/punchagan/patr",
            "vcs_info": {"vcs": "git", "commit_id": "abc123"},
        }
    )
    with patch("patr.updates.distribution") as mock_dist:
        mock_dist.return_value.read_text.return_value = direct_url
        assert updates._local_commit() == "abc123"


def test_local_commit_from_editable_install() -> None:
    direct_url = json.dumps(
        {"url": "file:///home/user/patr", "dir_info": {"editable": True}}
    )
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="def456\n"))
    with (
        patch("patr.updates.distribution") as mock_dist,
        patch("subprocess.run", mock_run),
    ):
        mock_dist.return_value.read_text.return_value = direct_url
        assert updates._local_commit() == "def456"


def test_local_commit_none_when_editable_checkout_has_no_git() -> None:
    direct_url = json.dumps(
        {"url": "file:///home/user/patr", "dir_info": {"editable": True}}
    )
    mock_run = MagicMock(return_value=MagicMock(returncode=128, stdout=""))
    with (
        patch("patr.updates.distribution") as mock_dist,
        patch("subprocess.run", mock_run),
    ):
        mock_dist.return_value.read_text.return_value = direct_url
        assert updates._local_commit() is None


def test_local_commit_none_when_package_not_found() -> None:
    with patch("patr.updates.distribution", side_effect=PackageNotFoundError("patr")):
        assert updates._local_commit() is None


# --- _latest_remote_commit ---


def test_latest_remote_commit_success() -> None:
    body = json.dumps({"sha": "remotesha123"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert updates._latest_remote_commit() == "remotesha123"


def test_latest_remote_commit_none_on_network_error() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert updates._latest_remote_commit() is None


# --- _compare_status ---


def test_compare_status_success() -> None:
    body = json.dumps({"status": "ahead"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert updates._compare_status("old", "new") == "ahead"


def test_compare_status_none_on_network_error() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert updates._compare_status("old", "new") is None


# --- check_for_update ---


def test_check_for_update_true_when_behind() -> None:
    # GitHub's main has commits ours doesn't: "ahead" describes main
    # relative to local, i.e. local is behind.
    with (
        patch("patr.updates._local_commit", return_value="old"),
        patch("patr.updates._latest_remote_commit", return_value="new"),
        patch("patr.updates._compare_status", return_value="ahead"),
    ):
        result = updates.check_for_update(force=True)
    assert result == {
        "update_available": True,
        "local": "old",
        "latest": "new",
    }


def test_check_for_update_false_when_up_to_date() -> None:
    with (
        patch("patr.updates._local_commit", return_value="same"),
        patch("patr.updates._latest_remote_commit", return_value="same"),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is False


def test_check_for_update_false_when_local_has_unpushed_commits() -> None:
    # The developer's own clone can be *ahead* of origin/main — a plain
    # sha inequality would wrongly nudge them to "update" in that case.
    with (
        patch("patr.updates._local_commit", return_value="local-with-wip"),
        patch("patr.updates._latest_remote_commit", return_value="main-sha"),
        patch("patr.updates._compare_status", return_value="behind"),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is False


def test_check_for_update_false_when_diverged() -> None:
    with (
        patch("patr.updates._local_commit", return_value="local-sha"),
        patch("patr.updates._latest_remote_commit", return_value="main-sha"),
        patch("patr.updates._compare_status", return_value="diverged"),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is False


def test_check_for_update_false_when_commit_unknown() -> None:
    with (
        patch("patr.updates._local_commit", return_value=None),
        patch("patr.updates._latest_remote_commit", return_value="new"),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is False


def test_check_for_update_skips_compare_call_when_identical() -> None:
    with (
        patch("patr.updates._local_commit", return_value="same"),
        patch("patr.updates._latest_remote_commit", return_value="same"),
        patch("patr.updates._compare_status") as mock_compare,
    ):
        updates.check_for_update(force=True)
    mock_compare.assert_not_called()


def test_check_for_update_is_cached() -> None:
    with (
        patch("patr.updates._local_commit", return_value="old") as mock_local,
        patch("patr.updates._latest_remote_commit", return_value="new") as mock_remote,
        patch("patr.updates._compare_status", return_value="ahead"),
    ):
        updates.check_for_update(force=True)
        updates.check_for_update()  # should hit the cache, not re-fetch
    mock_local.assert_called_once()
    mock_remote.assert_called_once()
