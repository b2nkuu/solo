---
description: Start a task — set in-progress and optionally create a branch
argument-hint: "<issue-number> [--force]"
allowed-tools: [Bash]
---

# /solo:start

Mark a single issue in-progress and (optionally) create a git branch for it. For batching the whole planned backlog through an autonomous lifecycle (start → implement → test → done + PR), use `/solo:loop` instead.

## Cache lag awareness

The slash command body Claude sees is **injected at session start** and stays frozen until `/reload-plugins` or a new session. The on-disk version at `commands/start.md` may have moved on (a recent PR to solo's own specs is the common case). If the disk version differs from the spec text you were handed, **prefer disk**. Before executing any step below, re-read `commands/start.md` from disk and follow that copy.

This matters most when `/solo:start` is being run inside the very session that just edited `commands/start.md` — typical dogfood scenario for solo itself. Re-read on disk first, then run.

## Input

`$ARGUMENTS` = `<issue-number> [--force]`. Tolerate a leading `#` on the issue number. Recognised flags:

- `--force` — bypass the `size:xl` gate (see step 5).
- Anything else → warn `⚠ unknown flag: <token> (ignored)` and continue.

Empty `$ARGUMENTS` → stop with `Usage: /solo:start <issue-number>`.

## Steps

### 1. Pre-flight + resolve repo

- `gh auth status` (stop on failure).
- Resolve repo as usual (`.solo/config.yml` → `gh repo view` → ask).

### 2. Read the issue

```bash
gh issue view <n> --repo <owner/repo> --json number,title,body,labels,state
```

- If the issue is already closed → stop with `❌ #<n> is closed.`
- If it already has `status:in-progress` → friendly no-op:
  ```
  ℹ️  #<n> already in progress.
  ```
  Skip status change but continue to branch creation (so the user can re-create a branch if needed).

### 3. Flip status to in-progress

Remove whichever `status:*` label is currently set (only one should be present per spec §4.4) and add `status:in-progress`. Ensure the label exists first (`gh label create "status:in-progress" --color "2ca02c" --force --repo <owner/repo>`).

```bash
gh issue edit <n> --repo <owner/repo> \
  --remove-label "<current status:* if any>" \
  --add-label "status:in-progress"
```

### 4. Update metadata

Fetch the body, find the `<!-- solo:metadata ... -->` comment, and set `started: <today>` (only overwrite if the field is empty). Write back:

```bash
gh issue view <n> --repo <owner/repo> --json body -q .body > /tmp/solo-body
# edit /tmp/solo-body in-place: replace ^started:.*$ with started: <YYYY-MM-DD>
gh issue edit <n> --repo <owner/repo> --body-file /tmp/solo-body
```

Preserve the rest of the body verbatim.

### 5. Branch creation (optional, trunk-based)

solo follows [trunk-based development](https://trunkbaseddevelopment.com/): branches are **short-lived** (target ≤ 2 days), scoped small, and merged back to `trunk` fast.

**Size gate:** if the issue is labeled `size:xl`, stop and warn:

```
⚠ #<n> is size:xl — too large for a short-lived branch.
   Break it down with /solo:plan first, or override with --force.
```

Only continue past the gate if the user passes `--force` in `$ARGUMENTS` or explicitly confirms.

Read TBD config from `.solo/config.yml`:

- `branch.enabled` (default `true`)
- `branch.pattern` (default `{type}/{issue}-{slug}`)
- `trunk.name` (default `main`)
- `trunk.max_branch_age_days` (default `2`)

Pre-branch hygiene:

- `git rev-parse --is-inside-work-tree` must return `true` — else skip branch creation, print `(not a git repo — skipped branch)`.
- Branch **from** `trunk.name`, not from whatever the current branch is. First: `git fetch origin <trunk>` then `git switch <trunk> && git pull --ff-only`. If that fails (uncommitted changes, divergence), ask the user before continuing.
- After trunk is up to date, check `git status --porcelain`:
  - Empty → create the branch automatically.
  - Non-empty → ask: `Working tree is dirty. Create branch anyway? [y/N]`. Only proceed on `y`.

Build the branch name. The default `branch.pattern` is `{prefix}/{issue}-{slug}`.

- `{prefix}` = resolved from the issue's `type:*` label per the conventional-commits-aligned mapping:

  | type label | prefix |
  |---|---|
  | `type:feature` | `feat` |
  | `type:bug` | `fix` |
  | `type:task`, `type:idea` | `chore` |
  | `type:research` | `spike` |

  Five prefixes total: `feat`, `fix`, `chore`, `spike`, plus `release/<version>` reserved for `/solo:release`'s manifest bump branch (see `commands/release.md` step 9). If a future config sets a custom `branch.pattern` with `{type}` instead of `{prefix}`, fall back to the raw type name (legacy behaviour).
- `{issue}` = the issue number.
- `{slug}` = the title lowercased, non-alphanumeric → `-`, collapse repeats, trimmed to ~40 chars.

```bash
git switch -c <branch-name>
```

Record the branch name in metadata `branch:` field (same body-edit flow as step 4).

### 6. Confirm

```
✅ Started #<n> — <title>
🌿 Branch: <branch-name>
```

If branch was skipped, drop the second line and add `(no branch created)`.

### 7. Show goalposts

Parse the issue body for the `## Acceptance` and `## Test Plan` sections. Print them as-is to set context for the work — checked items keep their `[x]`, unchecked stay `[ ]`. Skip a section entirely if it is missing or contains only the empty `- [ ]` placeholder. If both are absent, skip the whole step (no blank output).

```
📋 Acceptance:
   - [ ] <item 1>
   - [ ] <item 2>
   …

🧪 Test Plan:
   - [ ] <item 1>
   - [ ] <item 2>
   …
```

Read-only — does not modify the issue.
