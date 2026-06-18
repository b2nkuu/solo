---
description: Review inbox and plan tasks (set priority, size, status)
allowed-tools: [Bash]
---

# /solo:plan

Turn raw captures from the Inbox into planned work. Be efficient — batch the decisions.

Also offers a backfill pass for legacy issues missing a milestone (step 8) when strict milestone mode is on.

## Steps

### 1. Pre-flight + resolve repo

- `gh auth status` (stop on failure).
- Resolve repo as usual.
- Read `.solo/config.yml`: `milestone.current` (string) and `milestone.required` (default `true`).

### 2. Fetch inbox

```bash
gh issue list --repo <owner/repo> --state open \
  --label "status:inbox" --limit 100 \
  --json number,title,labels
```

If empty: print `📭 Inbox is empty.` and stop.

### 3. Present the batch

Render a numbered list of inbox items with their current type:

```
📋 Inbox (<count>):
  [1] #<n> [<type>] <title>
  [2] #<n> [<type>] <title>
  …
```

Then ask the user once for a batch decision. Accept either:

- **One-line shorthand per item:** `1: high m` (priority size), `2: low xs milestone:v1`, `3: skip` (leave in inbox).
- **Bulk:** `all: med m` to apply the same priority/size to every item.

Allowed values:

- Priority: `high`, `med` (alias `medium`), `low`
- Size: `xs`, `s`, `m`, `l`, `xl`
- Milestone: `milestone:<name>` (optional, per item). The milestone must already exist — do not auto-create. Create one in GitHub (web UI or `gh api repos/<owner/repo>/milestones -f title="<name>"`), then set `milestone.current` in `.solo/config.yml`.

**Milestone default:** if the user omits `milestone:<name>` for an item, attach `milestone.current` (if set and still open). Items with no milestone after this default are allowed only when `milestone.required: false`; otherwise re-ask for the missing items.

**Trunk-based sizing nudge:** after parsing the full batch input (but before step 4 confirm), collect every item the user assigned `size:xl`. Loop through them one at a time and prompt:

```
⚠ #<n> is size:xl — too large for a short-lived branch.
   Consider breaking it into smaller issues (size ≤ l) so each can ship in ≤ 2 days.

   [b]reakdown — let me suggest sub-issues
   [k]eep as xl   — plan anyway
   [s]kip          — leave in inbox
```

On `b`, run the **xl breakdown flow** (below) for that item, then move to the next xl item. On `k`, allow `xl` and continue. On `s`, drop the item from this plan pass and leave it in `status:inbox`. Only after every xl item has been resolved do you proceed to step 4.

`xl` is allowed (it's just a flag for "needs breakdown"), but solo follows trunk-based development — long-lived branches are an anti-pattern.

#### xl breakdown flow

Triggered when the user picks `b` on a `size:xl` item.

1. Fetch the parent issue:
   ```bash
   gh issue view <n> --repo <owner/repo> --json title,body,labels
   ```
2. Generate 2–4 sub-issue proposals from the title + `## What`. Each proposal must be independently shippable in ≤ 2 days (size ≤ `l`). Inherit the parent's `type:*` label by default; override only when a sub-issue is clearly a different type (e.g. a `type:feature` parent with a `type:research` spike sub-issue). Pull concrete nouns from the body — do not invent unrelated scope.
3. Show the proposals:
   ```
   🧩 Breakdown of #<n> <title>:
      [1] <sub-title 1>  (<type>, ~<size>)
          What: <one-line summary>
      [2] <sub-title 2>  (<type>, ~<size>)
          What: <one-line summary>
      …

   Create which? (e.g. "1,2,3", "all", "edit", "skip")
   ```
4. On `edit`, accept a pasted revision (one sub-issue per block: `title | type | size | what`). On `skip`, abort the breakdown (parent stays `size:xl`, user chose `k` semantics).
5. For each selected sub-issue, create it via `gh issue create` using the standard capture body template (`## What`, `## Why`, `## Acceptance`, `## Test Plan`, `## Notes`, `<!-- solo:metadata -->`). Pre-fill `## What` from the proposal, leave AC/test as the empty `- [ ]` placeholder, and append a line to `## Notes`:
   ```
   Split from #<parent>
   ```
   Apply labels: the chosen `type:*`, `status:planned`, the inherited `priority:*` from the parent (omit if the parent had none — user can set it later), and the proposed `size:*`. Attach the parent's milestone if any. Do not put new sub-issues in `status:inbox` — they were just planned. Add each new sub-issue number to the running list of "items planned this pass" so step 6 picks them up for AC + test plan generation alongside the originals.
6. After creation, edit the parent body to append under `## Notes`:
   ```
   Broken down into: #<c1>, #<c2>, …
   ```
   Then ask:
   ```
   Close #<parent> now? [Y/n]
   ```
   On `Y` (default), `gh issue close <parent> --reason "not planned" --comment "Broken down into #<c1>, #<c2>, …"`. On `n`, leave open but drop it from the current plan pass (do not write `status:planned` on the parent; its sub-issues carry the work now).
7. Report:
   ```
   🧩 Broke #<parent> into <N> sub-issues: #<c1>, #<c2>, …
   ```

### 4. Summarize and confirm

Before applying any changes, print:

```
About to apply:
  #<n>  +priority:high  +size:m   inbox → planned
  #<n>  +priority:low   +size:xs  +milestone:v1   inbox → planned
  #<n>  (skipped)
Confirm? [y/N]
```

Only `y` proceeds. Anything else aborts with no changes.

### 5. Apply

For each non-skipped item:

1. Ensure each needed label exists:
   ```bash
   gh label create "priority:high"   --color "e11d48" --force --repo <owner/repo>
   gh label create "priority:medium" --color "ff9900" --force --repo <owner/repo>
   gh label create "priority:low"    --color "9e9e9e" --force --repo <owner/repo>
   gh label create "size:xs" --color "c4b5fd" --force --repo <owner/repo>
   gh label create "size:s"  --color "a78bfa" --force --repo <owner/repo>
   gh label create "size:m"  --color "8b5cf6" --force --repo <owner/repo>
   gh label create "size:l"  --color "7c3aed" --force --repo <owner/repo>
   gh label create "size:xl" --color "6d28d9" --force --repo <owner/repo>
   gh label create "status:planned" --color "fbbf24" --force --repo <owner/repo>
   ```
   (Only create the ones you actually need; the `--force` keeps it idempotent.)
2. Apply labels + status swap in one edit:
   ```bash
   gh issue edit <n> --repo <owner/repo> \
     --add-label "priority:<x>,size:<y>,status:planned" \
     --remove-label "status:inbox" \
     [--milestone "<name>"]
   ```

### 6. Generate AC + test plan

After apply, offer to flesh out Acceptance Criteria and Test Plan for the items just planned:

```
Generate AC + test plan for <N> planned items? [Y/n]
```

`n` skips this step entirely. On `Y`, loop through each item in order. For each one:

1. Fetch the current body:
   ```bash
   gh issue view <n> --repo <owner/repo> --json title,body,labels
   ```
2. Detect existing content:
   - If `## Acceptance` already contains non-empty checklist items (anything beyond a single empty `- [ ]`), or `## Test Plan` does → prompt `Replace existing AC/test? [y/N]`. Default `N` skips this item.
3. Generate suggestions from the title + `## What` section + the issue's `type:*` label:
   - `type:feature` → AC focused on observable behavior + edge cases; test plan covers unit, integration, edge.
   - `type:bug` → AC includes regression check + reproduction no longer triggers; test plan covers repro path + regression test + nearby surface.
   - `type:research` → AC frames the questions to answer + deliverable artifact; test plan is the validation method (spike doc, data check, prototype).
   - `type:task` → AC is concrete done-states; test plan is verification steps (often manual or smoke).
   - Aim for 3–5 AC items and 2–4 test plan items. Pull concrete nouns from the body — do not invent unrelated scope.
   - If the body has no `## What` content or the title is too vague, output `(no suggestion — provide your own or skip)` instead of guessing.
4. Show the suggestions:
   ```
   #<n> <title>
      What: <first line of ## What>

   📋 Suggested Acceptance:
      - [ ] <item 1>
      - [ ] <item 2>
      …

   🧪 Suggested Test Plan:
      - [ ] <item 1>
      - [ ] <item 2>
      …

   Use? [Y/edit/skip]
   ```
5. Apply:
   - **Y** (default) → rewrite the body. Replace the `## Acceptance` block (from the heading to the next `##` or `---`) with the suggested items. Same for `## Test Plan`. If `## Test Plan` is missing from the body (legacy issue), insert it immediately after `## Acceptance`. Preserve all other sections and the `<!-- solo:metadata -->` block exactly.
   - **edit** → open the suggestion as a draft for the user to paste a revised version (one acceptance line per `- [ ] …`, blank line, one test line per `- [ ] …`). Apply the user's text.
   - **skip** → leave the body unchanged.
6. Write back via `gh issue edit <n> --repo <owner/repo> --body-file <tempfile>`.

If generation fails for any item (API error, empty body), surface a one-line warning and continue with the next item — do not block.

### 7. Confirm

```
✅ Planned <count> items.
   AC/test filled: <N>   skipped: <M>
```

Drop the second line if step 6 was skipped entirely.

### 8. Backfill legacy issues (offered only when `milestone.required: true`)

After the inbox pass, check for open issues with no milestone (any status). If any exist:

```bash
gh issue list --repo <owner/repo> --state open --limit 200 \
  --search "no:milestone" --json number,title,labels
```

Present them and offer a batch assignment:

```
🧭 <count> open issues have no milestone:
  [1] #<n> [<status>] <title>
  …
Assign milestone? (name, "all:<name>", "skip", or enter to defer)
```

On a name (e.g. `v0.4`) or `all:<name>`, apply via `gh issue edit <n> --milestone "<name>"`. Verify the milestone exists and is open first — if not, abort the assignment for that batch with:

```
❌ Milestone "<name>" does not exist. Create it in GitHub first (web UI or `gh api repos/<owner/repo>/milestones -f title="<name>"`), then re-run /solo:plan.
```

Same rule as the inbox batch: `/solo:plan` never auto-creates milestones — keep creation explicit.

Skip this step entirely when `milestone.required: false`.
