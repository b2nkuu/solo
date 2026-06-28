---
description: Reflect on closed work — cycle time + rework from issue metadata
argument-hint: "[<milestone> | --since <YYYY-MM-DD> | --last <N>]"
allowed-tools: [Bash]
---

# /solo:retro

The **reflect** phase. solo already covers intent → plan → act → verify → ship; `/solo:retro` closes the loop by looking *backward* across work that already shipped, so the next `/solo:plan` round starts from evidence instead of memory.

It is read-only by default — it computes nothing new, only re-reads the `started` / `completed` metadata and the `[blocked]` / `[done-forced]` Notes that solo already wrote during the normal flow. No separate database, no new format: the GitHub Issues you closed are the source of truth, same as everywhere else in solo.

Unlike `/solo:today` (current, every day) or `/solo:test` / `/solo:done` (one issue, at close time), `/solo:retro` is cross-issue and periodic — run it at the end of a week, a milestone, or just before `/solo:release`.

## Steps

### 1. Pre-flight + resolve repo

- `gh auth status` (stop on failure).
- Resolve repo: `.solo/config.yml` `repo:` field → fallback `gh repo view --json nameWithOwner -q .nameWithOwner` → ask user.
- Read from `.solo/config.yml`: `milestone.current` (string), `trunk.max_branch_age_days` (default `2`), `display.date_format` (default `%Y-%m-%d`).

### 2. Resolve the range

Parse `$ARGUMENTS` (first recognised form wins):

- `--since <YYYY-MM-DD>` → issues closed on or after that date.
- `--last <N>` → the `N` most-recently-closed issues (by `closedAt`, descending).
- `<milestone>` (a bare token, not starting with `--`) → issues in that milestone.
- **Empty** → default: if `milestone.current` is set, use that milestone; otherwise fall back to `--since <7 days ago>`.

Anything else after a recognised form → warn `⚠ unknown arg: <token> (ignored)` and continue.

Echo the resolved range on the first output line so the user knows what window they are looking at (e.g. `range: milestone v0.4`, `range: since 2026-06-20`, `range: last 10 closed`).

### 3. Fetch closed issues

One call, then filter in memory:

```bash
gh issue list --repo <owner/repo> --state closed --limit 200 \
  --json number,title,body,labels,closedAt,milestone
```

Apply the step-2 filter:

- `--since` → keep issues whose `closedAt` date ≥ the given date.
- `--last N` → sort by `closedAt` desc, keep the first `N`.
- `<milestone>` / default-milestone → keep issues whose `milestone.title` matches.

If the filtered set is empty, print `📭 No closed issues in <range>.` and stop.

### 4. Extract metrics per issue

For each issue in range, read its `<!-- solo:metadata ... -->` block and `## Notes` section:

- **Cycle time** = `completed − started` in whole days, parsed from the metadata `started:` / `completed:` fields (both `YYYY-MM-DD`). A same-day close is `0`d, not blank.
  - Read each field's value from **its own line only** — `started:` with nothing after it is an *empty* value, not "the next field". A greedy pattern that lets `started:`'s value run past the end of the line will wrongly slurp `completed:` / `time_spent:` and either crash or fabricate a date. Anchor the match to the line (e.g. `^started:[ \t]*(\S*)[ \t]*$`).
  - If **either** field is empty or absent → the issue is **skipped** for cycle-time math (count it as skipped and remember its number; do not guess from `closedAt`, which can differ from the recorded `completed`).
- **Rework signal** — scan `## Notes` for the recognised tags (see `commands/done.md` "Recognised `## Notes` tags"):
  - `blocked` = count of `- <date>: [blocked] …` lines.
  - `forced` = count of `- <date>: [done-forced] …` lines.
- **Size** = the issue's `size:*` label (or `-` when absent), used to group cycle-time averages.

A skipped issue still contributes its rework counts — missing `started`/`completed` only blocks the cycle-time half, not the `[blocked]`/`[done-forced]` tally.

### 5. Render the report

Compact, no extra blank lines:

```
🔁 Retro (<range>)
   Analyzed: <N>   Skipped (no started/completed): <M>

   Cycle time:
     avg <X.X>d   ·   by size: xs <a>d · s <b>d · m <c>d · l <d>d · xl <e>d
     slowest: #<n> <X>d — <title>

   Rework:
     blocked: <B> across <k> issues
     done-forced: <F> across <j> issues
     #<n> ⚠ <B_n> blocked / <F_n> forced — <title>      ← one line per issue with B_n+F_n > 0
```

Rules:

- Omit a size bucket from the `by size` line when no analyzed issue carries that size.
- Drop the `slowest:` line when `N == 0` (everything was skipped).
- Drop the per-issue rework lines when every issue has `blocked == 0` and `forced == 0`; keep the two summary counts (they read `0 across 0 issues`).
- **Trunk-based nudge:** after the Rework block, for any analyzed issue whose cycle time exceeds `trunk.max_branch_age_days`, append:
  ```
   ⚠ <p> issues took longer than <trunk.max_branch_age_days>d — branches running long
  ```
  Skip this nudge when `trunk.max_branch_age_days` is `0` (disabled) or no issue exceeds it.

This render is the aggregate view and is **chat-only** — it is never written back to GitHub. The optional per-issue stamp in step 6 is the only thing that touches the issues.

### 6. Stamp the issues (opt-in)

After rendering, offer to record each analyzed issue's own metrics back onto it — keeping the audit trail on the issue where it already lives:

```
Stamp a [retro] note on <N> analyzed issues? [Y/n]
```

- `n` (or empty) → done, no writes. The report stays chat-only.
- `Y` → for each **analyzed** issue (skipped issues get no stamp — there is nothing to record), append one line to its `## Notes`:
  ```
  - <YYYY-MM-DD>: [retro] cycle <X>d · <B_n> blocked · <F_n> forced
  ```
  - `<YYYY-MM-DD>` = today, from `date +%Y-%m-%d`.
  - **Idempotency:** if an identical `[retro]` line (same date + same numbers) already exists in the issue's `## Notes`, skip that issue's write. Re-running `/solo:retro` the same day is a no-op, not a pile-up.
  - Use the same body-fetch / edit-in-place / `gh issue edit --body-file` pattern as `/solo:done`. Preserve every other line and the `<!-- solo:metadata -->` block exactly.
  - On a `gh` write failure for one issue, print a one-line warning and continue with the next — never abort the batch mid-way.

`[retro]` is a recognised Notes tag (see `commands/done.md`), so it survives the verbatim Notes copy into any future PR body — the reflection becomes part of the permanent record.

### 7. Confirm

```
🔁 Retro complete — <N> analyzed, <M> skipped.
   Stamped: <S>            ← only when step 6 was Y
```

Drop the second line when step 6 was `n`.

## Design constraints

- **Reuse, don't reinvent.** Every input is metadata solo already writes (`started`, `completed`, `[blocked]`, `[done-forced]`). No new store, no new format — Issues stay the single source of truth.
- **Read-only by default.** The aggregate report never mutates GitHub; only the opt-in step-6 stamp writes, and only after a `Y`.
- **Cross-issue, periodic.** This is the reflect phase — run it per week / milestone / pre-release, not per issue.
- **Honest skips.** An issue missing `started`/`completed` is reported as skipped, never silently dropped or guessed.
