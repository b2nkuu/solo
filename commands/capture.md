---
description: Quickly capture a task or idea into GitHub Issues (Inbox)
argument-hint: "\"<task description>\""
allowed-tools: [Bash]
---

# /solo:capture

Instantly record a task or idea into the project's GitHub Issues Inbox with minimal prompts. This command must work even when `/solo:init` has never been run — fall back to sensible defaults.

## Input

`$ARGUMENTS` is the free-text description of the task. If empty, ask **once**: "What do you want to capture?" — then proceed with the user's answer. Do not interrogate further.

## Steps

### 1. Pre-flight

Check `gh` is installed and authenticated:

```bash
gh auth status
```

- If `gh` is not installed: stop and tell the user to install it from `https://cli.github.com`.
- If `gh auth status` fails: stop and tell the user to run `gh auth login`.

### 2. Resolve target repo

In order:

1. If `.solo/config.yml` exists and has a non-empty `repo:` field that does not equal `"owner/repo"` (the placeholder), use it.
2. Else run `gh repo view --json nameWithOwner -q .nameWithOwner` from the current directory. If it succeeds, use that.
3. Else ask the user for `owner/repo`. After they answer, offer (don't force) to save it to `.solo/config.yml`.

Use `--repo <owner/repo>` on subsequent `gh` calls so the command works from any cwd.

### 3. Infer type from text

Lightweight keyword guessing (case-insensitive, no prompts):

- Contains `fix`, `bug`, `error`, `broken`, `crash` → `type:bug`
- Contains `add`, `implement`, `support`, `build`, `create` → `type:feature`
- Contains `investigate`, `research`, `spike`, `explore`, `figure out` → `type:research`
- Looks like a half-formed thought (very short, vague, ends with `?`, no verb) → `type:idea`
- Otherwise → `type:task`

Do **not** guess priority or size — leave them unset. The user sets those later in `/solo:plan`.

### 4. Ensure labels exist

The two labels needed are the inferred `type:*` and `status:inbox`. Create any missing ones silently with the suggested colors:

| Label | Color (hex) |
|-------|------|
| `type:feature` | `1f77b4` |
| `type:bug` | `d62728` |
| `type:task` | `2ca02c` |
| `type:idea` | `9467bd` |
| `type:research` | `17becf` |
| `status:inbox` | `ededed` |

```bash
gh label create "<name>" --color "<hex>" --force --repo <owner/repo>
```

`--force` makes this idempotent. Do not announce label creation — keep output clean.

### 5. Build title and body

**Title:**
- Trim whitespace and trailing punctuation (`.`, `!`, `?`, `…`).
- Capitalize the first letter.
- Truncate to ≤ 70 chars (cut at a word boundary, append `…` only if truncated).

**Body** — use this exact template, with today's date in `YYYY-MM-DD` format and `## What` filled from the input text:

```markdown
## What
<input text>

## Why


## Acceptance
- [ ]

## Test Plan
- [ ]

## Notes


---
<!-- solo:metadata
created: <YYYY-MM-DD>
started:
completed:
time_spent:
branch:
-->
```

Preserve the `<!-- solo:metadata ... -->` comment exactly as shown — other commands parse it.

### 6. Resolve milestone

Read `.solo/config.yml`: `milestone.current` (string) and `milestone.required` (default `true`). If config is missing, treat `milestone.current` as unset and `milestone.required` as `true` — the default applies even pre-init, so a misconfigured repo fails fast rather than silently capturing orphan issues.

If `milestone.current` is non-empty:

1. Verify it is still an **open** milestone on the repo:
   ```bash
   gh api "repos/<owner/repo>/milestones?state=open" --jq '.[].title'
   ```
2. If found → use it. If not found (closed/deleted) → fall through to the "no milestone" branch below.

**No milestone** branch:

- `milestone.required: true` (default) → block:
  ```
  ❌ No active milestone. Create one in GitHub (web UI or
     `gh api repos/<owner/repo>/milestones -f title="<name>"`) and set
     milestone.current in .solo/config.yml, or set milestone.required: false
     in .solo/config.yml to allow milestone-less issues.
  ```
  Stop without creating the issue.
- `milestone.required: false` → proceed without a milestone (no prompt — keep capture fast).

### 7. Create the issue

```bash
gh issue create \
  --repo <owner/repo> \
  --title "<title>" \
  --body-file <tempfile> \
  --label "<type:*>,status:inbox" \
  [--milestone "<milestone.current>"]
```

Only include `--milestone` if a valid open milestone was resolved in step 6. Use `--body-file` (write the body to a temp file) rather than `--body` to avoid shell-escaping issues with multi-line content. Capture the returned issue URL/number.

### 8. Confirm

Print exactly two lines (three if a milestone was attached):

```
✅ Captured #<number>: <title>
   <type:*>  ·  status:inbox
   📦 <milestone>
```

## Design constraints

- Speed over completeness — one line in, one line out.
- Never block on optional fields (priority, size, why, acceptance).
- Avoid multi-question interrogations. The only allowed prompts are (a) text when no argument given, (b) `owner/repo` when unresolvable.
- Do not create duplicate labels; `--force` covers that.
