"""Check whether a newer commit of patr is available on GitHub than the one
installed locally, so the UI can nudge the user to update.

There are no formal releases/tags — patr is a single-maintainer tool
installed by cloning the repo, so "up to date" means "HEAD matches the
latest commit on GitHub's default branch".
"""

import json
import subprocess
import time
import urllib.parse
import urllib.request
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

GITHUB_REPO = "punchagan/patr"
GITHUB_BRANCH = "main"
CHECK_INTERVAL_SECONDS = 60 * 60  # re-check the network at most once an hour

# Files whose presence in a diff means a plain `git pull` might need a
# dependency sync (`uv sync`) afterward — self-updating past one of these is
# not considered safe, since a missing sync could leave the app broken.
DEPENDENCY_FILES = {"pyproject.toml", "uv.lock"}

_cache = {"checked_at": 0.0, "result": None}


def _direct_url_info() -> dict | None:
    """Return the parsed PEP 610 direct_url.json that pip/uv record on
    install, or None if package metadata is missing entirely."""
    try:
        dist = distribution("patr")
        raw = dist.read_text("direct_url.json")
    except PackageNotFoundError:
        return None
    if not raw:
        return None
    return json.loads(raw)


def install_method() -> str:
    """Return "vcs" (`uv tool install git+https://...`), "editable"
    (`pip install -e .`, the documented dev install), or "unknown" (package
    metadata missing, or some other install method) — used to tailor the
    manual-update instructions, since the two supported methods need
    different commands to update."""
    info = _direct_url_info()
    if info is None:
        return "unknown"
    if info.get("vcs_info", {}).get("vcs") == "git":
        return "vcs"
    if info.get("dir_info", {}).get("editable"):
        return "editable"
    return "unknown"


def _editable_checkout_path() -> Path | None:
    """Return the local checkout directory when patr was installed with
    `pip install -e .` (the documented dev install), or None when it was
    installed from a VCS URL (no local checkout to pull into) or package
    metadata is missing entirely."""
    info = _direct_url_info()
    if info is None or info.get("vcs_info"):
        return None
    url = info.get("url", "")
    if not url.startswith("file://"):
        return None
    return Path(urllib.parse.urlsplit(url).path)


def _local_commit() -> str | None:
    """Return the git commit patr was installed from, or None if it can't be
    determined (not installed from git, or package metadata is missing).

    Uses the PEP 610 direct_url.json that pip/uv record on install:
    - `uv tool install git+https://...` records vcs_info.commit_id directly.
    - `pip install -e .` (the documented dev install) records the local
      checkout path instead, so fall back to `git rev-parse HEAD` there.
    """
    info = _direct_url_info()
    if info is None:
        return None

    vcs_info = info.get("vcs_info")
    if vcs_info and vcs_info.get("vcs") == "git":
        return vcs_info.get("commit_id")

    checkout = _editable_checkout_path()
    if checkout is None:
        return None
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _local_tree_clean() -> bool:
    """Return True if the editable checkout has no uncommitted changes.
    False when there's no editable checkout at all, or git fails — a
    self-update should never touch a dirty or indeterminate tree."""
    checkout = _editable_checkout_path()
    if checkout is None:
        return False
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == ""


def _latest_remote_commit() -> str | None:
    """Fetch the latest commit sha on GitHub's default branch, or None on
    any failure (offline, rate-limited, etc.) — this check must never break
    the app."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}"
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return data.get("sha")
    except Exception:
        return None


def _compare(local: str, latest: str) -> dict | None:
    """Fetch GitHub's comparison of local...latest (status, changed files,
    etc.), or None on any failure."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/compare/{local}...{latest}"
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _compare_status(local: str, latest: str) -> str | None:
    """Return GitHub's ahead/behind/diverged/identical status describing how
    `latest` relates to `local`, or None on any failure.

    "ahead" means latest has commits local doesn't — local is behind and
    should update. "behind" means local has commits latest doesn't (e.g. the
    developer's own clone with unpushed work) — not an update nudge.
    "diverged" is ambiguous, so it's also not treated as an update nudge.
    """
    data = _compare(local, latest)
    return data.get("status") if data else None


def _dependency_files_changed(local: str, latest: str) -> bool:
    """Return True if pyproject.toml or uv.lock changed between local and
    latest — meaning a plain `git pull` might need a dependency sync
    afterward, so self-updating past it isn't safe. Fails safe (True, i.e.
    "unsafe") when the comparison itself can't be fetched."""
    data = _compare(local, latest)
    if data is None:
        return True
    changed = {f.get("filename") for f in data.get("files", [])}
    return bool(changed & DEPENDENCY_FILES)


def check_for_update(force: bool = False) -> dict:
    """Return whether a newer commit of patr exists on GitHub than the one
    installed locally, and whether it's safe to apply automatically. Cached
    for CHECK_INTERVAL_SECONDS since this hits the network; pass force=True
    to bypass the cache."""
    now = time.time()
    if (
        not force
        and _cache["result"] is not None
        and now - _cache["checked_at"] < CHECK_INTERVAL_SECONDS
    ):
        return _cache["result"]

    local = _local_commit()
    latest = _latest_remote_commit()
    status = None
    safe = False
    if local and latest and local != latest:
        status = _compare_status(local, latest)
        if status == "ahead":
            safe = _local_tree_clean() and not _dependency_files_changed(local, latest)
    result = {
        "update_available": status == "ahead",
        "local": local,
        "latest": latest,
        "safe_to_auto_update": safe,
        "install_method": install_method(),
    }
    _cache["checked_at"] = now
    _cache["result"] = result
    return result


def apply_update() -> dict:
    """Attempt a safe, fast-forward-only self-update in place.

    Only proceeds when check_for_update() considers it safe (clean tree, no
    dependency file changes) — the server re-derives this itself rather than
    trusting a client-supplied flag. On success, the existing Werkzeug
    reloader (already watching for file changes, since debug=True) restarts
    the process once the pulled .py files land on disk — no explicit restart
    needed here.
    """
    result = check_for_update(force=True)
    if not result["safe_to_auto_update"]:
        return {
            "ok": False,
            "error": "Not safe to auto-update — ask the maintainer to update manually.",
        }

    checkout = _editable_checkout_path()
    if checkout is None:
        return {"ok": False, "error": "No local checkout to update."}

    pull = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
    )
    if pull.returncode != 0:
        return {"ok": False, "error": pull.stderr.strip() or "git pull failed"}

    # Avoid showing a stale "update available" for up to CHECK_INTERVAL_SECONDS after we just applied one.
    _cache["checked_at"] = 0.0
    _cache["result"] = None
    return {"ok": True}
