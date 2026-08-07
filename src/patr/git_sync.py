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
import tempfile

from patr import state


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=state.REPO_ROOT, capture_output=True, text=True, check=False
    )


_no_hooks_dir: str | None = None


def _no_hooks() -> list[str]:
    """`-c core.hooksPath=<empty dir>` — prepend right after "git" (before
    the subcommand) for any operation that creates a commit: `commit`,
    `cherry-pick`, `rebase`.

    squash_edition_commits() and split_commit() replay/reconstruct content
    that's already been committed — and already gone through the repo's
    real hooks — once; re-running commit hooks on every replayed commit is
    redundant at best. At worst (e.g. a hook that renames or re-encodes
    images on commit) it leaves stray untracked derivative files behind
    after every squash/split, since nothing re-stages or re-commits the
    hook's output — confirmed via a real user's repo with an image-tweaking
    hook. There's no single flag that reliably disables hooks across all
    three commands: `git cherry-pick` has no `--no-verify` at all, and
    `--no-verify` never covers `post-commit` regardless. Overriding
    `core.hooksPath` does, uniformly.
    """
    global _no_hooks_dir
    if _no_hooks_dir is None:
        _no_hooks_dir = tempfile.mkdtemp(prefix="patr-no-hooks-")
    return ["-c", f"core.hooksPath={_no_hooks_dir}"]


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


def _subjects_by_commit() -> dict[str, str]:
    """Map each local-only commit SHA to its subject line, via a single
    `git log` call over the whole upstream..HEAD range. Empty if there's no
    upstream configured."""
    upstream = upstream_ref()
    if upstream is None:
        return {}
    out = _run(
        ["git", "log", "--reverse", "--format=%H%x01%s", f"{upstream}..HEAD"]
    ).stdout
    result: dict[str, str] = {}
    for line in out.splitlines():
        sha, sep, subject = line.partition("\x01")
        if sep:
            result[sha] = subject
    return result


def blocking_commits(
    edition_relpaths: list[str],
) -> list[tuple[str, str, list[str]]]:
    """Return (sha, subject, touched_edition_relpaths) for each local-only
    commit that touches more than one of the given editions, or touches
    exactly one of them plus some path outside all of them — either way,
    squash_edition_commits() refuses to squash every edition such a commit
    touches (see _classify_commits). Read-only; meant for reporting (e.g.
    `patr squash-drafts`'s dry run) so these can be split manually — with
    `git rebase -i`, say — before running --apply.
    """
    commits = _local_only_commits()
    touched_map = _touched_paths_by_commit()
    subjects = _subjects_by_commit()

    def matches(edition_relpath: str, p: str) -> bool:
        return p == edition_relpath or p.startswith(edition_relpath + "/")

    result = []
    for sha in commits:
        paths = touched_map.get(sha, [])
        if not paths:
            continue
        touched_editions = [
            ep for ep in edition_relpaths if any(matches(ep, p) for p in paths)
        ]
        if not touched_editions:
            continue
        fully_covered = all(
            any(matches(ep, p) for ep in touched_editions) for p in paths
        )
        if len(touched_editions) > 1 or not fully_covered:
            result.append((sha, subjects.get(sha, ""), touched_editions))
    return result


def split_commit(
    sha: str, edition_relpaths: list[str]
) -> tuple[bool, str, list[tuple[str, str]]]:
    """Split a single local-only commit into one commit per edition it
    touches (grouped by which of edition_relpaths each changed path falls
    under), plus one more commit for any remaining paths that belong to
    none of them. Everything that came after `sha` in local history is
    replayed on top afterward, unchanged.

    Meant for exactly the commits blocking_commits() reports — splitting
    one so each piece only touches a single edition unblocks
    squash_edition_commits() for the edition(s) involved.

    Since the split pieces' combined diff is identical to the original
    commit's diff, the tree state right after the split matches the
    original tree state at that point exactly, file for file — so
    replaying the later commits on top can't newly conflict as a *result*
    of splitting (any conflict there would already have existed before).

    Returns (ok, error, new_commits) — new_commits is [(sha, label), ...]
    for the pieces `sha` was split into (label is the matched edition_relpath,
    or "other"), in the order created; empty on failure. Refuses outright,
    without touching anything, if the working tree is dirty or `sha` isn't
    among the local-only (not-yet-pushed) commits. On any failure partway
    through — a checkout, stage, commit, or later cherry-pick failing —
    restores the original history exactly (nothing left half-done) and
    returns an error.
    """
    if not working_tree_clean():
        return False, "working tree has uncommitted changes", []

    # sha may be abbreviated (e.g. from blocking_commits()'s 8-char report)
    # — resolve to the full SHA before comparing against local-only commits.
    resolved = _run(["git", "rev-parse", sha]).stdout.strip()
    if not resolved:
        return False, f"{sha} is not a valid commit", []
    sha = resolved

    commits = _local_only_commits()
    if sha not in commits:
        return False, f"{sha} is not a local-only (unpushed) commit", []

    original_head = commits[-1]
    after = commits[commits.index(sha) + 1 :]

    parent = _run(["git", "rev-parse", f"{sha}^"]).stdout.strip()
    if not parent:
        return False, f"could not resolve the parent of {sha} (root commit?)", []

    message = _run(["git", "log", "-1", "--format=%B", sha]).stdout.rstrip("\n")
    paths = _touched_paths_by_commit().get(sha, [])
    if not paths:
        return False, f"{sha} has no changed paths to split", []

    def matches(edition_relpath: str, p: str) -> bool:
        return p == edition_relpath or p.startswith(edition_relpath + "/")

    groups: list[tuple[str | None, list[str]]] = []
    remaining = list(paths)
    for ep in edition_relpaths:
        group = [p for p in remaining if matches(ep, p)]
        if group:
            groups.append((ep, group))
            remaining = [p for p in remaining if p not in group]
    if remaining:
        groups.append((None, remaining))

    def _restore() -> None:
        _run(["git", "reset", "--hard", original_head])

    if _run(["git", "reset", "--hard", parent]).returncode != 0:
        _restore()
        return False, f"failed to reset to {sha}'s parent", []

    new_commits: list[tuple[str, str]] = []
    for label, group_paths in groups:
        existing = [
            p
            for p in group_paths
            if _run(["git", "cat-file", "-e", f"{sha}:{p}"]).returncode == 0
        ]
        deleted = [p for p in group_paths if p not in existing]
        if existing and _run(["git", "checkout", sha, "--", *existing]).returncode != 0:
            _restore()
            return False, f"failed to check out {label or 'other'} paths from {sha}", []
        for p in deleted:
            if (state.REPO_ROOT / p).exists():
                _run(["git", "rm", "-q", p])
        # Only `existing`, not the full group — `git rm` above already
        # staged `deleted` paths; re-adding a now-nonexistent path fails
        # ("pathspec did not match any files").
        if existing and _run(["git", "add", *existing]).returncode != 0:
            _restore()
            return False, f"failed to stage {label or 'other'} paths", []
        suffix = f" (split: {label or 'other'})"
        if (
            _run(["git", *_no_hooks(), "commit", "-m", message + suffix]).returncode
            != 0
        ):
            _restore()
            return False, f"failed to commit {label or 'other'} split", []
        new_sha = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
        new_commits.append((new_sha, label or "other"))

    for after_sha in after:
        if _run(["git", *_no_hooks(), "cherry-pick", after_sha]).returncode != 0:
            _run(["git", "cherry-pick", "--abort"])
            _restore()
            return (
                False,
                (
                    f"cherry-pick of {after_sha} failed while replaying commits after "
                    f"the split — resolve manually or re-run to retry"
                ),
                [],
            )

    return True, "", new_commits


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


def squash_edition_commits(edition_relpath: str) -> tuple[bool, str]:
    """Squash local-only (not-yet-pushed) commits that *exclusively* touch
    edition_relpath into a single commit, keeping the most recent matching
    commit's message. Commits touching other paths only (e.g. other
    editions) are replayed unchanged, in their original relative order; the
    squashed commit itself always lands at the new tip (after all replayed
    commits) — appropriate since this runs right before a push.

    edition_relpath is relative to REPO_ROOT (e.g. "content/newsletter/foo").
    Returns (ok, error) — mirrors split_commit()/fetch_rebase_and_push()
    rather than a bare bool, so a genuine failure (a cherry-pick conflict, a
    merge commit needing -m, an unexpected git error) is distinguishable
    from an ordinary no-op instead of collapsing into the same `False` —
    the CLI previously reported both identically as "nothing to squash",
    which was misleading for anything that wasn't actually a no-op.

    ok is False, with an explanatory error, on: no upstream configured,
    dirty working tree, fewer than two exclusively matching commits, a
    commit touching edition_relpath *and* something else (see
    _classify_commits — refuses outright rather than risk a cherry-pick
    conflict or silently wrong content), a cherry-pick/commit step failing,
    or the matching commits netting to zero diff from the upstream base
    (e.g. an edition created and deleted again before ever being pushed —
    nothing to commit). On any ok=False, the original history is left
    exactly as it was.
    """
    upstream = upstream_ref()
    if upstream is None:
        return False, "no upstream tracking branch configured"
    if not working_tree_clean():
        return False, "working tree has uncommitted changes"

    commits = _local_only_commits()
    if not commits:
        return False, "no local-only (unpushed) commits"
    original_head = commits[-1]

    mine, mixed = _classify_commits(edition_relpath, commits)
    if mixed:
        return False, (
            f"{len(mixed)} local-only commit(s) touch {edition_relpath} and "
            "something else — split them first (see split_commit)"
        )
    others = [c for c in commits if c not in mine]

    if len(mine) < 2:
        return False, "fewer than two local-only commits touch this edition"

    final_message = _run(["git", "log", "-1", "--format=%B", mine[-1]]).stdout

    base = _run(["git", "merge-base", upstream, "HEAD"]).stdout.strip()
    if not base:
        return False, "could not compute merge-base with upstream"

    def _restore() -> None:
        _run(["git", "reset", "--hard", original_head])

    if _run(["git", "reset", "--hard", base]).returncode != 0:
        _restore()
        return False, "failed to reset to the merge-base"

    for sha in others:
        cherry_pick = _run(["git", *_no_hooks(), "cherry-pick", sha])
        if cherry_pick.returncode != 0:
            _run(["git", "cherry-pick", "--abort"])
            _restore()
            return False, (
                f"cherry-pick of {sha} failed (e.g. a real conflict, or a merge "
                "commit needing -m) — resolve manually or re-run to retry: "
                f"{(cherry_pick.stderr or cherry_pick.stdout).strip()}"
            )

    edition_path = state.REPO_ROOT / edition_relpath
    exists_at_head = (
        _run(["git", "cat-file", "-e", f"{original_head}:{edition_relpath}"]).returncode
        == 0
    )
    if exists_at_head:
        checkout = _run(["git", "checkout", original_head, "--", edition_relpath])
        if checkout.returncode != 0:
            _restore()
            return False, (
                f"failed to check out {edition_relpath} from {original_head}: "
                f"{(checkout.stderr or checkout.stdout).strip()}"
            )
        _run(["git", "add", edition_relpath])
    elif edition_path.exists():
        _run(["git", "rm", "-r", "-q", edition_relpath])

    commit = _run(["git", *_no_hooks(), "commit", "-m", final_message])
    if commit.returncode != 0:
        _restore()
        return False, (f"failed to commit: {(commit.stderr or commit.stdout).strip()}")
    return True, ""


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

    rebase = _run(["git", *_no_hooks(), "rebase", upstream])
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
