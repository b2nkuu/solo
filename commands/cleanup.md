---
description: Sweep stale local branches and worktrees whose issue is closed (or whose PR was merged)
allowed-tools: [Bash]
---

# /solo:cleanup

`/solo:done` and `/solo:workflow` create real local branches and (for the batch path) per-issue worktrees under `.solo/worktrees/<n>/`. After a PR merges with `--delete-branch`, the remote branch is gone but the **local** copy and its worktree stay — disk clutter that hides what's actually in flight and breaks future `/solo:workflow` retries when a branch with the same name still exists locally.

`/solo:cleanup` is the explicit sweep. It lists every local branch + worktree that looks stale, asks once, then deletes in a single batch. It is **always** opt-in — `/solo:done` and `/solo:workflow` never auto-clean.

## When to reach for it

- `/solo:today` printed `ℹ N stale branches — /solo:cleanup`.
- About to re-run `/solo:workflow` and want a fresh slate.
- After a session that closed several issues at once and `git branch` / `git worktree list` got noisy.

For remote branch deletion: that's `gh pr merge --delete-branch`'s job at merge time, not this command's. `/solo:cleanup` only touches the local repo.

## Input

`$ARGUMENTS` must be empty. If anything is passed, stop with `Usage: /solo:cleanup (takes no arguments).`

## Steps

### 1. Pre-flight + resolve repo

- `gh auth status` (stop on failure).
- Resolve repo from `.solo/config.yml`.
- Read `trunk.name` (default `main`) and `branch.pattern` (default `{prefix}/{issue}-{slug}`).
- `git rev-parse --is-inside-work-tree` must return `true` — else stop with `❌ /solo:cleanup must run inside a git work tree.`

### 2. Prune stale remote refs

Always run first so the rest of the scan reflects what `origin` actually has right now:

```bash
git remote prune origin
```

Capture the pruned ref list to mention in the summary. No confirm needed — this only removes local references to branches that no longer exist on the remote. Safe to run before the PR lookups in step 3 — prune only touches local remote-tracking refs (`refs/remotes/origin/*`), not GitHub's API.

### 3. Build the local candidate list

Collect every local branch except `trunk.name` itself:

```bash
git branch --format='%(refname:short)' | grep -v "^<trunk>$"
```

`<trunk>` is the literal trunk name from config (e.g. `main`, `master`, `develop`).

For each candidate, compute these facts (in memory, one pass — do not delete yet):

1. **Issue number.** Try, in order:
   - Find a metadata `branch: <name>` on any **closed** GitHub issue that matches this branch name (preferred — the explicit link).
   - Else regex-parse the branch name against `branch.pattern` translating `{prefix}` → `[a-z]+`, `{issue}` → `(\d+)`, `{slug}` → `.+`. Extract `<issue>`.
   - Else: no issue link. Record `issue: null`.
2. **PR.** Look up an open or merged PR whose `headRefName` matches the branch name:
   ```bash
   gh pr list --repo <owner/repo> --state all --head "<branch>" \
     --json number,state,mergedAt,headRefName
   ```
   Record the most recent one's `state` and `mergedAt`.
3. **Worktree.** From `git worktree list --porcelain`, find the entry whose `branch` matches this branch name. Record `worktree_path` (or `null` if none).
4. **Worktree dirty.** If a worktree exists, check `git -C <worktree_path> status --porcelain`. Non-empty → `dirty: true`.

### 4. Classify each candidate

Apply the predicates **in this order**; the first match wins. If none match, the branch is **active** (skipped silently).

| Order | Classification | Predicate | Action |
|---|---|---|---|
| 1 | **dirty** | worktree exists AND has uncommitted changes | **skip** — report under "needs attention" |
| 2 | **release-bump** | branch matches `release/<version>` AND its PR is `MERGED` | candidate for delete |
| 3 | **stale-merged** | PR is `MERGED`, AND (issue is `CLOSED` OR there was no issue link) | candidate for delete |
| 4 | **stale-closed** | issue is `CLOSED` AND no PR was ever opened from this branch | candidate for delete |
| 5 | **active** | none of the above — including: issue open, PR open/draft, `release/*` with an open or closed-not-merged PR, **or** no issue link AND no PR ever opened (user-created branches stay) | **skip** — silent |

The order matters: **dirty wins over everything**, even a `release/*` branch whose PR was merged. We never delete a worktree the user might still be using.

### 5. Preview

If no candidate landed in the delete categories AND no dirty entries exist:

```
✨ Nothing to clean.
```

and stop.

Otherwise:

```
🧹 /solo:cleanup preview

Stale (will delete):
  - <branch>   ← issue #<n> closed, PR #<pr> merged   (worktree: <path>)
  - <branch>   ← release/<version> bump merged
  …

Dirty (skip — uncommitted changes; remove manually):
  - <branch>   ← worktree: <path>   (M N files)
  …

Pruned remote refs: <N>   (already removed by step 2)

Delete the <K> stale entries? [y/N]
```

Show every group only when non-empty — the `Pruned remote refs` line is omitted when the prune count is `0`. The `Delete the <K> stale entries?` line is omitted when `K == 0` — in that case the preview was purely informational.

**Orphan remote refs are intentionally not surfaced here.** If a branch still exists on `origin` because `gh pr merge --delete-branch` silent-failed at merge time, the preview will not list it — remote branch deletion is out of scope for this command. See the Notes section for the manual recovery path (`gh api -X DELETE …`). Silence in the preview is not a bug; it reflects the local-only contract.

### 6. Apply

Only on `y` (case-insensitive). For each stale entry, in this exact order:

1. **Worktree first.** If `worktree_path` is non-null:
   ```bash
   git worktree remove "<worktree_path>"
   ```
   Worktree-first matters — git refuses to delete a branch that is still checked out in any linked worktree. Removing the worktree releases that reservation so the next step can succeed.
2. **Branch.** `git branch -D <branch>`.

Sequential loop — one branch at a time. If any single delete fails, surface the stderr verbatim, mark the entry as `failed`, and continue with the rest. Don't abort the whole sweep on one bad branch.

### 7. Summary

```
🧹 /solo:cleanup finished
  Deleted: <D> branches (<W> worktrees)
  Skipped (dirty): <S>
  Failed: <F>            ← only if F > 0
  Remote refs pruned: <P>
```

Each `Failed` entry gets a follow-up line citing the branch and the error.

`Remote refs pruned` counts only **local remote-tracking refs** dropped by `git remote prune origin` in step 2 — i.e. branches GitHub had already deleted. Orphan remote refs (still live on `origin` despite `--delete-branch`) are **not** counted here and not reported anywhere in the summary; remote = out of scope. See Notes for manual recovery.

## Design constraints

- **Local-only.** This command never touches remote branches; that's `gh pr merge --delete-branch`'s job at merge time. The only remote interaction is `git remote prune origin` to refresh local remote-tracking refs.
- **Dirty worktrees are always skipped.** A worktree with uncommitted changes is preserved no matter what its issue/PR state is — the user has to clean it up by hand. There is no `--force` to override; the safety here is non-negotiable. Manual escape hatch when the user knows the work is throwaway: `git worktree remove --force <path> && git branch -D <branch>`.
- **Single batched confirm.** Per the plan/release/done pattern, present the whole sweep first and ask once. No per-item prompt.
- **Worktree before branch, always.** `git worktree remove` releases the branch reservation; deleting the branch first would fail.
- **Sequential apply, continue on failure.** One bad delete should not abort the sweep — the user gets a per-entry failure list at the end.
- **Empty-guard.** If nothing is stale and nothing is dirty, print `✨ Nothing to clean.` and exit. No noisy "0 entries" preview.

## Notes

- The local main / trunk branch is never a candidate. It's filtered out in step 3 by name.
- Branches that match no issue and have no PR are conservatively classified as `active` (skipped). Treating them as stale would risk deleting work-in-progress branches the user created outside `/solo:start`.
- `release/<version>` bump branches don't have an issue but do have a PR — the `release-bump` row handles them. After merge, they're as stale as any task branch.
- **Orphan remote refs are out of scope.** Sometimes a PR is merged with `gh pr merge --delete-branch` but the upstream ref persists on `origin` (silent fail — most often branch protection, restricted permissions, or a default-branch reference still pointing at it). `git remote prune origin` in step 2 does **not** delete those refs — prune only drops local remote-tracking refs for branches GitHub has already removed. `/solo:cleanup` will not surface or delete these; remote branch lifecycle is `gh pr merge --delete-branch`'s responsibility, not this command's. Manual recovery when you spot one:
  ```bash
  gh api -X DELETE /repos/<owner>/<repo>/git/refs/heads/<branch>
  ```
  Or delete it from the GitHub web UI (`Branches` page → trash icon next to the branch). After the remote ref is gone, re-run `/solo:cleanup` to prune the now-dangling local remote-tracking ref.
