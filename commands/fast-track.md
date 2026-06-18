---
description: Fast-track a tiny task — capture + plan + start in one shot (xs/s only)
argument-hint: "\"<title>\" [<priority> <size>]"
allowed-tools: [Bash]
---

# /solo:fast-track

Collapse `/solo:capture` → `/solo:plan` → `/solo:start` into a single command for trivial work where the three-step ceremony is heavier than the task itself. Strictly scoped to `size:xs` and `size:s`; larger work still goes through the normal flow so design pressure is preserved.

## Input

`$ARGUMENTS` = `"<title>" [<priority> <size>]`.

- `<title>` is required (free text, quoted if it contains spaces).
- `<priority>` is optional. Allowed: `high`, `medium` (alias `med`), `low`. Default: `medium`.
- `<size>` is optional. Allowed: `xs`, `s`. Default: `s`.

Defaults apply **only** when an argument is omitted — never when it is present but malformed.

Empty `$ARGUMENTS` → stop with `Usage: /solo:fast-track "<title>" [<priority> <size>]`.

### Argument parsing rules

1. Extract the title (first quoted string, or everything up to the first space if unquoted and only one token).
2. Look at the remaining tokens:
   - 0 trailing tokens → use defaults `medium s`.
   - 2 trailing tokens → first is priority, second is size. Validate both. If either is unrecognised → reject with `❌ malformed args. Usage: /solo:fast-track "<title>" [<priority> <size>]` (do **not** silently fall back to defaults).
   - 1 trailing token, or 3+ trailing tokens → reject as malformed (do not guess which one was supplied).
3. Normalize `med` → `medium`.

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
- `git rev-parse --is-inside-work-tree` must return `true` — else stop with `❌ not a git repo`.
- Read TBD config from `.solo/config.yml`:
  - `branch.enabled` (default `true`) — if `false`, stop with `❌ branch creation disabled in .solo/config.yml; /solo:fast-track requires it`.
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
- Build the slug (same algorithm as `/solo:start` step 5):
  - `{prefix}` = `chore` (fast-track always uses `type:task`).
  - `{slug}` = title lowercased, non-alphanumeric → `-`, collapse repeats, trimmed to ~40 chars.
- **Branch-already-exists preflight**: list local branches matching `chore/*-<slug>` (the issue number is unknown at this point but the slug is fixed). If any such branch exists → stop with `❌ a branch already exists for this slug: <branch>`. This catches the "I already fast-tracked this" case before the issue is created so no orphan issue is left behind. The post-create existence check in step 3 is a defense-in-depth backstop for the unlikely race where the new issue number happens to collide.

### 2. Create the issue with in-progress labels in one call

Use the same body template as `/solo:capture` (step 5 of `commands/capture.md`) — `## What`, `## Why`, `## Acceptance`, `## Test Plan`, `## Notes`, and the `<!-- solo:metadata -->` block — with today's date in `created:` and the title repeated in `## What`. **Do not** prompt for AC or Test Plan content; fast-track uses the title itself as the acceptance criterion and the user can flesh out detail mid-flight with `/solo:note`.

Ensure labels exist (silent, idempotent):

```bash
gh label create "type:task"          --color "2ca02c" --force --repo <owner/repo>
gh label create "priority:<p>"       --color "<hex>"  --force --repo <owner/repo>
gh label create "size:<s>"           --color "<hex>"  --force --repo <owner/repo>
gh label create "status:in-progress" --color "2ca02c" --force --repo <owner/repo>
```

(Use the colors from `commands/capture.md` and `commands/plan.md`.)

Resolve milestone using the same rules as `/solo:capture` step 6 (`milestone.current` if open; otherwise honour `milestone.required`).

Create the issue, jumping past `status:inbox` straight to `status:in-progress` — all four labels applied in a single call:

```bash
gh issue create \
  --repo <owner/repo> \
  --title "<title>" \
  --body-file <tempfile> \
  --label "type:task,priority:<p>,size:<s>,status:in-progress" \
  [--milestone "<milestone.current>"]
```

Capture the returned issue number `<n>`. Do **not** apply `status:inbox` at any point — fast-track skips the inbox entirely.

### 3. Create the branch off trunk

Run the existing `/solo:start` branch flow (see `commands/start.md` step 5) using the already-validated trunk + clean working tree:

- Final branch name = `chore/<n>-<slug>`.
- Defense-in-depth check: `git show-ref --verify --quiet refs/heads/<branch>`. If it somehow exists, stop with `❌ branch <branch> already exists (issue #<n> was created — recover with /solo:start <n>)`.
- Create and switch:
  ```bash
  git switch -c chore/<n>-<slug>
  ```
- Record the branch name in the issue body's `<!-- solo:metadata -->` `branch:` field, and set `started: <YYYY-MM-DD>` (same edit flow as `/solo:start` step 4).

### 4. Confirm + show goalposts

Print the same final block `/solo:start` ends with (step 6 + step 7 of `commands/start.md`):

```
✅ Fast-tracked #<n> — <title>
🌿 Branch: chore/<n>-<slug>
   type:task  ·  priority:<p>  ·  size:<s>  ·  status:in-progress
```

Then print the `📋 Acceptance:` and `🧪 Test Plan:` goalposts block exactly like `/solo:start` step 7. For fast-tracked issues the AC and Test Plan are the empty `- [ ]` placeholder, so per the start.md rule both sections are skipped — the confirm block above is the entire output.

## Design constraints

- One invocation, one round trip — no batched prompts, no AC/Test Plan generation prompt.
- Defaults (`medium s`) apply only when an arg is omitted, never to recover from a malformed arg.
- Hard refuse `size:m`, `size:l`, `size:xl` — fast-track is the trivial-work shortcut only.
- All `/solo:start` preflight guards (dirty tree, trunk out of sync, branch already exists) fire **before** issue creation. No orphan issues on rejection.
- The created issue is fully compatible with the rest of solo's lifecycle: `/solo:note`, `/solo:test`, `/solo:done` all work normally on it.
