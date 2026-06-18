---
description: Show today's focus — in-progress, suggested, and blocked tasks
allowed-tools: [Bash]
---

# /solo:today

Show a focused, scannable list of what to work on today.

## Steps

### 1. Pre-flight + resolve repo

- Run `gh auth status`. On failure: stop, tell user to run `gh auth login`.
- Resolve repo: `.solo/config.yml` `repo:` field → fallback `gh repo view --json nameWithOwner -q .nameWithOwner` → ask user.
- Read `display.today_suggested_limit` (default `5`), `milestone.current`, and `milestone.required` (default `true`) from `.solo/config.yml`.

### 2. Fetch open issues

One call, then group in memory:

```bash
gh issue list --repo <owner/repo> --state open --limit 200 \
  --json number,title,labels,body,milestone
```

### 3. Group by status

For each issue, look at its `labels[].name` array and bucket by which `status:*` label it carries:

- `status:in-progress` → **In Progress**
- `status:planned` → **Suggested Next**
- `status:blocked` → **Blocked**
- (Issues with `status:inbox` or no status label are excluded from `/solo:today`.)

### 4. Order Suggested Next

Sort by priority then size:

- Priority order: `priority:high` > `priority:medium` > `priority:low` > (no priority label)
- Size order: `size:xs` < `size:s` < `size:m` < `size:l` < `size:xl` < (no size label, sorted last)

Show only the top N (`display.today_suggested_limit`, default 5).

### 5. Extract blocked reasons

For each Blocked issue, scan the `body` for the most recent `[blocked]` note under `## Notes` (format: `- <date>: [blocked] <reason>`). If none in body, fetch comments and find the latest `[blocked]` line:

```bash
gh issue view <n> --repo <owner/repo> --json comments -q '.comments[].body'
```

Use the reason text (everything after `[blocked] `).

### 6. Render

Use this exact shape (omit a group entirely if empty; if all three are empty, print `No active tasks. Try /solo:plan or /solo:capture.`):

```
📅 Today (<YYYY-MM-DD>)
📦 <milestone.current> (<closed>/<total> done)        ← only if milestone.current set

In Progress (<count>):
  #<n> [<priority>][<size>] <title>
  …

Suggested Next (<count>):
  #<n> [<priority>][<size>] <title>
  …

Blocked (<count>):
  #<n> ⏸ <reason>
  …
```

For the milestone progress line, fetch counts via:

```bash
gh api "repos/<owner/repo>/milestones?state=open" \
  --jq '.[] | select(.title=="<milestone.current>") | "\(.closed_issues)\t\(.open_issues + .closed_issues)"'
```

If `milestone.current` is set but no matching open milestone exists, show `📦 <name> (missing — create it in GitHub and update milestone.current in .solo/config.yml)` instead.

For the `[priority]` and `[size]` brackets in-line, use short forms: `high`/`med`/`low` and `xs`/`s`/`m`/`l`/`xl`. If a label is missing, render `-` (e.g. `[-][m]`).

Keep output compact — no extra blank lines, no headers other than the ones above.

### 7. Stale-branch warning (trunk-based)

After rendering, for each **In Progress** issue parse the `started:` field from its `<!-- solo:metadata -->` block. If `started` is more than `trunk.max_branch_age_days` (default `2`) days ago, append a one-line warning under the In Progress group:

```
  ⚠ #<n> in progress for <X>d — ship or break it down
```

This is the trunk-based-development nudge: short-lived branches only. Don't show the warning if `trunk.max_branch_age_days` is set to `0` (disabled).

### 8. Milestone hygiene warning

After the stale-branch warning, count open issues (from step 2) with `milestone == null`. If the count is > 0:

- `milestone.required: true` → loud warning:
  ```
  ⚠ <N> open issues without a milestone — /solo:plan to backfill
  ```
- `milestone.required: false` → only show if `milestone.current` is set (the user clearly cares about milestones) and the count is ≥ 3, as a soft hint:
  ```
  ℹ <N> open issues without a milestone
  ```

Skip entirely if `milestone.current` is unset and `milestone.required` is false.

### 9. Stale local branches hint

After the milestone hygiene warning, surface a soft hint when the local working tree has accumulated noticeably-stale branches. The check is **read-only and silent unless the count clears a threshold** — `/solo:today` never deletes anything, only nudges; `/solo:cleanup` is where the actual sweep lives.

Use a **cheap heuristic** so this step adds no GitHub API calls beyond what step 2 already paid for:

1. `git branch --format='%(refname:short)'` — local branch names, exclude `trunk.name`.
2. For each branch, extract `<issue>` by regex-parsing the name against `branch.pattern` (translating `{prefix}` → `[a-z]+`, `{issue}` → `(\d+)`, `{slug}` → `.+`, anchored with `^` and `$` so a name like `xfeat/123-foo` does **not** match `feat/{issue}-{slug}`). Branches that don't match (e.g. user-created branches outside `/solo:start`) are **not** counted.
3. For each extracted issue number, check: is it in the open-issue list from step 2? If yes, it's still active — not stale. If no, treat it as stale (the issue is either closed, missing, or in a status the step-2 filter dropped).

Worktrees and PR state are intentionally **not** consulted here — those are `/solo:cleanup`'s job. The point is a fast hint, not the authoritative cleanup decision.

If the stale count is ≥ 3, append at the bottom of the output:

```
ℹ <N> stale local branches — /solo:cleanup
```

Skip the hint entirely when the count is < 3. Three matches the threshold used for the milestone hygiene soft hint — small handfuls aren't worth surfacing; larger pools are.

This count is a **superset** of what `/solo:cleanup` will actually delete. `/solo:cleanup` additionally checks PR state (a branch whose issue is closed but whose PR is still open stays in cleanup's `active` group) and skips dirty worktrees. `/solo:today`'s hint is intentionally lossy — its job is the nudge, not the final word.
