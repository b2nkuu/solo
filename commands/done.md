---
description: Mark a task done — record outcome and close the issue
argument-hint: "<issue-number> [--force]"
allowed-tools: [Bash]
---

# /solo:done

Finish a task: record an optional outcome line, set `completed`, flip status, close the issue.

By default `/solo:done` refuses to close when any Acceptance or Test Plan item is still `- [ ]` after the tick prompt — closing should mean the work and its verification are complete. Pass `--force` (or `-f`) to override when an item has genuinely gone obsolete.

## Cache lag awareness

The slash command body Claude sees is **injected at session start** and stays frozen until `/reload-plugins` or a new session. The on-disk version at `commands/done.md` may have moved on (a recent PR to solo's own specs is the common case). If the disk version differs from the spec text you were handed, **prefer disk**. Before executing any step below, re-read `commands/done.md` from disk and follow that copy.

This matters most when `/solo:done` is being run inside the very session that just edited `commands/done.md` — typical dogfood scenario for solo itself. Re-read on disk first, then run.

## Input

`$ARGUMENTS` = `<issue-number> [--force]`. Recognised flags:

- `--force` / `-f` — bypass the Acceptance + Test Plan completion gate (step 4a). A `[done-forced]` Notes line records what slipped through.

Anything else after the issue number → warn `⚠ unknown flag: <token> (ignored)` and continue.

## Steps

### 1. Pre-flight + resolve repo

- `gh auth status` (stop on failure).
- Resolve repo as usual.

### 2. Fetch issue

```bash
gh issue view <n> --repo <owner/repo> --json number,title,body,labels,state
```

If already closed (state is `CLOSED`) — typically because a merged PR with `Closes #<n>` auto-closed it — **do not stop**. The status label is sticky and almost certainly still reads `status:in-progress` (or `status:blocked`), which leaves the issue showing up in `/solo:today` and `/solo:status` buckets that should be empty for closed work. Instead:

- Skip step 7 (the close call) — the issue is already closed.
- Still run step 6 (flip status to `status:done`) — this is the whole point of detect-and-flip.
- Steps 3–5 (outcome prompt, body edits, metadata) are also skipped: the user is fixing up state on a PR-closed issue, not finishing the work manually. Closing was already recorded by the PR merge, and re-prompting for an outcome on something they already shipped is friction.
- Skip step 8 (PR offer) — a PR already closed this issue, by definition.
- Print a short note in step 9: `ℹ️  #<n> was already closed (PR auto-close). Flipped status:* → status:done.`

In short: detect already-closed → jump straight to step 6, then step 9. The rest of the flow is for issues that are still open when `/solo:done` runs.

### 3. Confirm final tick state + ask for outcome (optional)

Parse both `## Acceptance` and `## Test Plan` from the body. For each section, list every `- [ ]` / `- [x]` item with an index. A section is "skippable" if it is missing or contains only the empty `- [ ]` placeholder — drop it from the prompt entirely. If both sections are skippable, jump straight to the outcome question.

`/solo:test` is the recommended way to verify both sections **before** `/solo:done`: it walks AC and Test Plan item by item, suggests grep/code lookups for AC and run/manual checks for TP, and ticks what passed. If the user already ran `/solo:test`, most items here will already be `- [x]` — this prompt is a final confirmation, not a first-touch verification. The completion gate in step 4a will catch anything still left.

Prompt in one block (omit any skippable section):

```
Acceptance items (<N>):
  1. [<x or space>] <item 1>
  2. [<x or space>] <item 2>
  …

Test Plan items (<M>):
  1. [<x or space>] <item 1>
  …

Tick any remaining? [Y/edit/n]
One-line outcome (enter to skip):
```

`Tick any remaining?` is a final confirmation across both sections. If `/solo:test` was run, most items are already ticked and `Y` is a no-op for those. Read the responses (Y/edit/n is the first line, outcome is the second). If the user types nothing for outcome, skip the outcome step. Hold all decisions for step 4.

Tick handling (applied uniformly to AC and TP — both have been through the same `/solo:test` rigor, so neither is special):
- **Y** (default) — set every still-unticked `- [ ]` under `## Acceptance` AND `## Test Plan` to `- [x]`. Already-ticked items stay ticked. This is a no-op when `/solo:test` already covered everything.
- **edit** — re-prompt separately so the user can tick a subset of the remaining items in each section:
  ```
  Acceptance tick which? (e.g. "1,3,4", "all", "none")
  Test plan tick which? (e.g. "1,2", "all", "none")
  ```
  Parse comma-separated indices per section. `all` ticks every item in that section; `none` leaves it. Invalid/out-of-range indices are ignored with a one-line warning.
- **n** — leave both sections unchanged. Use this when you intentionally want the completion gate to fire (e.g. you know an AC item is unmet and you'll `--force` close).

If a section was skippable, treat it as if `none` was chosen for that section (no edits to it).

### 4a. Completion gate

After resolving step 3's tick decisions but **before** any body write, compute the final tick state each section would have if step 4 were applied (i.e. apply `Y` / `edit` / `n` in-memory). Then for each non-skippable section, list its items that would still be `- [ ]`:

- `K_ac` = count of unticked items in `## Acceptance` after the would-be edits.
- `K_tp` = count of unticked items in `## Test Plan` after the would-be edits.

Skippable sections (missing or only the placeholder `- [ ]`) contribute `0` and never gate.

If `K_ac + K_tp == 0` → proceed to step 4.

If `K_ac + K_tp > 0` and `--force` (or `-f`) is **not** set → stop with:

```
❌ Cannot close #<n> — <K_ac + K_tp> unticked items:
   Acceptance (<K_ac>):
     - [ ] <item>
     …
   Test Plan (<K_tp>):
     - [ ] <item>
     …
Tick the remaining items first, or rerun with `/solo:done --force <n>` to close anyway.
```

Omit a section's block when its count is `0`. Make no mutations — no body edit, no metadata write, no label change, no close call.

If `--force` is set, proceed to step 4. The forced-close gets a Notes line appended in step 4 alongside the outcome (see below).

### 4. Apply body edits (outcome + acceptance + test plan)

Edit the body in one write that covers both changes (skip the write entirely if neither applies):

- If an outcome was provided, append under `## Notes`:
  ```
  - <YYYY-MM-DD>: [done] <outcome>
  ```
  (If `## Notes` is empty or contains only whitespace, put the bullet right under the heading.)
- If `--force` was used to bypass step 4a, append a second Notes line summarising what slipped through:
  ```
  - <YYYY-MM-DD>: [done-forced] <K_ac> AC + <K_tp> Test Plan unticked at close
  ```
  Omit a `0`'d half (e.g. `2 AC unticked at close` when Test Plan was clean; `1 Test Plan unticked at close` when AC was clean). Use the `K_ac` / `K_tp` values from step 4a — measured **before** step 4 applied any ticks (which it won't for `n`; `Y` and `edit` flow doesn't trigger this branch because the gate would have passed).
- If the acceptance decision was `Y` or `edit`, rewrite the `## Acceptance` block per step 3. Same for `## Test Plan`.

Use the same body-fetch / edit-in-place / `gh issue edit --body-file` pattern as `/solo:start`.

### 5. Update metadata

Set `completed: <YYYY-MM-DD>` inside the `<!-- solo:metadata ... -->` block (only if currently empty). Same edit pattern.

### 6. Flip status to done

Ensure label exists:

```bash
gh label create "status:done" --color "cccccc" --force --repo <owner/repo>
```

Inspect the labels fetched in step 2 and find any existing `status:*` label (there should be at most one). Two branches:

- **A current `status:*` label exists** (e.g. `status:in-progress`, `status:blocked`, `status:planned`, `status:inbox`) and it is not already `status:done` — swap it:

  ```bash
  gh issue edit <n> --repo <owner/repo> \
    --remove-label "<current status:*>" \
    --add-label "status:done"
  ```

- **No `status:*` label is present**, or the only one is already `status:done` — skip the remove (passing `--remove-label` for a label that isn't on the issue makes `gh` error out). Just ensure `status:done` is on:

  ```bash
  gh issue edit <n> --repo <owner/repo> \
    --add-label "status:done"
  ```

This branch matters for the detect-and-flip path from step 2 (a PR-closed issue might still have `status:in-progress`, or might already have been hand-fixed to `status:done`), and also keeps the normal-close path robust when an issue somehow has no status label.

### 7. Close the issue

```bash
gh issue close <n> --repo <owner/repo>
```

### 8. Trunk-based merge hint

Read `trunk.name` from `.solo/config.yml` (default `main`) and the issue metadata `branch:` field.

**Guards — skip the PR offer entirely if any of these fail:**

- Not inside a git work tree (`git rev-parse --is-inside-work-tree` is not `true`).
- No `branch:` recorded in the issue metadata.
- Current local branch (`git branch --show-current`) does not match the recorded branch — the user is somewhere else, don't surprise them.
- Current branch IS the trunk (`git branch --show-current` == `trunk.name`) — there's nothing to PR.
- No `origin` remote exists (`git remote get-url origin` fails) — local-only repo, can't push.

If all guards pass, offer (don't force):

```
Branch <name> is on this issue. Open a PR to <trunk>? [Y/n]
```

On `y`:

1. Build the PR body per the **PR body shape** appendix at the bottom of this file. Use the issue body that step 4 just wrote — no second prompt to the user. Re-fetch the body via `gh issue view <n> --json body -q .body` rather than reusing an in-memory copy, so a step 4 failure that aborts before this point is impossible to render past. Write the rendered Markdown to a temp file so newlines and code blocks survive (`gh pr create --body "..."` mangles multi-line content; `--body-file` does not).

   ```bash
   # Render the body per the appendix, write to /tmp/solo-pr-<n>.md
   ```

2. Push and open the PR with the body file:

   ```bash
   git push -u origin <branch>
   gh pr create --repo <owner/repo> --base <trunk> --head <branch> \
     --title "<issue title>" \
     --body-file /tmp/solo-pr-<n>.md
   ```

If `gh pr create` fails because a PR already exists for the branch, surface the existing URL instead of erroring out:

```bash
gh pr view --repo <owner/repo> --head <branch> --json url -q .url 2>/dev/null
```

The principle: short-lived branches → merged back to trunk fast, not left dangling.

### 9. Confirm

```
🎉 Closed #<n> — <title>
```

If a PR was opened, add a second line: `🔀 PR: <url>`.

## Appendix: PR body shape

This appendix defines the canonical PR body that **both** `/solo:done` step 8 and `/solo:workflow` Stage E step 8 produce. Single source of truth — drift between the two commands is a bug.

> **Cache-lag note for self-edits.** When you (Claude) run `/solo:done` after a spec change to this very file (`commands/done.md`), re-read from disk first to get the latest appendix rules. The injected slash command body is frozen at session start, but the canonical render rules for the PR body live here and may have been updated by an in-session commit (or a freshly merged PR) — disk wins.
>
> **Approach call-out source.** The `[approach]` line consumed by Summary synthesis (below) is expected to be written automatically by `/spirit:implement` Phase 5 — tracked in `b2nkuu/spirit#8`. Until that ships, the line only appears when the user writes it manually as a comment on the issue (or edits the body's `## Notes` directly). A PR with no Approach call-out is the normal `/solo:workflow` path and is not a bug.

### Render order (top to bottom)

```markdown
Closes #<n>

## Summary
<one paragraph synthesizing the issue title + ## What + the most recent [approach] line in ## Notes, if any>

## Acceptance
- [<x or space>] <item>
…

## Test Plan
- [<x or space>] <item>
…

## Notes
<verbatim copy of the issue's ## Notes block, with the trailing <!-- solo:metadata --> comment stripped>
```

Every section appears **only when non-empty after rendering**:

- `Closes #<n>` — always present (first line, single line).
- `## Summary` — always present. See "Summary synthesis" below for fallback when sources are sparse.
- `## Acceptance` — omitted when the issue's `## Acceptance` is skippable. Skippable means the heading is absent, OR the section contains no `- [ ]` / `- [x]` items at all (whitespace, the empty `- [ ]` placeholder, or stray text without checklist syntax all count as "no items"). Ticks in the rendered output reflect the body that step 4 just wrote, so a `--force` close shows any `- [ ]` lines that survived the gate.
- `## Test Plan` — same omit rule against the issue's `## Test Plan`.
- `## Notes` — copy the issue's `## Notes` block verbatim with two strip operations applied **only** to the bottom of the section:
  1. Remove a trailing `---` line if it is the **last non-blank line**.
  2. Remove a trailing `<!-- solo:metadata … -->` HTML comment if it is the last non-blank block (the comment itself spans multiple lines — strip the whole opening-to-closing comment).
  A `---` or `<!-- … -->` that appears anywhere **above** the trailing block is preserved verbatim (a user may have intentionally pasted one inside a `[decision]` line). If the resulting section has no remaining non-blank lines, omit the `## Notes` heading from the PR body entirely. Preserve every other line including the timestamped `[test]` / `[done]` / `[done-forced]` / `[workflow]` / `[approach]` / `[decision]` / `[blocked]` entries — that audit trail is the whole point.

Do **not** insert section headings that have no content.

### Summary synthesis

The `## Summary` paragraph is built from these three sources, in priority order:

1. **Issue title** — always available.
2. **`## What`** — copy the first paragraph (until the first blank line) as the structural backbone.
3. **Last `[approach]` line in `## Notes`** — if the user (or `/spirit:implement`) wrote one, splice the gist into the paragraph as "Approach: <gist>" or fold it inline. The line format is:
   ```
   - <YYYY-MM-DD>: [approach] <one-line description of the chosen approach>
   ```
   "Last" means **last in file order** (Notes are date-stamped only, not time-stamped, so file order is the canonical resolution for same-day duplicates). Later approach lines override earlier ones.

Fallback when sources are sparse:

- No `## What` content → Summary is the issue title used verbatim as a single sentence. Append `.` only if the title does not already end with sentence punctuation (`.`, `!`, `?`, `…`). Never paraphrase — preserve the exact title text, including non-English script and question marks like "...ได้ไหม?".
- No `[approach]` line → render Summary from title + `## What` without an Approach call-out. This is the **expected** path for `/solo:workflow`-driven PRs, which never write `[approach]` lines themselves.
- Both empty → Summary is the title alone, rendered per the rule above. The heading still appears (Summary is the only always-present section after `Closes`).

Note: the most recent `[done]` (from `/solo:done` step 4) or `[workflow]` (from `/solo:workflow` Stage E) line is part of the verbatim Notes copy, **not** the Summary. Don't double-render them.

Keep the paragraph **under ~120 words**. Never invent scope that isn't in the issue body — Wabi-Sabi: ship what's true, don't fabricate.

### Recognised `## Notes` tags

These bracketed tags carry meaning across solo commands. Spelled here so producers and consumers agree:

| Tag | Written by | Lands in body Notes? | Meaning |
|---|---|---|---|
| `[test]` | `/solo:test` step 6 | yes | Per-walk pass/fail/skip summary |
| `[done]` | `/solo:done` step 4 | yes | Outcome line from the close prompt |
| `[done-forced]` | `/solo:done --force` step 4 | yes | What slipped past the completion gate |
| `[workflow]` | `/solo:workflow` Stage E | yes | Auto-close audit (`auto-closed (N rounds, M commits)`) |
| `[approach]` | `/spirit:implement` Phase 5, or a manual comment / `## Notes` edit | yes | One-line description of the chosen approach, consumed by the Summary synthesis above |
| `[blocked]` | Manual — applied directly to the issue when work stalls | yes | Reason the issue was blocked |
| `[decision]` | Manual comment / `## Notes` edit | yes | A decision worth preserving in the body, not just the comment thread |

Every tag in the table lands in the body's `## Notes` section by design, so all of them survive the verbatim copy into the PR body. A line that does not start with a bracketed tag is fine — it just doesn't get special treatment by the synthesis logic above.
