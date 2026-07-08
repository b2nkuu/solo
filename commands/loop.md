---
description: Run every planned issue end-to-end autonomously (start → implement → test → done + PR)
allowed-tools: [Bash, Task]
---

# /solo:loop

Pick every `status:planned` issue in the current milestone and drive each one through its full solo lifecycle in parallel — claim, branch, plan, implement, verify, close, PR — with no further interaction. The work that `/solo:start` + `/solo:test` + `/solo:done` would do manually for a single issue, batched and unattended.

Use this after `/solo:plan` has set Acceptance + Test Plan on every backlog item and you want the planned slice to ship without sitting in front of it.

## Cache lag awareness

The slash command body Claude sees is **injected at session start** and stays frozen until `/reload-plugins` or a new session. The on-disk version at `commands/loop.md` (and the sibling `commands/start.md`, `commands/test.md`, `commands/done.md` that its pipeline stages mirror) may have moved on. If the disk version differs from the spec text you were handed, **prefer disk**. Before executing any step below, re-read `commands/loop.md` from disk — and re-read the sibling command files whenever a pipeline stage delegates to their behaviour (Stage A mirrors start, Stage D mirrors test, Stage E mirrors done's PR-body appendix).

This matters most when `/solo:loop` is being run inside the very session that just edited any of these specs — typical dogfood scenario for solo itself. Re-read on disk first, then run.

Long-term enforcement (when the user also runs spirit): the dogfood verification step is tracked in `b2nkuu/spirit#9` — Phase 6 of `/spirit:implement` is expected to re-read disk + simulate the new behaviour automatically for any PR that touches `commands/*.md` or `skills/*/SKILL.md`. Until that ships, this "Cache lag awareness" section is the convention.

## When to reach for it

- Small planned backlog (typically 2–8 issues) that all have AC + Test Plan filled.
- No `size:xl` items left — they belong in `/solo:plan` breakdown, not here.
- You're willing to review what each pipeline produced via PRs rather than commits-on-trunk.

For a single issue you want to drive yourself, use `/solo:start <n>` instead. `/solo:loop` never accepts an issue number argument — it always operates on the planned slice.

## Input

`$ARGUMENTS` must be empty. If anything is passed, stop with `Usage: /solo:loop (takes no arguments).`

## Steps

### 1. Pre-flight + resolve repo

- `gh auth status` (stop on failure).
- Resolve repo from `.solo/config.yml`.
- Read knobs (all optional; defaults shown):

  ```yaml
  trunk:
    name: "main"
  milestone:
    current: "<name>"           # source filter
  loop:
    max_parallel: 4              # max concurrent implement/verify subagents (see note)
    max_retries: 3               # implement→verify loop cap per issue
    worktree_root: ".solo/worktrees"   # relative to repo root
    plan_model: sonnet           # optional model overrides
    implement_model: sonnet
    verify_model: haiku
    auto_confirm: false          # true → skip the step 4 prompt (unattended); step 3 refusals still gate
    max_issues_per_run: 5        # budget cap per run, independent of max_parallel
    report_issue: "<n>"          # unattended: post each issue's summary as a comment here (fallback: stdout)
  verify:
    commands:                    # repo invariants run in every worktree during Stage D — exit 0 required for all
      - "<lint/analyze cmd>"
      - "<test cmd>"
  ```

  **About `loop.auto_confirm` (unattended mode).** Default `false` — the step 4 confirm prompts as usual. Set `true` to run from a scheduler (`claude -p "/solo:loop"` via cron / GitHub Actions): step 4 skips the prompt entirely, but the step 3 refusals (empty list, `size:xl`, missing AC/Test Plan) remain hard gates that abort the batch. `auto_confirm` only removes the *human keypress*, never the safety checks.

  **About `verify.commands` (hard verify gate).** Optional list of repo-invariant commands (lint, type-check, test) run inside each issue's worktree during Stage D, **in addition** to walking that issue's `## Test Plan`. Division of labour: `## Test Plan` = per-issue acceptance conditions; `verify.commands` = repo-wide invariants every change must satisfy. All commands must exit `0` or the round fails (same retry loop as a failed Test Plan item). Missing `verify:` config → current behaviour, and the summary marks the issue `verified (test-plan only)`. See Stage D for the `env-missing` fast-fail rule.

  **About `loop.max_parallel`:** how many implement/verify `Task` subagents may run concurrently. The orchestrator keeps at most `loop.max_parallel` in flight as a **sliding window** — it fills up to the cap, and as soon as **any** one finishes it dispatches the next waiting issue, so effective concurrency is `min(loop.max_parallel, N)` where `N` is the source list size. Set it low on a small machine or to leave headroom for other work; there is no separate runtime ceiling to fight — the orchestrator honours this number directly. **Claim (Stage A) and Done+PR (Stage E) are always serial** — they touch the shared repo's git index/refs, so they run one-at-a-time in the orchestrator even while implement/verify agents fan out.

### 2. Build the source list

```bash
gh issue list --repo <owner/repo> --state open --limit 200 \
  --json number,title,body,labels,milestone,author
```

Filter to issues that carry `status:planned`. Then:

- If `milestone.current` is set → keep only issues whose `milestone.title == milestone.current`.
- Otherwise → keep all planned issues.

**Author filter (unattended safety rail).** Then keep only issues whose `author.login` is the repo owner or a repo collaborator — an unattended agent must never ingest instructions from a public-repo stranger's issue body. Resolve the allowed set once per run:

```bash
gh api "repos/<owner/repo>/collaborators?permission=push" --jq '.[].login'
```

Union that list with the repo owner. Drop any planned issue authored outside it and note the exclusion in the run summary (`excluded <k> issue(s): non-collaborator author`). `/solo:plan` is the human content gate; this filter is the mechanical backstop for the headless path. The filter applies in both modes, but it only matters when `auto_confirm: true` — an interactive run has a human at the step 4 prompt.

**Budget cap.** After filtering, if the list is longer than `loop.max_issues_per_run` (default 5), keep the first `max_issues_per_run` by the same priority-then-size order `/solo:today` uses, and note the deferral in the summary (`capped at <max>: <k> planned issue(s) deferred to next run`). This bounds cost per unattended run independently of `max_parallel` (which caps concurrency, not total).

### 3. Refusals (before any mutation)

Every refusal aborts the whole batch — no partial flips, no partial branches, no partial worktrees.

- Empty source list → stop with:
  ```
  No planned issues to run.
  ```
- Any issue carries `size:xl` → list them and stop:
  ```
  ⚠ size:xl in batch:
     #<n> <title>
     …
     Break them down with /solo:plan first.
  ```
- Any issue's body has no real Acceptance or Test Plan content — a section is "missing" only when the heading is absent **or** the section's only checklist line is the single empty `- [ ]` placeholder (same skippable heuristic as `/solo:done` step 3). A section with at least one real `- [ ]` or `- [x]` item counts as present. → list them and stop:
  ```
  ⚠ Missing AC or Test Plan:
     #<n> <title> (no AC)
     #<m> <title> (no Test Plan)
     …
     Run /solo:plan to fill them in.
  ```

### 4. Confirm

**When `loop.auto_confirm: true` (unattended): skip this step entirely** — print the batch block below for the log, then proceed straight to step 5 with no prompt. The step 3 refusals already gated the batch; the confirm keypress is the only thing `auto_confirm` removes.

Otherwise (default), show the batch and ask once:

```
🤖 /solo:loop — <N> issue(s):
   #<n1> [<priority>][<size>] <title>
   #<n2> [<priority>][<size>] <title>
   …
   parallel: <min(N, loop.max_parallel)>   retries: <loop.max_retries>
   milestone filter: <milestone.current or "none">
   worktree root: <repo>/<loop.worktree_root>
Start? [y/N]
```

Anything other than `y` (case-insensitive) → abort. The batch confirm is strict — Thai/informal tokens like `ครับ` / `ใช่` are **not** accepted here (the assistant skill's softer confirm vocabulary applies to skill-mediated conversations, not to this command's prompt).

### 5. Sync trunk

Once for the whole batch:

```bash
git fetch origin <trunk>
git switch <trunk>
git pull --ff-only
```

Fail-fast if trunk can't be brought clean — ask the user before any worktree is created.

Stamp `claimed_at = <today YYYY-MM-DD>` **once, here, in the orchestrator** — before any pipeline starts. The orchestrator holds this value and writes it verbatim into each issue's `started:` metadata in Stage A. Subagents must **not** re-resolve "today" themselves — agent wall-clock can drift hours behind orchestrator wall-clock under heavy parallelism, and we want all claimed issues to read with the same `started:` date. Pass `claimed_at` into any subagent prompt that needs it rather than letting the agent compute it.

### 6. Run the pipelines (main-loop orchestration)

The command's own session **is** the orchestrator — there is no separate runtime. It drives **one pipeline per issue** directly:

- **Git and GitHub steps run in the orchestrator via `Bash`/`gh`** — Stage A (claim + worktree) and Stage E (done + push + PR). These need a shell and touch the shared repo, so the orchestrator does them itself, **serially**, never inside a subagent and never in parallel.
- **The reasoning-heavy stages run as `Task` subagents** — Stage B (plan), C (implement), D.1 (verify) — each launched with `cwd` set to that issue's worktree. Up to `loop.max_parallel` of these run concurrently; the orchestrator dispatches, then awaits results.

> **Why not one background runtime call?** Claim/worktree/push/PR are `git`/`gh` shell commands. A subagent-less background script has no shell and cannot touch the filesystem, so those steps must run either in the orchestrator's own `Bash` (chosen here) or inside a `Task` subagent that has `Bash`. The orchestrator owns them directly: it keeps the atomic-claim and PR steps serial and lets only the implement/verify agents fan out. Do **not** try to push the whole pipeline into a single fire-and-forget call — the git steps will fail with no shell.

Concurrency model: iterate the source list; for each issue run Stage A serially (claim), then dispatch its Stage B→C→D subagents, keeping at most `loop.max_parallel` issues' agents in flight. As each issue's verify comes back green, run its Stage E serially (done + PR) before or alongside the next dispatch. Red pipelines record their failure and move on — one red never aborts the batch.

Each pipeline is the end-to-end solo lifecycle for one issue:

#### Pipeline stage A — Claim (atomic)

The orchestrator does this itself via `Bash`/`gh`, **serially** per issue, so the flip+branch+worktree creation is one logical step before any subagent runs:

1. `gh issue edit <n> --remove-label status:planned --add-label status:in-progress` — atomic ownership flip.
2. Compute `branch = <prefix>/<n>-<slug>`. `<prefix>` is resolved from the `type:*` label per the conventional-commits mapping in `commands/start.md` step 5 — `feat` for `type:feature`, `fix` for `type:bug`, `chore` for `type:task`/`type:idea`, `spike` for `type:research`. `<slug>` comes from the title — lowercased, non-alphanumeric → `-`, collapse repeats, trim to ~40 chars.
3. `worktree_path = <repo>/<loop.worktree_root>/<n>`.
4. `git worktree add "<worktree_path>" -b "<branch>" "<trunk>"` — branch + dedicated worktree created off the just-synced trunk.
5. Fetch the issue body, set `started: <claimed_at>` (the orchestrator-stamped value, **not** a freshly resolved "today") and `branch: <branch>` in the `<!-- solo:metadata -->` block, `gh issue edit --body-file`.

If any step in Claim fails for a given issue, that issue's pipeline fails immediately with the partial state recorded. Other pipelines are unaffected.

**Crash safety:** an orchestrator killed before the `gh issue edit` flip leaves the issue as `planned`; killed after the flip but before worktree creation leaves the issue as `in-progress` with no worktree — that's the cost of an atomic flip we don't try to roll back. Re-runs of `/solo:loop` will skip the issue (it's no longer `planned`), so the user fixes manually.

#### Pipeline stage B — Plan agent

A `Task` subagent (model `loop.plan_model`) launched with `cwd: worktree_path` so it sees the same trunk snapshot the implement agent will edit. Its prompt asks it to read the issue's `## What` + `## Acceptance` + `## Test Plan` and return, as its final message, a JSON object:

```json
{ "subtasks": [{ "id": "...", "summary": "...", "covers": [0, 2] }] }
```

`covers` is the list of `## Acceptance` indices each subtask satisfies. The orchestrator validates that every Acceptance index appears in at least one subtask's `covers`; on miss it re-prompts the agent **once** with the gap list. On a second miss this issue's pipeline fails with `plan-coverage-incomplete`.

#### Pipeline stage C — Implement agent

A `Task` subagent (model `loop.implement_model`) launched with `cwd: worktree_path` — works the subtasks serially in the issue's own worktree (the orchestrator already created a dedicated worktree, so the agent edits there directly). The agent's prompt instructs it to:

- Stay inside the worktree.
- Commit per subtask with a message that references the parent issue (`<subtask summary> (#<n>)`).
- Return `{ commits: ["<sha>", …], notes: "<one-line summary>" }`.

#### Pipeline stage D — Verify agent

Verification has **two halves**, both required to pass a round: the per-issue Test Plan walk, then the repo-invariant hard-command gate.

**D.1 — Test Plan walk.** A `Task` subagent (model `loop.verify_model`) launched with `cwd: worktree_path`. Walks the issue body's `## Test Plan` items in the spirit of `/solo:test` — proposes a check per item, runs it via Bash inside the worktree, and returns as its final message:

```json
{ "results": [{ "index": 0, "passed": true, "evidence": "..." }] }
```

**D.2 — Hard verify gate (`verify.commands`).** After the Test Plan walk, if `verify.commands` is configured, the orchestrator runs the commands with `cwd: <worktree_path>` (arbitrary shell — lint, type-check, test — not git subcommands), in listed order.

First, a **preflight resolvability probe**: for each configured command, check that its leading binary resolves (e.g. `command -v <bin>`). If any binary is unresolvable, the runner's toolchain is absent — fail the pipeline immediately with reason `env-missing` and the offending command, **without running anything and without burning a retry**. Retrying can't install a missing SDK; this is the one Stage D failure that skips the retry loop. Scoping the fast-fail to the preflight probe (not to "exit 127 anywhere") is deliberate: a `127` that surfaces *mid-run* — a sub-process the command itself invoked is missing — is a code/dependency bug the implement agent can fix, so it stays in the normal retry path below.

Once every binary resolves, run the commands in order:

- **Every command exits `0`** → the hard gate passes.
- **Any command exits non-zero** (including a mid-run `127`) → the gate fails. Capture the last ~20 lines of that command's combined stdout/stderr as evidence. This counts as a **failed round** — same retry loop as a failed Test Plan item (D.3 below), so stage C gets another attempt.
- **`verify.commands` unset** → skip D.2 entirely; the pipeline is verified on the Test Plan alone, and the summary marks the issue `verified (test-plan only)`.

`## Test Plan` = per-issue acceptance conditions; `verify.commands` = repo-wide invariants. Both must be green for the round to pass.

**D.3 — Round decision.** Combining D.1 and D.2:

- **Test Plan all passed AND hard gate passed (or unset)** → continue to stage E (Done).
- **Test Plan failure OR hard-gate non-zero exit** AND retry count < `loop.max_retries` → loop back to stage C with the failing Test Plan indices and/or the failing command's evidence in the implement prompt. Bump retry counter.
- **Same** AND retry exhausted → pipeline fails with the unticked indices + last evidence (`status:blocked` per the failure shape below).
- **`env-missing`** → immediate pipeline failure, no retry (see D.2).

#### Pipeline stage E — Done + PR

Orchestrator, via `Bash`/`gh`, **serial** per issue (never in a subagent):

1. Rewrite the issue body so every `## Acceptance` and `## Test Plan` line that is `- [ ]` becomes `- [x]`.
2. Append to `## Notes`: `- <claimed_at>: [loop] auto-closed (N implement→verify rounds, <commits> commits)`.
3. Set `completed: <claimed_at>` in metadata.
4. `gh issue edit --body-file` to apply body + metadata.
5. `gh label create status:done --force`; `gh issue edit --remove-label status:in-progress --add-label status:done`.
6. `gh issue close <n>`.
7. `git -C "<worktree_path>" push -u origin "<branch>"`.
8. Render the PR body per the **Appendix: PR body shape** at the bottom of `commands/done.md` — that appendix defines section order, omit rules, Summary synthesis, and the recognised-tags table. Single source of truth — Stage E and `/solo:done` step 8 produce identical bodies. Write the rendered Markdown to a temp file, then:
   ```
   gh pr create --repo <owner/repo> --base <trunk> --head <branch> \
     --title "<issue title>" \
     --body-file /tmp/solo-pr-<n>.md
   ```
   Source data: the issue body **after** step 1-4 of this stage applied (ticks, `[loop]` Notes line, `completed:` metadata). That way the PR mirrors what just shipped to the issue.
9. Record the pipeline outcome `{ status: "green", issue: <n>, branch, worktree_path, pr_url, rounds: <retry+1> }` in the orchestrator's results list for the step 7 summary.

If the PR call surfaces "a pull request already exists" (e.g. a previous failed re-run), fetch the URL with `gh pr view --repo <owner/repo> --head <branch> --json url -q .url` and use it.

#### Pipeline failure shape

Any stage failure records `{ status: "red", issue: <n>, branch, worktree_path, reason, evidence }` in the orchestrator's results list. Failed pipelines leave the worktree intact and open no PR — the user picks up manually from the worktree. **The issue is flipped `status:in-progress` → `status:blocked`** (`gh label create status:blocked --force`; swap the labels) so `/solo:today` surfaces it in the Blocked bucket instead of leaving a silently-stuck in-progress issue. The `reason` + last `evidence` are also written as a `- <claimed_at>: [blocked] <stage>: <reason>` line under the issue's `## Notes`, matching the manual-block convention so the audit trail is uniform. (Re-run safety still holds: `status:blocked` is out of the `status:planned` source filter.)

#### Pipeline persisted summary (unattended)

Under `loop.auto_confirm: true`, each pipeline — green **or** red — posts its own one-issue summary as a comment on the issue named by `loop.report_issue` (the same green/red lines step 7 would print for that issue, including `rounds` and any `verified (test-plan only)` marker). If `loop.report_issue` is unset, fall back to stdout only. This is the headless equivalent of the human reading step 7's terminal output: a scheduled run leaves its trail on GitHub where the owner will see it, and the per-issue round count makes cost patterns visible in the report issue over time. Under interactive mode (`auto_confirm: false`) nothing is posted — step 7's printed summary is enough.

### 7. Summary

After all pipelines finish, print a per-issue summary from the orchestrator's results list:

```
🤖 /solo:loop finished — <P> green / <F> red — <T> total implement→verify rounds

Green:
   #<n> <title>  →  PR <pr_url>  (worktree: <path>, <rounds> round(s))
   …

Red:
   #<n> <title>  →  worktree: <path>
      ✗ <stage>: <reason> — <evidence>
   …

Next:
- Review and merge green PRs (the green pipelines already pushed their branches and opened PRs — no extra branch checkout needed on your side).
- For red issues: `cd <worktree>` (e.g. `cd .solo/worktrees/<n>`), fix, `/solo:test <n>`, `/solo:done <n>`. The worktree already has the right branch checked out — you don't `git switch` into anything.
```

`<T>` is the sum of every pipeline's `rounds` (implement→verify attempts across the whole batch) — the headline cost signal. The same total rides along in the unattended per-issue comments posted to `loop.report_issue`, so cost patterns stay visible over successive scheduled runs.

### 8. Re-run safety

`/solo:loop` is safe to re-run after partial failure:

- Green issues are already `status:done` and closed → out of the source filter.
- Red issues are `status:blocked` (flipped by the failure shape) → out of the source filter.
- Only fresh `status:planned` issues get picked up.

To retry a red issue end-to-end, manually flip it back: `gh issue edit <n> --remove-label status:blocked --add-label status:planned`. The orchestrator will then create a new worktree (different branch suffix if the previous branch still exists) — you're expected to clean the old worktree yourself first with `git worktree remove`.

## Design constraints

- **One worktree per issue, user-facing.** `.solo/worktrees/<n>/` is the canonical place — created by the orchestrator (Stage A) and left in place after the run, so the user can `cd` into it; branches are real local branches, not throwaways. The implement and verify subagents get a `cwd` to that path — the worktree already exists, so no per-agent isolation is created or needed.
- **Atomic claim, no rollback to `planned`.** The status flip is the ownership token. We never "un-claim" back to `status:planned` on failure — a failed pipeline flips `in-progress` → `status:blocked` (surfaced by `/solo:today`), keeping its worktree so the human can finish or recycle. The one thing we never do is silently drop the issue back into the source pool.
- **No batch-level mutation before per-pipeline claim.** Refusals (step 3) check everything up front; if any pipeline fails after, the rest still run.
- **Per-pipeline isolation, batch-level reporting.** One red pipeline does not abort the run. The summary surfaces every outcome with enough breadcrumbs (`worktree_path`, `pr_url`, failure stage) to pick up.
- **Solo skill semantics, not new ones.** Pipeline stages mirror `/solo:start` + `/solo:test` + `/solo:done` behaviour. If those commands evolve, this command's stages should evolve with them — keep them in sync.
- **Unattended removes the keypress, never the gates.** `auto_confirm: true` skips only the step 4 confirm. Step 3 refusals, the author filter, the `max_issues_per_run` cap, the hard verify gate, and the human merge gate (PRs, never a merge) all still apply — an unattended run is the interactive run minus one prompt, not minus its safety.

## Non-goals

- **Automating `/solo:plan`.** The loop never generates Acceptance or Test Plan content. That quality is the human judgment the loop's correctness rests on — `/solo:plan` stays a human step, and the author filter + `status:planned` gate mean only human-curated issues ever enter an unattended run.
- **Changing the human merge gate.** Green pipelines push branches and open PRs; they never merge. Unattended mode must not gain merge rights — enable trunk branch protection so code lands only through a reviewed PR. In headless mode this is a mechanical guarantee, not a spec promise (see the README "Runner permissions" note).
