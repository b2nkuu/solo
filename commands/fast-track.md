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
