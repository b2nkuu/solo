---
description: Walk through an issue's Acceptance + Test Plan, run or verify each item, tick what passes
argument-hint: "<issue-number>"
allowed-tools: [Bash]
---

# /solo:test

Walk through every item under `## Acceptance` **and** `## Test Plan` on an issue, decide per item (run a command, manual verify, fail, or skip), and tick what passed back into the body.

Use this after the work is done but before `/solo:done` — it converts both the promised acceptance criteria and the verification plan from intentions into a checked record of what was actually verified. AC and Test Plan get the same per-item rigor; closing should mean every promise + every verification was inspected one by one.

## Cache lag awareness

The slash command body Claude sees is **injected at session start** and stays frozen until `/reload-plugins` or a new session. The on-disk version at `commands/test.md` may have moved on (a recent PR to solo's own specs is the common case — e.g. the move from "walk TP only" to "walk AC + TP"). If the disk version differs from the spec text you were handed, **prefer disk**. Before executing any step below, re-read `commands/test.md` from disk and follow that copy.

This matters most when `/solo:test` is being run inside the very session that just edited `commands/test.md` — typical dogfood scenario for solo itself. Re-read on disk first, then walk.

## Input

`$ARGUMENTS` = issue number (no `#` prefix needed; tolerate it if given).

## Steps

### 1. Pre-flight + resolve repo

- `gh auth status` (stop on failure).
- Resolve repo as usual (`.solo/config.yml` → `gh repo view` → ask).

### 2. Read the issue

```bash
gh issue view <n> --repo <owner/repo> --json number,title,body,labels,state
```

- If the issue is already closed → friendly note `ℹ️  #<n> is closed.` and continue (user may be re-verifying).
- Parse both `## Acceptance` and `## Test Plan`. A section is **skippable** if it is missing or contains only the empty `- [ ]` placeholder.
- If **both** sections are skippable, stop with:
  ```
  ❌ #<n> has nothing to test — both Acceptance and Test Plan are empty. Run /solo:plan to generate them, or edit the issue body to add items.
  ```
- If only one section is skippable, walk only the non-skippable one and mention the skip in the header (step 3).

### 3. Show the plan

List the non-skippable sections in order — **Acceptance first, then Test Plan** — each with its own index restarting at `[1]`:

```
🧪 #<n> <title>
   Acceptance (<N> items)
     [1] [<x or space>] <ac item 1>
     [2] [<x or space>] <ac item 2>
     …
   Test Plan (<M> items)
     [1] [<x or space>] <tp item 1>
     [2] [<x or space>] <tp item 2>
     …
```

If a section was skipped because it was skippable, omit its block and add a single line like `(Acceptance is empty — skipping)` or `(Test Plan is empty — skipping)`.

### 4. Decide per section — batch first, then walk

For each non-skippable section (Acceptance first, then Test Plan), first try a batch decision (step 4-batch). If the user gives an empty input, fall through to the per-item walk (step 4a–4c). If the user gives an accepted batch verdict, skip the walk for that section.

#### 4-batch. Batch decision (optional)

Offer a batch decision **per section that will be walked**. Acceptance first, then Test Plan. For each non-skippable section, show:

```
Batch decision for <Section> (<N> items)? (e.g. "all:m", "all:s", "1,3:m, 2:f", or enter to walk one-by-one):
```

`<Section>` is `Acceptance` or `Test Plan`. `<N>` is the number of items in that section.

Parse the response. Whitespace around tokens is ignored. Accepted shapes:

- **Empty** (just enter) → fall through to the per-item walk (step 4a–4c) for this section. Today's behavior.
- **`all:<verb>`** — applies the same verb to every item in the section. Verb is one of:
  - `m` — mark every item pass (manual).
  - `s` — leave every item unchanged.
  - (No `all:f` and no `all:r` — failing or running everything in one shot is too dangerous; force per-item if the user wants that.)
- **Comma-grouped index decisions** — one or more groups separated by `,`. Each group is `<indices>:<verb>` where `<indices>` is one or more comma-joined integers (e.g. `1,3:m` or `2:f`). Verbs are `m`, `f`, or `s`. Every item in the section must appear in exactly one group; missing indices are treated as `s` only if the user did not list them — but if the parser sees any group at all, only listed indices are touched and the rest are left unchanged (effectively `s`).

  Concretely: groups are tokenized by splitting the input on `,` while respecting the `:verb` suffix. The simplest reliable parse: split on `,`, then walk tokens left-to-right; a token of the form `<int>:<verb>` closes the current pending group with that verb, while a bare `<int>` joins the pending group.

  Examples:
  - `1,3:m, 2:f` → group `[1,3]` verb `m`, group `[2]` verb `f`.
  - `1,3:m, 2,4:f, 5:s` → three groups.
  - `1:m, 2:m, 3:m` → three single-index groups, all `m`.

**Validation — re-prompt without writing on any of these:**

- Unknown verb anywhere (`all:x`, `1:z`, `all:f`, `all:r`).
- Malformed group (e.g. `1,3` with no `:verb`, `:m` with no index, trailing `,`, empty token).
- Out-of-range index (less than `1` or greater than `<N>`).
- Duplicate indices across groups (same item appears twice).
- Mixing `all:*` with index groups in the same input.

On invalid input, print one line such as:

```
↳ unknown decision — try "all:m", "all:s", "1,3:m, 2:f", or enter to walk.
```

and re-prompt for the same section. Do not edit the body and do not advance to the next section.

If the batch input is empty, proceed to step 4a–4c for this section. If a non-empty input is accepted, hold the parsed decision in memory (the apply rules live in step 4-batch-apply / 4-batch-fail) and skip 4a–4c for this section.

#### 4-walk. Walk items one at a time

If the batch step returned empty for this section, walk it one at a time. For each item, do steps 4a–4c. The prompt header in 4b should clarify which section the item belongs to.

Skip 4-walk entirely for any section that was fully resolved by a batch decision.

#### 4a. Suggest how to verify

Read the item text together with the issue title, `## What`, and `type:*` label. The suggestion depends on which section the item is in:

**For Acceptance items** — the question is "does the current implementation satisfy this AC?" Propose a way to **inspect the implementation**, not a test runner invocation:

- If the AC names a concrete behavior or symbol (e.g. `function X returns Y`, `endpoint /foo returns 200`, `CLI flag --bar is parsed`) → propose a `grep` / `rg` / code lookup that locates the relevant code. Examples:
  - `function shouldGate returns true when…` → `rg -n 'function shouldGate|shouldGate\s*=' <likely-dir>`
  - `/solo:done refuses to close when AC unticked` → `rg -n 'unticked|completion gate' commands/done.md`
  - `Endpoint /users requires auth` → `rg -n 'router\.(get|post).*users' src/`
- If the AC is inherently a UX/visual/manual promise (e.g. "error message is friendly", "UI shows green checkmark") → output `(manual — verify yourself)`.
- If you cannot infer a meaningful inspection → output `(no suggestion — choose manual or skip)`.

Do **not** propose `bun test ...`, `pytest`, `cargo test`, or other test-runner commands for AC items — that is Test Plan's job. AC verification is "look at the implementation and confirm it does the thing."

**For Test Plan items** — the question is "does running this verification pass?" Propose an executable command when possible:

- If the item names a concrete code path or behavior → propose a shell command (test runner, lint, type check, curl, etc.) that exercises it. Examples:
  - `Unit: serializer outputs correct columns` → `bun test src/serializer.test.ts` (use the project's actual test runner — read `package.json` / `Cargo.toml` / `pyproject.toml` if needed).
  - `Integration: hit endpoint with/without auth` → propose `curl` calls or the integration test file.
  - `Edge: empty users table → header only` → propose a test pattern flag or a `psql` snippet.
- If the item is inherently manual (UI clickthrough, observability check, design review) → output `(manual — verify yourself)` and skip the run option in the prompt.
- If you genuinely cannot infer a verification → output `(no suggestion — choose manual or skip)`.

Never invent file paths or commands that depend on tools the project clearly does not use.

#### 4b. Prompt

```
[<Section> <i>/<N>] <item text>
   suggested: <command or "(manual — verify yourself)">
   [r]un / [m]anual / [f]ail / [s]kip
```

`<Section>` is `AC` for Acceptance items, `TP` for Test Plan items. Omit `r` from the choices when there is no command to run.

- **r** — execute the suggested command via the Bash tool. Stream the result. Treat exit code `0` as pass, anything else as fail. Capture the last ~10 lines of combined stdout/stderr for the summary.
  - For AC items, `r` runs the proposed `grep` / `rg` / lookup. Treat a non-zero exit (no match) as fail — the user picked grep because they expected to see the implementation.
- **m** — the user confirms the check passed manually (no command run). Mark pass.
- **f** — the user confirms it failed. Prompt once: `Failure note (enter to skip):`. Mark fail.
- **s** — leave the item exactly as it was; do not change its tick state.

If the user provides a different command (e.g. they paste `bun test --watch ...` instead of `r`), execute that command and treat the result the same as `r`.

#### 4c. Record the per-item result

In memory, hold a tuple `(section, index, decision, note?)` for each item — `section` is `ac` or `tp`. Do not write to GitHub yet — batch the body edit at the end so a mid-walk abort leaves the issue clean.

### 5. Apply ticks

Fetch the body, rewrite **both** the `## Acceptance` block and the `## Test Plan` block in place (only the sections that were walked):

- For every item the walk marked `pass` (whether by `r` exit 0 or `m`), change `- [ ] ` to `- [x] ` in its own section.
- For `fail`, force the item to `- [ ] ` in its own section (untick it even if it was previously ticked — failing now is the truth).
- For `skip`, leave the line unchanged.

A failed AC item unticks the AC line; a failed TP item unticks the TP line. Never cross sections — index `2` in AC and index `2` in TP are independent.

Use the same body-fetch / edit-in-place / `gh issue edit --body-file` pattern as `/solo:start` and `/solo:done`.

### 6. Record a Notes entry

Append a single line under `## Notes` (one section edit, batched with step 5), summarising **both** sections in a single bullet:

```
- <YYYY-MM-DD>: [test] AC <P_ac> pass / <F_ac> fail / <S_ac> skip / TP <P_tp> pass / <F_tp> fail / <S_tp> skip
```

If a section was skipped because it was skippable, omit its half (e.g. `[test] TP 3 pass / 0 fail / 0 skip` when AC was empty; `[test] AC 4 pass / 0 fail / 1 skip` when TP was empty).

If `<F_ac> + <F_tp> > 0`, also append a sub-line per failure with the user's note (or `(no note)`), tagged with section + index so the failing item is unambiguous:

```
- <YYYY-MM-DD>: [test] AC 4 pass / 0 fail / 1 skip / TP 3 pass / 1 fail / 0 skip
  - failed [TP 2]: <failure note>
```

### 7. Summary

```
🧪 #<n>: AC <P_ac>/<N>, TP <P_tp>/<M>
```

`<N>` is total Acceptance items walked, `<M>` is total Test Plan items walked. Omit a half when its section was skippable (e.g. `🧪 #<n>: TP 3/3` when AC was empty).

If `<F_ac> + <F_tp> > 0`, add a second line nudging next steps:

```
   ↳ /solo:note <n> "[blocked] <reason>" if you're stuck, or fix and rerun /solo:test <n>.
```

If `<F_ac> + <F_tp> == 0` and every walked item is now ticked, add:

```
✅ Acceptance + Test Plan complete — ready for /solo:done <n>.
```

(Drop the missing half from that line too — e.g. `✅ Test Plan complete — ready for /solo:done <n>.` when only TP was walked.)

## Design constraints

- **Walk AC and TP with equal rigor.** Both are checkboxes the user promised. Both deserve per-item inspection before close.
- **AC suggestions look at implementation; TP suggestions run verifications.** Don't blur the two — AC asks "does the code do this?", TP asks "does this check pass?"
- **Never auto-run without `r`.** The user picks `r` explicitly per item or section; you do not chain runs across items.
- **Never tick fail items.** A failed step is the truth — surface it, regardless of which section it's in.
- **Batch the body write.** All ticks (both sections) + the Notes line go in one `gh issue edit --body-file` call after the walk.
- **Read-only on issue body until the end.** This makes `Ctrl-C` mid-walk safe.
- **Don't change `status:*` labels.** This command verifies; it does not advance the workflow. Use `/solo:done` to close.
