"""Git history hygiene for auto-committed edition drafts.

server.commit_edition() creates local-only "wip:" commits on every save
(never pushed on its own). By the time an edition is actually published or
sent, there can be a long trail of these, interleaved with wip commits from
other editions worked on in between. squash_edition_commits() collapses just
one edition's local-only commits into a single commit, leaving everything
else on the branch untouched. fetch_rebase_and_push() then integrates any
remote changes before pushing, so a push never silently diverges from the
remote.
"""

import subprocess

from patr import state


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=state.REPO_ROOT, capture_output=True, text=True, check=False
    )


def upstream_ref() -> str | None:
    """Return the current branch's upstream tracking ref (e.g. "origin/main"),
    or None if none is configured."""
    r = _run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    return r.stdout.strip() if r.returncode == 0 else None


def working_tree_clean() -> bool:
    """Return True if there are no uncommitted changes."""
    return not _run(["git", "status", "--porcelain"]).stdout.strip()


def _local_only_commits() -> list[str]:
    """Return SHAs of commits ahead of the upstream tracking branch, oldest
    first. Empty if there's no upstream configured or nothing is ahead."""
    upstream = upstream_ref()
    if upstream is None:
        return []
    return [
        c
        for c in _run(
            ["git", "rev-list", "--reverse", f"{upstream}..HEAD"]
        ).stdout.split()
        if c
    ]


def _commits_touching(edition_relpath: str, commits: list[str]) -> list[str]:
    return [
        sha
        for sha in commits
        if _run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                sha,
                "--",
                edition_relpath,
            ]
        ).stdout.strip()
    ]


def squashable_commit_count(edition_relpath: str) -> int:
    """Read-only preview: how many local-only commits touch edition_relpath.

    Doesn't mutate anything — safe to call for a dry-run report. A count of
    0 or 1 means squash_edition_commits() would no-op (nothing to squash).
    """
    return len(_commits_touching(edition_relpath, _local_only_commits()))


def squash_edition_commits(edition_relpath: str) -> bool:
    """Squash local-only (not-yet-pushed) commits touching edition_relpath
    into a single commit, keeping the most recent matching commit's message.
    Commits touching other paths (e.g. other editions) are replayed
    unchanged, in their original relative order; the squashed commit itself
    always lands at the new tip (after all replayed commits) — appropriate
    since this runs right before a push.

    edition_relpath is relative to REPO_ROOT (e.g. "content/newsletter/foo").
    Returns True if a squash was performed, False on any no-op or failure:
    no upstream configured, dirty working tree, fewer than two matching
    commits, a cherry-pick/commit step failing, or the matching commits
    netting to zero diff from the upstream base (e.g. an edition created and
    deleted again before ever being pushed — nothing to commit). On any
    False, the original history is left exactly as it was.
    """
    upstream = upstream_ref()
    if upstream is None:
        return False
    if not working_tree_clean():
        return False

    commits = _local_only_commits()
    if not commits:
        return False
    original_head = commits[-1]

    mine = _commits_touching(edition_relpath, commits)
    others = [c for c in commits if c not in mine]

    if len(mine) < 2:
        return False

    final_message = _run(["git", "log", "-1", "--format=%B", mine[-1]]).stdout

    base = _run(["git", "merge-base", upstream, "HEAD"]).stdout.strip()
    if not base:
        return False

    def _restore() -> None:
        _run(["git", "reset", "--hard", original_head])

    if _run(["git", "reset", "--hard", base]).returncode != 0:
        _restore()
        return False

    for sha in others:
        if _run(["git", "cherry-pick", sha]).returncode != 0:
            _run(["git", "cherry-pick", "--abort"])
            _restore()
            return False

    edition_path = state.REPO_ROOT / edition_relpath
    exists_at_head = (
        _run(["git", "cat-file", "-e", f"{original_head}:{edition_relpath}"]).returncode
        == 0
    )
    if exists_at_head:
        if (
            _run(["git", "checkout", original_head, "--", edition_relpath]).returncode
            != 0
        ):
            _restore()
            return False
        _run(["git", "add", edition_relpath])
    elif edition_path.exists():
        _run(["git", "rm", "-r", "-q", edition_relpath])

    if _run(["git", "commit", "-m", final_message]).returncode != 0:
        _restore()
        return False
    return True


def fetch_rebase_and_push() -> tuple[bool, str]:
    """Fetch the upstream remote and rebase local commits on top before
    pushing, so a push never silently diverges from a remote that moved
    (e.g. edited from another machine). Returns (ok, error_message).

    On a rebase conflict, aborts the rebase and leaves local commits exactly
    as they were beforehand — nothing is lost — and returns an error message
    for the caller to surface so the user can resolve it manually.
    """
    upstream = upstream_ref()
    if upstream is None:
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        r = _run(["git", "push", "origin", f"HEAD:{branch}"])
        return r.returncode == 0, (r.stderr or r.stdout).strip()

    remote, _, branch = upstream.partition("/")
    fetch = _run(["git", "fetch", remote, branch])
    if fetch.returncode != 0:
        return False, f"git fetch failed: {(fetch.stderr or fetch.stdout).strip()}"

    rebase = _run(["git", "rebase", upstream])
    if rebase.returncode != 0:
        _run(["git", "rebase", "--abort"])
        return False, (
            "git rebase failed after fetching remote changes — resolve manually: "
            f"{(rebase.stderr or rebase.stdout).strip()}"
        )

    # Explicit refspec — a bare `git push` depends on push.default, which is
    # not universally "simple" (some setups use "nothing", requiring an
    # explicit refspec for every push).
    push = _run(["git", "push", remote, f"HEAD:{branch}"])
    if push.returncode != 0:
        return False, f"git push failed: {(push.stderr or push.stdout).strip()}"
    return True, ""
