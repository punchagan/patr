"""Tests for the "newer version available" nudge and safe self-update."""

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


# --- _editable_checkout_path ---


def test_editable_checkout_path_for_editable_install() -> None:
    direct_url = json.dumps(
        {"url": "file:///home/user/patr", "dir_info": {"editable": True}}
    )
    with patch("patr.updates.distribution") as mock_dist:
        mock_dist.return_value.read_text.return_value = direct_url
        assert str(updates._editable_checkout_path()) == "/home/user/patr"


def test_editable_checkout_path_none_for_vcs_install() -> None:
    direct_url = json.dumps(
        {
            "url": "https://github.com/punchagan/patr",
            "vcs_info": {"vcs": "git", "commit_id": "abc123"},
        }
    )
    with patch("patr.updates.distribution") as mock_dist:
        mock_dist.return_value.read_text.return_value = direct_url
        assert updates._editable_checkout_path() is None


def test_editable_checkout_path_none_when_package_not_found() -> None:
    with patch("patr.updates.distribution", side_effect=PackageNotFoundError("patr")):
        assert updates._editable_checkout_path() is None


# --- install_method ---


def test_install_method_vcs() -> None:
    direct_url = json.dumps(
        {
            "url": "https://github.com/punchagan/patr",
            "vcs_info": {"vcs": "git", "commit_id": "abc123"},
        }
    )
    with patch("patr.updates.distribution") as mock_dist:
        mock_dist.return_value.read_text.return_value = direct_url
        assert updates.install_method() == "vcs"


def test_install_method_editable() -> None:
    direct_url = json.dumps(
        {"url": "file:///home/user/patr", "dir_info": {"editable": True}}
    )
    with patch("patr.updates.distribution") as mock_dist:
        mock_dist.return_value.read_text.return_value = direct_url
        assert updates.install_method() == "editable"


def test_install_method_unknown_when_package_not_found() -> None:
    with patch("patr.updates.distribution", side_effect=PackageNotFoundError("patr")):
        assert updates.install_method() == "unknown"


def test_install_method_unknown_for_non_editable_non_vcs_install() -> None:
    # e.g. a regular `pip install patr` from a built wheel/sdist.
    direct_url = json.dumps({"url": "file:///home/user/patr"})
    with patch("patr.updates.distribution") as mock_dist:
        mock_dist.return_value.read_text.return_value = direct_url
        assert updates.install_method() == "unknown"


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


# --- _local_tree_clean ---


def test_local_tree_clean_true_when_no_uncommitted_changes() -> None:
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=""))
    with (
        patch("patr.updates._editable_checkout_path", return_value="/checkout"),
        patch("subprocess.run", mock_run),
    ):
        assert updates._local_tree_clean() is True


def test_local_tree_clean_false_when_dirty() -> None:
    mock_run = MagicMock(
        return_value=MagicMock(returncode=0, stdout=" M src/patr/updates.py\n")
    )
    with (
        patch("patr.updates._editable_checkout_path", return_value="/checkout"),
        patch("subprocess.run", mock_run),
    ):
        assert updates._local_tree_clean() is False


def test_local_tree_clean_false_when_git_status_fails() -> None:
    mock_run = MagicMock(return_value=MagicMock(returncode=128, stdout=""))
    with (
        patch("patr.updates._editable_checkout_path", return_value="/checkout"),
        patch("subprocess.run", mock_run),
    ):
        assert updates._local_tree_clean() is False


def test_local_tree_clean_false_when_no_checkout() -> None:
    with patch("patr.updates._editable_checkout_path", return_value=None):
        assert updates._local_tree_clean() is False


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


# --- _compare_status / _dependency_files_changed ---


def _mock_compare_response(data: dict) -> MagicMock:
    body = json.dumps(data).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


def test_compare_status_success() -> None:
    with patch(
        "urllib.request.urlopen",
        return_value=_mock_compare_response({"status": "ahead", "files": []}),
    ):
        assert updates._compare_status("old", "new") == "ahead"


def test_compare_status_none_on_network_error() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert updates._compare_status("old", "new") is None


def test_dependency_files_changed_true_when_pyproject_changed() -> None:
    with patch(
        "urllib.request.urlopen",
        return_value=_mock_compare_response(
            {"status": "ahead", "files": [{"filename": "pyproject.toml"}]}
        ),
    ):
        assert updates._dependency_files_changed("old", "new") is True


def test_dependency_files_changed_true_when_lockfile_changed() -> None:
    with patch(
        "urllib.request.urlopen",
        return_value=_mock_compare_response(
            {"status": "ahead", "files": [{"filename": "uv.lock"}]}
        ),
    ):
        assert updates._dependency_files_changed("old", "new") is True


def test_dependency_files_changed_false_when_unrelated_files() -> None:
    with patch(
        "urllib.request.urlopen",
        return_value=_mock_compare_response(
            {"status": "ahead", "files": [{"filename": "src/patr/server.py"}]}
        ),
    ):
        assert updates._dependency_files_changed("old", "new") is False


def test_dependency_files_changed_true_on_network_error() -> None:
    # Fail safe: if we can't tell what changed, assume it's unsafe.
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert updates._dependency_files_changed("old", "new") is True


# --- check_for_update ---


def test_check_for_update_true_and_safe_when_behind_with_clean_pull() -> None:
    with (
        patch("patr.updates._local_commit", return_value="old"),
        patch("patr.updates._latest_remote_commit", return_value="new"),
        patch("patr.updates._compare_status", return_value="ahead"),
        patch("patr.updates._local_tree_clean", return_value=True),
        patch("patr.updates._dependency_files_changed", return_value=False),
    ):
        result = updates.check_for_update(force=True)
    assert result == {
        "update_available": True,
        "local": "old",
        "latest": "new",
        "safe_to_auto_update": True,
    }


def test_check_for_update_not_safe_when_tree_dirty() -> None:
    with (
        patch("patr.updates._local_commit", return_value="old"),
        patch("patr.updates._latest_remote_commit", return_value="new"),
        patch("patr.updates._compare_status", return_value="ahead"),
        patch("patr.updates._local_tree_clean", return_value=False),
        patch("patr.updates._dependency_files_changed", return_value=False),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is True
    assert result["safe_to_auto_update"] is False


def test_check_for_update_not_safe_when_dependency_files_changed() -> None:
    with (
        patch("patr.updates._local_commit", return_value="old"),
        patch("patr.updates._latest_remote_commit", return_value="new"),
        patch("patr.updates._compare_status", return_value="ahead"),
        patch("patr.updates._local_tree_clean", return_value=True),
        patch("patr.updates._dependency_files_changed", return_value=True),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is True
    assert result["safe_to_auto_update"] is False


def test_check_for_update_false_when_up_to_date() -> None:
    with (
        patch("patr.updates._local_commit", return_value="same"),
        patch("patr.updates._latest_remote_commit", return_value="same"),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is False
    assert result["safe_to_auto_update"] is False


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
    assert result["safe_to_auto_update"] is False


def test_check_for_update_false_when_diverged() -> None:
    with (
        patch("patr.updates._local_commit", return_value="local-sha"),
        patch("patr.updates._latest_remote_commit", return_value="main-sha"),
        patch("patr.updates._compare_status", return_value="diverged"),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is False
    assert result["safe_to_auto_update"] is False


def test_check_for_update_false_when_commit_unknown() -> None:
    with (
        patch("patr.updates._local_commit", return_value=None),
        patch("patr.updates._latest_remote_commit", return_value="new"),
    ):
        result = updates.check_for_update(force=True)
    assert result["update_available"] is False
    assert result["safe_to_auto_update"] is False


def test_check_for_update_skips_compare_call_when_identical() -> None:
    with (
        patch("patr.updates._local_commit", return_value="same"),
        patch("patr.updates._latest_remote_commit", return_value="same"),
        patch("patr.updates._compare_status") as mock_compare,
    ):
        updates.check_for_update(force=True)
    mock_compare.assert_not_called()


def test_check_for_update_skips_safety_checks_when_not_ahead() -> None:
    with (
        patch("patr.updates._local_commit", return_value="old"),
        patch("patr.updates._latest_remote_commit", return_value="new"),
        patch("patr.updates._compare_status", return_value="diverged"),
        patch("patr.updates._local_tree_clean") as mock_clean,
        patch("patr.updates._dependency_files_changed") as mock_deps,
    ):
        updates.check_for_update(force=True)
    mock_clean.assert_not_called()
    mock_deps.assert_not_called()


def test_check_for_update_is_cached() -> None:
    with (
        patch("patr.updates._local_commit", return_value="old") as mock_local,
        patch("patr.updates._latest_remote_commit", return_value="new") as mock_remote,
        patch("patr.updates._compare_status", return_value="ahead"),
        patch("patr.updates._local_tree_clean", return_value=True),
        patch("patr.updates._dependency_files_changed", return_value=False),
    ):
        updates.check_for_update(force=True)
        updates.check_for_update()  # should hit the cache, not re-fetch
    mock_local.assert_called_once()
    mock_remote.assert_called_once()


# --- apply_update ---


def _patch_check_for_update(safe: bool):
    return patch(
        "patr.updates.check_for_update",
        return_value={
            "update_available": safe,
            "local": "old",
            "latest": "new",
            "safe_to_auto_update": safe,
        },
    )


def test_apply_update_refuses_when_not_safe() -> None:
    with (
        _patch_check_for_update(safe=False),
        patch("subprocess.run") as mock_run,
    ):
        result = updates.apply_update()
    assert result["ok"] is False
    mock_run.assert_not_called()


def test_apply_update_errors_when_no_checkout() -> None:
    with (
        _patch_check_for_update(safe=True),
        patch("patr.updates._editable_checkout_path", return_value=None),
        patch("subprocess.run") as mock_run,
    ):
        result = updates.apply_update()
    assert result["ok"] is False
    mock_run.assert_not_called()


def test_apply_update_success_resets_cache() -> None:
    updates._cache["checked_at"] = 123.0
    updates._cache["result"] = {"stale": True}
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with (
        _patch_check_for_update(safe=True),
        patch("patr.updates._editable_checkout_path", return_value="/checkout"),
        patch("subprocess.run", mock_run),
    ):
        result = updates.apply_update()
    assert result == {"ok": True}
    mock_run.assert_called_once_with(
        ["git", "pull", "--ff-only"],
        cwd="/checkout",
        capture_output=True,
        text=True,
        check=False,
    )
    assert updates._cache["result"] is None


def test_apply_update_reports_git_pull_failure() -> None:
    mock_run = MagicMock(
        return_value=MagicMock(returncode=1, stdout="", stderr="not a fast-forward")
    )
    with (
        _patch_check_for_update(safe=True),
        patch("patr.updates._editable_checkout_path", return_value="/checkout"),
        patch("subprocess.run", mock_run),
    ):
        result = updates.apply_update()
    assert result["ok"] is False
    assert "fast-forward" in result["error"]
