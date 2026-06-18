---
description: Initialize solo for this repository (labels + config)
allowed-tools: [Bash]
---

# /solo:init

One-time, idempotent setup for a project: create the label taxonomy and write `.solo/config.yml`.

## Managed `.gitignore` lines

Solo writes a small set of local directories that should never be tracked. The list below is the **single source of truth** — to teach `/solo:init` about a new solo-local directory in the future, add one line here and the gitignore step picks it up automatically.

```
.solo/worktrees/
```

Each entry is matched against `.gitignore` by **exact line equality** (not substring). New entries must be added one per line, with no leading/trailing whitespace and no trailing comment.

## Steps

### 1. Pre-flight

```bash
gh auth status
```

- If `gh` is not installed: stop with `https://cli.github.com` hint.
- If auth fails: stop with `gh auth login` hint.

### 2. Resolve / confirm repo

- If `.solo/config.yml` already exists with a real `repo:` field → confirm it: `Use repo <owner/repo>? [Y/n]`.
- Else try `gh repo view --json nameWithOwner -q .nameWithOwner`. If found → confirm.
- Else ask the user for `owner/repo`.

### 3. Create labels (idempotent)

Create the full taxonomy with `--force` so reruns are safe. Run them as a batch. Every label uses a distinct hex color — issues frequently carry one label from each category at once, so reusing a color across categories makes the chips visually indistinguishable.

```bash
REPO=<owner/repo>

# Type
gh label create "type:feature"  --color "1f77b4" --force --repo $REPO
gh label create "type:bug"      --color "d62728" --force --repo $REPO
gh label create "type:task"     --color "2ca02c" --force --repo $REPO
gh label create "type:idea"     --color "9467bd" --force --repo $REPO
gh label create "type:research" --color "17becf" --force --repo $REPO

# Priority
gh label create "priority:high"   --color "e11d48" --force --repo $REPO
gh label create "priority:medium" --color "ff9900" --force --repo $REPO
gh label create "priority:low"    --color "9e9e9e" --force --repo $REPO

# Status
gh label create "status:inbox"       --color "ededed" --force --repo $REPO
gh label create "status:planned"     --color "fbbf24" --force --repo $REPO
gh label create "status:in-progress" --color "2ca02c" --force --repo $REPO
gh label create "status:blocked"     --color "8b0000" --force --repo $REPO
gh label create "status:done"        --color "cccccc" --force --repo $REPO

# Size
gh label create "size:xs" --color "c4b5fd" --force --repo $REPO
gh label create "size:s"  --color "a78bfa" --force --repo $REPO
gh label create "size:m"  --color "8b5cf6" --force --repo $REPO
gh label create "size:l"  --color "7c3aed" --force --repo $REPO
gh label create "size:xl" --color "6d28d9" --force --repo $REPO
```

### 4. Write `.solo/config.yml`

If the file does not exist, create it. If it does, **do not overwrite** — print `ℹ️  .solo/config.yml already exists, keeping it.` instead.

Detect the trunk branch name (default `main`, fallback `master` if `main` doesn't exist locally):

```bash
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||'
# fallback if not in a git repo: "main"
```

Use the detected name as `trunk.name`.

```yaml
# solo configuration
version: 1

repo: "<owner/repo>"

defaults:
  inbox_label: "status:inbox"
  capture_type_guessing: true

trunk:
  name: "<detected-or-main>"
  max_branch_age_days: 2          # /solo:today warns when an in-progress branch is older

branch:
  enabled: true
  pattern: "{prefix}/{issue}-{slug}"   # {prefix} resolved from type:* label (see mapping below)
  branch_from_trunk: true              # always branch from trunk, not current
  # type:* → prefix mapping (5 prefixes, conventional-commits aligned):
  #   type:feature              → feat
  #   type:bug                  → fix
  #   type:task, type:idea      → chore
  #   type:research             → spike   (exploration / time-boxed, may not ship)
  # release flow uses a sixth-style prefix: release/<version> (manifest bump branch in /solo:release).

note:
  storage: "comment"
  decision_prefix: "[decision]"

release:
  tag_pattern: "v{version}"
  initial_version: "0.1.0"

milestone:
  current: "v0.1.0"               # active milestone; new issues attach here
  required: true                  # default-on; set false to allow issues without a milestone

display:
  today_suggested_limit: 5
  date_format: "%Y-%m-%d"
```

Create `.solo/` directory if missing.

If `.solo/config.yml` already exists but is missing the `release:` or `milestone:` blocks (older installs), append the missing blocks in place — do not rewrite the rest of the file.

### 5. Initial milestone

Default: create one milestone named after `release.initial_version` (e.g. `v0.1.0`).

Offer: `Create initial milestone v0.1.0? [Y/n]` (also accept a custom name, or `n` to skip).

If accepted:

```bash
gh api repos/<owner/repo>/milestones -f title="<name>" 2>/dev/null || true
```

(Errors swallowed — duplicates are not fatal.)

If skipped, set `milestone.current: ""` in the config so other commands know there's no active milestone yet.

If multiple names were given (comma-separated), create each; set `milestone.current` to the first one.

### 6. Confirm

```
✅ solo initialized for <owner/repo>
   labels: 18 created/updated
   config: .solo/config.yml
   milestone: <name> (current)
```

Drop the milestone line if none was created.
