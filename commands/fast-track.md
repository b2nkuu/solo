---
description: Fast-track a tiny task — capture + plan + start in one shot (xs/s only)
argument-hint: "\"<title>\" [<priority> <size>] [--no-branch]"
allowed-tools: [Bash]
---

# /solo:fast-track

Collapse `/solo:capture` → `/solo:plan` → `/solo:start` into a single command for trivial work where the three-step ceremony is heavier than the task itself. Strictly scoped to `size:xs` and `size:s`; larger work still goes through the normal flow so design pressure is preserved.

## Input

`$ARGUMENTS` = `"<title>" [<priority> <size>] [--no-branch]`.

- `<title>` is required (free text, quoted if it contains spaces).
- `<priority>` is optional. Allowed: `high`, `medium` (alias `med`), `low`. Default: `medium`.
- `<size>` is optional. Allowed: `xs`, `s`. Default: `s`.
- `--no-branch` is optional. Create the issue as `status:planned` and do not touch git at all — no fetch, no switch, no branch. Use it from a git worktree that belongs to another issue, then run `/solo:start <n>` later in the worktree where the work will happen.

Defaults apply **only** when an argument is omitted — never when it is present but malformed.

Empty `$ARGUMENTS` → stop with `Usage: /solo:fast-track "<title>" [<priority> <size>] [--no-branch]`.

### Argument parsing rules

1. Extract the title (first quoted string, or everything up to the first space if unquoted and only one token).
2. Remove `--no-branch` from the remaining tokens wherever it appears and remember it was set. Any other `--` token → reject as malformed.
3. Look at the remaining tokens:
   - 0 trailing tokens → use defaults `medium s`.
   - 2 trailing tokens → first is priority, second is size. Validate both. If either is unrecognised → reject with `❌ malformed args. Usage: /solo:fast-track "<title>" [<priority> <size>] [--no-branch]` (do **not** silently fall back to defaults).
   - 1 trailing token, or 3+ trailing tokens → reject as malformed (do not guess which one was supplied).
4. Normalize `med` → `medium`.

### Hard refusal: size:l / size:xl

If the parsed size is `l` or `xl` (or the user writes `m`), stop immediately:

```
❌ /solo:fast-track is for size:xs / size:s only. For larger work,
   use /solo:capture "<title>" then /solo:plan to size + flesh out AC.
```

No issue is created. `m` (`medium` size) is rejected with the same message — fast-track exists for the truly trivial path; anything `m` or larger deserves the planning prompt.

## Steps

### 1. Pre-flight + resolve repo

These guards fire **before any issue creation** so a rejection never leaves an orphan issue.

- `gh auth status` (stop on failure).
- Resolve repo as usual (`.solo/config.yml` → `gh repo view` → ask).
- Read `language:` from `.solo/config.yml` (default `english`) — used for the drafted AC + Test Plan in step 2.

With `--no-branch`, skip every git guard below and go straight to step 2 — nothing in git is read or changed.

- `git rev-parse --is-inside-work-tree` must return `true` — else stop with `❌ not a git repo`.
- Read TBD config from `.solo/config.yml`:
  - `branch.enabled` (default `true`) — if `false`, stop with `❌ branch creation disabled in .solo/config.yml; use --no-branch or /solo:capture`.
  - `branch.pattern` (default `{prefix}/{issue}-{slug}`)
  - `trunk.name` (default `main`)
- Fetch and sync trunk:
  ```bash
  git fetch origin <trunk>
  git switch <trunk> && git pull --ff-only
  ```
  If the trunk pull fails (uncommitted changes on trunk, divergence) → stop with `❌ trunk <trunk> is out of sync — resolve before fast-tracking`.
- Check `git status --porcelain`:
  - Non-empty → stop with `❌ working tree is dirty — commit or stash before fast-tracking`. No issue is created.
- Resolve the `branch.pattern` tokens (same rules as `/solo:start` step 5):
  - `{prefix}` = `chore` (fast-track always uses `type:task`). A legacy `{type}` token resolves to `task`.
  - `{slug}` = title lowercased, non-alphanumeric → `-`, collapse repeats, trimmed to ~40 chars.
  - Literal text in the pattern (e.g. `b2nkuu/` in `b2nkuu/{issue}-{slug}`) is kept as-is.
- **Branch-already-exists preflight**: build a glob from `branch.pattern` with the resolved tokens and `{issue}` → `*` (e.g. `chore/*-<slug>` for the default pattern, `b2nkuu/*-<slug>` for `b2nkuu/{issue}-{slug}`), then list local branches matching it (the issue number is unknown at this point but the rest is fixed). If any such branch exists → stop with `❌ a branch already exists for this slug: <branch>`. This catches the "I already fast-tracked this" case before the issue is created so no orphan issue is left behind. The post-create existence check in step 3 is a defense-in-depth backstop for the unlikely race where the new issue number happens to collide.

### 2. Create the issue with its labels in one call

Use the same body template as `/solo:capture` (step 5 of `commands/capture.md`) — `## What`, `## Why`, `## Acceptance`, `## Test Plan`, `## Notes`, and the `<!-- solo:metadata -->` block — with today's date in `created:` and the title repeated in `## What`.

Fill `## Acceptance` and `## Test Plan` with a draft written from the title — **without prompting**, so repos whose CI requires ticked AC/Test Plan items stay green and `/solo:test` has something to walk:

- 1–3 Acceptance items: concrete done-states for the change the title names (the `type:task` rule from `/solo:plan` step 6).
- 1–2 Test Plan items: how to verify each done-state (a command to run, a file to inspect, a quick manual check).
- Write the prose in `language:`; headings, `- [ ]` syntax, file paths, and identifiers stay English (same rule as `/solo:plan` step 6).
- Stay inside what the title says — do not invent scope. The user can refine mid-flight with `/solo:note`.

The status label is `status:in-progress` by default, or `status:planned` with `--no-branch`.

Ensure labels exist (silent, idempotent):

```bash
gh label create "type:task"          --color "2ca02c" --force --repo <owner/repo>
gh label create "priority:<p>"       --color "<hex>"  --force --repo <owner/repo>
gh label create "size:<s>"           --color "<hex>"  --force --repo <owner/repo>
gh label create "status:in-progress" --color "2ca02c" --force --repo <owner/repo>   # or status:planned (fbbf24) with --no-branch
```

(Use the colors from `commands/capture.md` and `commands/plan.md`.)

Resolve milestone using the same rules as `/solo:capture` step 6 (`milestone.current` if open; otherwise honour `milestone.required`).

Create the issue, jumping past `status:inbox` straight to its status — all four labels applied in a single call:

```bash
gh issue create \
  --repo <owner/repo> \
  --title "<title>" \
  --body-file <tempfile> \
  --label "type:task,priority:<p>,size:<s>,<status>" \
  [--milestone "<milestone.current>"]
```

Capture the returned issue number `<n>`. Do **not** apply `status:inbox` at any point — fast-track skips the inbox entirely.

### 3. Create the branch off trunk

Skip this step with `--no-branch` — leave `started:` and `branch:` empty; `/solo:start <n>` fills them later.

Run the existing `/solo:start` branch flow (see `commands/start.md` step 5) using the already-validated trunk + clean working tree:

- Final branch name = `branch.pattern` with the tokens resolved in step 1 and `{issue}` → `<n>` (default pattern: `chore/<n>-<slug>`).
- Defense-in-depth check: `git show-ref --verify --quiet refs/heads/<branch>`. If it somehow exists, stop with `❌ branch <branch> already exists (issue #<n> was created — recover with /solo:start <n>)`.
- Create and switch:
  ```bash
  git switch -c <branch>
  ```
- Record the branch name in the issue body's `<!-- solo:metadata -->` `branch:` field, and set `started: <YYYY-MM-DD>` (same edit flow as `/solo:start` step 4).

### 4. Confirm + show goalposts

Print the same final block `/solo:start` ends with (step 6 + step 7 of `commands/start.md`):

```
✅ Fast-tracked #<n> — <title>
🌿 Branch: <branch>
   type:task  ·  priority:<p>  ·  size:<s>  ·  status:in-progress
```

With `--no-branch`, replace the branch line and status:

```
✅ Fast-tracked #<n> — <title>
   type:task  ·  priority:<p>  ·  size:<s>  ·  status:planned
   (no branch — run /solo:start <n> in the worktree for this issue)
```

Then print the `📋 Acceptance:` and `🧪 Test Plan:` goalposts block exactly like `/solo:start` step 7, showing the drafted items from step 2.

## Design constraints

- One invocation, one round trip — no batched prompts. AC and Test Plan are drafted from the title without asking.
- Defaults (`medium s`) apply only when an arg is omitted, never to recover from a malformed arg.
- Hard refuse `size:m`, `size:l`, `size:xl` — fast-track is the trivial-work shortcut only.
- The branch name always comes from `branch.pattern` — never a hardcoded `chore/` prefix.
- All `/solo:start` preflight guards (dirty tree, trunk out of sync, branch already exists) fire **before** issue creation. No orphan issues on rejection.
- `--no-branch` never touches git: no fetch, no switch, no branch, no `started:`. The current checkout stays exactly as it was.
- The created issue is fully compatible with the rest of solo's lifecycle: `/solo:note`, `/solo:test`, `/solo:done` all work normally on it.
