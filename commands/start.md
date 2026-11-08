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

Fetch the body, find the standalone `<!-- solo:metadata ... -->` block (a line that is exactly `<!-- solo:metadata` through the closing `-->`; a mid-sentence mention of `<!-- solo:metadata -->` is not a block — ignore it and leave it untouched), and set `started: <today>` (only overwrite if the field is empty). Write back:

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
- `branch.pattern` (default `{prefix}/{issue}-{slug}`)
- `trunk.name` (default `main`)
- `trunk.max_branch_age_days` (default `2`)

Pre-branch hygiene:

- `git rev-parse --is-inside-work-tree` must return `true` — else skip branch creation, print `(not a git repo — skipped branch)`.
- Branch **from** `trunk.name`, not from whatever the current branch is. First: `git fetch origin <trunk>` then `git switch <trunk> && git pull --ff-only`. If that fails (uncommitted changes, divergence), ask the user before continuing.
- After trunk is up to date, check `git status --porcelain`:
  - Empty → create the branch automatically.
  - Non-empty → ask: `Working tree is dirty. Create branch anyway? [y/N]`. Only proceed on `y`.

Build the branch name from `branch.pattern` per the **Name** rule in the **Appendix: branch.pattern** at the bottom of this file (`{prefix}` from the issue's `type:*` label, `{issue}` = the issue number, `{slug}` from the title).

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

## Appendix: branch.pattern

This appendix is the canonical definition of how `branch.pattern` becomes a branch name, a glob, or a parse regex. `/solo:start` step 5, `/solo:fast-track` steps 1 + 3, `/solo:loop` Stage A, `/solo:today` steps 9–10, and `/solo:cleanup` step 3 all follow it.

> **Why consumers also carry an inline copy.** An installed command only sees its own injected body — in a user's repo there is no `commands/start.md` on disk to read. So each consumer states the one rule it uses inline, worded to match this appendix. When you change a rule here, update every inline copy in the same PR: `grep -rn 'Appendix: branch.pattern' commands/` lists them all. An inline copy that disagrees with this appendix is a bug.

### Default

`branch.pattern` defaults to `{prefix}/{issue}-{slug}` when unset in `.solo/config.yml`.

### Tokens

| Token | Resolves to |
|---|---|
| `{prefix}` | Conventional-commits prefix from the issue's `type:*` label (table below) |
| `{type}` | Legacy: the raw type name (`feature`, `bug`, `task`, `idea`, `research`). Still honoured for old configs; new repos should use `{prefix}` |
| `{issue}` | The issue number |
| `{slug}` | Slug rule below |

Any other text in the pattern is literal and kept as-is (e.g. `b2nkuu/` in `b2nkuu/{issue}-{slug}`).

| type label | prefix |
|---|---|
| `type:feature` | `feat` |
| `type:bug` | `fix` |
| `type:task`, `type:idea` | `chore` |
| `type:research` | `spike` |

Five prefixes total: `feat`, `fix`, `chore`, `spike`, plus `release/<version>` reserved for `/solo:release`'s manifest bump branch (see `commands/release.md` step 9). `release/<version>` is never built from `branch.pattern` and carries no issue number.

**Slug rule.** Lowercase the title, replace each run of characters outside `[a-z0-9]` with `-`, and trim `-` from both ends. If the result is longer than 40 chars, keep the longest run of whole `-`-separated words that fits in 40 (hard-cut at 40 when the first word alone is longer). If the result is empty — e.g. a title written only in Thai — use `issue`. The rule is deterministic: the same title always gives the same slug.

### Three uses

1. **Name** — substitute every token. Used when the issue number is known (`/solo:start`, `/solo:fast-track` step 3, `/solo:loop` Stage A).
2. **Glob** — used when the issue number is not known yet (`/solo:fast-track`'s branch-already-exists preflight). Substitute every token except `{issue}` → `*`, backslash-escaping any `[`, `]`, `*`, `?` in the literal text and the resolved values. List candidates with `git branch --list '<glob>'`, then keep only those that match the **Regex** below with `{slug}` replaced by the escaped literal slug — `*` also matches `-` and `/`, so `chore/*-fix-typo` would otherwise catch `chore/40-docs-fix-typo`.
3. **Regex** — parse an existing branch name back to its issue number (`/solo:today`, `/solo:cleanup`). Escape the literal text, then translate `{prefix}` → `(?:feat|fix|chore|spike)`, `{type}` → `(?:feature|bug|task|idea|research)`, `{issue}` → `(\d+)`, `{slug}` → `.+`, and anchor with `^…$`. The `(\d+)` capture is the issue number. No match → the branch was not created by solo; callers skip it.

Restricting `{prefix}` / `{type}` to the known values keeps hand-made branches such as `docs/12-notes` from being read as solo branches for #12 (and offered for deletion by `/solo:cleanup`). Anchoring keeps `xb2nkuu/123-foo` from matching `b2nkuu/{issue}-{slug}`.

| `branch.pattern` | Name (`type:task`, #12, "Fix typo") | Glob | Regex |
|---|---|---|---|
| `{prefix}/{issue}-{slug}` | `chore/12-fix-typo` | `chore/*-fix-typo` | `^(?:feat\|fix\|chore\|spike)/(\d+)-.+$` |
| `b2nkuu/{issue}-{slug}` | `b2nkuu/12-fix-typo` | `b2nkuu/*-fix-typo` | `^b2nkuu/(\d+)-.+$` |
| `{type}/{issue}-{slug}` (legacy) | `task/12-fix-typo` | `task/*-fix-typo` | `^(?:feature\|bug\|task\|idea\|research)/(\d+)-.+$` |
