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
CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # re-check the network at most once a day

_cache = {"checked_at": 0.0, "result": None}


def _local_commit() -> str | None:
    """Return the git commit patr was installed from, or None if it can't be
    determined (not installed from git, or package metadata is missing).

    Uses the PEP 610 direct_url.json that pip/uv record on install:
    - `uv tool install git+https://...` records vcs_info.commit_id directly.
    - `pip install -e .` (the documented dev install) records the local
      checkout path instead, so fall back to `git rev-parse HEAD` there.
    """
    try:
        dist = distribution("patr")
        raw = dist.read_text("direct_url.json")
    except PackageNotFoundError:
        return None
    if not raw:
        return None
    info = json.loads(raw)

    vcs_info = info.get("vcs_info")
    if vcs_info and vcs_info.get("vcs") == "git":
        return vcs_info.get("commit_id")

    url = info.get("url", "")
    if not url.startswith("file://"):
        return None
    checkout = Path(urllib.parse.urlsplit(url).path)
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


def _compare_status(local: str, latest: str) -> str | None:
    """Return GitHub's ahead/behind/diverged/identical status describing how
    `latest` relates to `local`, or None on any failure.

    "ahead" means latest has commits local doesn't — local is behind and
    should update. "behind" means local has commits latest doesn't (e.g. the
    developer's own clone with unpushed work) — not an update nudge.
    "diverged" is ambiguous, so it's also not treated as an update nudge.
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/compare/{local}...{latest}"
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return data.get("status")
    except Exception:
        return None


def check_for_update(force: bool = False) -> dict:
    """Return whether a newer commit of patr exists on GitHub than the one
    installed locally. Cached for CHECK_INTERVAL_SECONDS since this hits the
    network; pass force=True to bypass the cache."""
    now = time.time()
    if (
        not force
        and _cache["result"] is not None
        and now - _cache["checked_at"] < CHECK_INTERVAL_SECONDS
    ):
        return _cache["result"]

    local = _local_commit()
    latest = _latest_remote_commit()
    if local and latest and local != latest:
        status = _compare_status(local, latest)
    else:
        status = None
    result = {
        "update_available": status == "ahead",
        "local": local,
        "latest": latest,
    }
    _cache["checked_at"] = now
    _cache["result"] = result
    return result
