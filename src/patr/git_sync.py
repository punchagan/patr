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


def _touched_paths_by_commit() -> dict[str, list[str]]:
    """Map each local-only commit SHA to its changed file paths, via a
    single `git log --name-only` call over the whole upstream..HEAD range.

    Deliberately not one `git diff-tree` per commit (the previous
    implementation) — that's O(commits) subprocess spawns, which turns into
    tens of thousands of process spawns (and a very slow `patr
    squash-drafts --repo ...` dry run) on a repo with thousands of unpushed
    commits. Empty if there's no upstream configured.
    """
    upstream = upstream_ref()
    if upstream is None:
        return {}
    out = _run(
        [
            "git",
            "log",
            "--reverse",
            "--name-only",
            "--format=%x00%H",
            f"{upstream}..HEAD",
        ]
    ).stdout
    result: dict[str, list[str]] = {}
    for chunk in out.split("\x00"):
        lines = chunk.splitlines()
        if not lines:
            continue
        result[lines[0]] = [p for p in lines[1:] if p]
    return result


def _classify_commits(
    edition_relpath: str, commits: list[str]
) -> tuple[list[str], list[str]]:
    """Split commits into (exclusive, mixed) relative to edition_relpath —
    "exclusive" touches only paths under edition_relpath, "mixed" touches
    edition_relpath *and* at least one path outside it (e.g. a manual
    `git add -A` commit spanning two editions — never produced by Patr's own
    auto-commit, which always `git add`s exactly one edition's directory,
    but possible in a repo's pre-existing history). Commits touching neither
    are omitted entirely.

    Mixed commits are deliberately never candidates for squashing (see
    squash_edition_commits) — cherry-picking one onto the merge-base would
    apply its edition_relpath-touching hunk against a pre-image that never
    existed there (the intervening "exclusive" commits it actually depended
    on for that path were skipped), which can conflict or, worse, silently
    resolve toward the wrong content instead of failing loudly.
    """
    touched_map = _touched_paths_by_commit()
    prefix = edition_relpath + "/"

    def matches(p: str) -> bool:
        return p == edition_relpath or p.startswith(prefix)

    exclusive, mixed = [], []
    for sha in commits:
        paths = touched_map.get(sha, [])
        touches_this = any(matches(p) for p in paths)
        if not touches_this:
            continue
        if all(matches(p) for p in paths):
            exclusive.append(sha)
        else:
            mixed.append(sha)
    return exclusive, mixed


def squashable_commit_count(edition_relpath: str) -> int:
    """Read-only preview: how many local-only commits exclusively touch
    edition_relpath and would be folded together.

    Doesn't mutate anything — safe to call for a dry-run report. Returns 0
    when squash_edition_commits() would refuse to squash at all — including
    when a commit touching edition_relpath also touches something else (see
    _classify_commits) — not just when there's nothing to squash.
    """
    exclusive, mixed = _classify_commits(edition_relpath, _local_only_commits())
    if mixed:
        return 0
    return len(exclusive)


def squash_edition_commits(edition_relpath: str) -> bool:
    """Squash local-only (not-yet-pushed) commits that *exclusively* touch
    edition_relpath into a single commit, keeping the most recent matching
    commit's message. Commits touching other paths only (e.g. other
    editions) are replayed unchanged, in their original relative order; the
    squashed commit itself always lands at the new tip (after all replayed
    commits) — appropriate since this runs right before a push.

    edition_relpath is relative to REPO_ROOT (e.g. "content/newsletter/foo").
    Returns True if a squash was performed, False on any no-op or failure:
    no upstream configured, dirty working tree, fewer than two exclusively
    matching commits, a commit touching edition_relpath *and* something else
    (see _classify_commits — refuses outright rather than risk a cherry-pick
    conflict or silently wrong content), a cherry-pick/commit step failing,
    or the matching commits netting to zero diff from the upstream base
    (e.g. an edition created and deleted again before ever being pushed —
    nothing to commit). On any False, the original history is left exactly
    as it was.
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

    mine, mixed = _classify_commits(edition_relpath, commits)
    if mixed:
        return False
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
