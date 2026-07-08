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
- Read `display.today_suggested_limit` (default `5`), `display.show_assignee` (default: auto — see step 6), `milestone.current`, `milestone.required` (default `true`), and `okr.stale_days` (default `7`) from `.solo/config.yml`.

### 2. Fetch open issues

One call, then group in memory:

```bash
gh issue list --repo <owner/repo> --state open --limit 200 \
  --json number,title,labels,body,milestone,assignees
```

`assignees` is an array of objects; the `.login` of each entry is what we render in step 6. An empty array means unassigned.

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
🎯 <milestone.current>: KR1 2/5 · KR2 0/3 — ⏰ not measured for <N> days   ← only if the milestone description has a KR block

In Progress (<count>):
  #<n> [<priority>][<size>] @<login> <title>
  …

Suggested Next (<count>):
  #<n> [<priority>][<size>] @<login> <title>
  …

Blocked (<count>):
  #<n> ⏸ <reason>
  …
```

**Assignee prefix:** between the `[size]` bracket and `<title>`, render the issue's assignees as `@<login>` (or `@a,@b` joined by commas for multiple, no spaces). Drop the prefix entirely (no `@?`, no placeholder) when the assignee array is empty. The prefix appears only on **In Progress** and **Suggested Next** rows — Blocked rows keep the `⏸ <reason>` shape unchanged.

Rendering is gated by `display.show_assignee` (see step 1):

- **Explicit `true`** → always render the prefix (omit only for genuinely-unassigned issues).
- **Explicit `false`** → never render the prefix, even when assignees exist.
- **Unset (auto-detect, default)** → scan the issue list from step 2: if any open issue has a non-empty `assignees` array, render the prefix; otherwise omit it. This keeps single-owner repos clean while light-up multi-owner repos automatically.

For the milestone progress line, fetch counts via:

```bash
gh api "repos/<owner/repo>/milestones?state=open" \
  --jq '.[] | select(.title=="<milestone.current>") | "\(.closed_issues)\t\(.open_issues + .closed_issues)"'
```

If `milestone.current` is set but no matching open milestone exists, show `📦 <name> (missing — create it in GitHub and update milestone.current in .solo/config.yml)` instead.

For the `🎯` KR summary line — same gating as the `📦` line (only when `milestone.current` is set and matches an open milestone). Fetch the milestone's `description` (add `,description` to the `--jq` fields, or read it from the same milestones response) and look for an OKR block: a `## Key Results` heading followed by checklist lines in the form:

```
- [ ] KR1: <outcome> — current: <x> / target: <y> (measured: YYYY-MM-DD)
```

**If the description has no `## Key Results` block, render nothing — no `🎯` line at all.** When a block exists:

1. For each KR line, parse `current: <x> / target: <y>` into the `<x>/<y>` count and take the label from the leading `KRn:` token.
2. Render each as `KR1 2/5 · KR2 0/3`, joined by ` · `.
3. Parse each `(measured: YYYY-MM-DD)` date. Take the **oldest** one and compute `<N>` = whole days since today. If `<N>` exceeds `okr.stale_days` (default `7`), append the tail `— ⏰ not measured for <N> days`. Otherwise omit the tail entirely (no `⏰`).

The full line is `🎯 <milestone.current>: KR1 2/5 · KR2 0/3 — ⏰ not measured for <N> days`. This is a read-only summary — updating a KR means editing the milestone description directly (see the README milestone OKR convention).

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

### 10. Branch-scope drift warning (trunk-based)

After the stale-local-branches hint, run one last **read-only, local-only** check: does the work on the *currently checked-out* branch look like it has drifted from the issue the branch is named for? This is the "started coding issue A on a branch named for issue B" nudge — never blocking, same class as steps 7–9, and intentionally lossy (false positives should be cheap to ignore).

Only the **current** branch is inspected — solo does not walk every In Progress issue's branch. That keeps the step O(1): a single `git log` / `git diff` pair, no extra GitHub API calls beyond step 2.

1. `git branch --show-current`. If empty (detached HEAD) or equal to `trunk.name` → skip silently.
2. Extract `<issue>` from the branch name by regex-parsing it against `branch.pattern` (same translation as step 9: `{prefix}` → `[a-z]+`, `{issue}` → `(\d+)`, `{slug}` → `.+`, anchored `^…$`). No match (a branch created outside `/solo:start`) → skip silently.
3. The extracted `<issue>` must be one of the **In Progress** issues grouped in step 3. If it isn't (e.g. the branch is for a planned or already-closed issue), skip — the drift line surfaces under the In Progress group only, matching the issue's chosen surface point.
4. Gather the branch's work relative to trunk:
   - Commit subjects: `git log <trunk.name>..HEAD --format='%s'`. Subjects only — commit **bodies** are intentionally not scanned, so a body line like `relates to #12` or `see #9` never trips the drift check.
   - Changed paths: `git diff --name-only <trunk.name>...HEAD`.
   - If there are **zero commits** (fresh branch, nothing committed yet) → skip silently. Nothing has drifted yet, and the `git` calls must not error on an empty range.
5. Raise the warning if **either** signal trips:
   - **Commit-trailer drift:** scan the commit **subject lines** (not bodies) for `#<num>` references — typically a squash-merge suffix `(#n)` or a `Closes/Fixes #n` written on the subject. If any subject references an issue number other than `<issue>` (the branch's own issue) → drift. Body mentions are excluded so legitimate cross-references (`relates to #12`) don't raise a false positive on aligned work.
   - **Scope-overlap miss:** build the keyword set from the issue **title plus the first non-empty line of its `## What` section** (the body is already in hand from step 2 — no extra fetch). Tokenize both (lowercase, split on non-alphanumeric, drop tokens shorter than 3 chars and common stopwords like `the`, `and`, `for`, `when`). Pulling in `## What` widens "scope" beyond the title alone, so a branch whose work matches the described scope but reuses none of the title's exact words still counts as aligned. If **zero** of those keywords appears in any commit subject **or** any changed file path → drift. Zero overlap is the deliberately conservative trigger; *any* partial overlap counts as aligned, so a branch that touches even one on-topic file or word never warns. This keeps false positives rare and cheap, per the issue's "false positives should be cheap to ignore."
6. On drift, append one soft line directly under the In Progress group (alongside the issue's row), consistent in shape with the step 7 stale-branch warning:

```
  ⚠ #<n> branch work may have drifted from issue scope — verify or re-home
```

No drift, no line — silence is the aligned-work signal. This step never modifies anything; re-homing commits is left to the user (a future `/solo:start` / manual rebase), matching the read-only contract of every other `/solo:today` nudge.
