---
description: Run every planned issue end-to-end through an autonomous Workflow (start → implement → test → done + PR)
allowed-tools: [Bash, Workflow]
---

# /solo:workflow

Pick every `status:planned` issue in the current milestone and drive each one through its full solo lifecycle in parallel — claim, branch, plan, implement, verify, close, PR — with no further interaction. The work that `/solo:start` + `/solo:test` + `/solo:done` would do manually for a single issue, batched and unattended.

Use this after `/solo:plan` has set Acceptance + Test Plan on every backlog item and you want the planned slice to ship without sitting in front of it.

## Cache lag awareness

The slash command body Claude sees is **injected at session start** and stays frozen until `/reload-plugins` or a new session. The on-disk version at `commands/workflow.md` (and the sibling `commands/start.md`, `commands/test.md`, `commands/done.md` that its pipeline stages mirror) may have moved on. If the disk version differs from the spec text you were handed, **prefer disk**. Before executing any step below, re-read `commands/workflow.md` from disk — and re-read the sibling command files whenever a pipeline stage delegates to their behaviour (Stage A mirrors start, Stage D mirrors test, Stage E mirrors done's PR-body appendix).

This matters most when `/solo:workflow` is being run inside the very session that just edited any of these specs — typical dogfood scenario for solo itself. Re-read on disk first, then run.

Long-term enforcement (when the user also runs spirit): the dogfood verification step is tracked in `b2nkuu/spirit#9` — Phase 6 of `/spirit:implement` is expected to re-read disk + simulate the new behaviour automatically for any PR that touches `commands/*.md` or `skills/*/SKILL.md`. Until that ships, this "Cache lag awareness" section is the convention.

## When to reach for it

- Small planned backlog (typically 2–8 issues) that all have AC + Test Plan filled.
- No `size:xl` items left — they belong in `/solo:plan` breakdown, not here.
- You're willing to review what each pipeline produced via PRs rather than commits-on-trunk.

For a single issue you want to drive yourself, use `/solo:start <n>` instead. `/solo:workflow` never accepts an issue number argument — it always operates on the planned slice.

## Input

`$ARGUMENTS` must be empty. If anything is passed, stop with `Usage: /solo:workflow (takes no arguments).`

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
  workflow:
    max_parallel: 4              # script-level soft cap on concurrent pipelines (see note)
    max_retries: 3               # implement→verify loop cap per issue
    worktree_root: ".solo/worktrees"   # relative to repo root
    plan_model: sonnet           # optional model overrides
    implement_model: sonnet
    verify_model: haiku
  ```

  **About `workflow.max_parallel`:** this is the **script-level soft cap** — the upper bound the orchestrator asks the Workflow tool to honour when scheduling pipelines. It is **distinct** from the Workflow runtime's own hard ceiling, which is roughly `min(16, cores - 2)` and applied unconditionally by the runtime regardless of what the script requests. The effective concurrency is `min(workflow.max_parallel, min(16, cores - 2), N)` where `N` is the source list size. Set `workflow.max_parallel` low to throttle yourself below the runtime cap (e.g. on a small laptop, or to leave headroom for other tools). Setting it above the runtime cap has no effect — the runtime cap wins.

### 2. Build the source list

```bash
gh issue list --repo <owner/repo> --state open --limit 200 \
  --json number,title,body,labels,milestone
```

Filter to issues that carry `status:planned`. Then:

- If `milestone.current` is set → keep only issues whose `milestone.title == milestone.current`.
- Otherwise → keep all planned issues.

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

Show the batch and ask once:

```
🤖 /solo:workflow — <N> issue(s):
   #<n1> [<priority>][<size>] <title>
   #<n2> [<priority>][<size>] <title>
   …
   parallel: <min(N, workflow.max_parallel)>   retries: <workflow.max_retries>   (runtime may further cap at min(16, cores-2))
   milestone filter: <milestone.current or "none">
   worktree root: <repo>/<workflow.worktree_root>
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

Stamp `claimed_at = <today YYYY-MM-DD>` **once, here, in the orchestrator process** — before any pipeline is spawned. This value is passed into every pipeline via the Workflow `args` (step 6) and is the literal string written to each issue's `started:` metadata in Stage A. Pipelines must **not** re-resolve "today" themselves — agent wall-clock can drift hours behind orchestrator wall-clock under heavy parallelism, and we want all claimed issues to read with the same `started:` date.

### 6. Invoke the Workflow tool

One Workflow call. Pass `{ source: <list>, repo, trunk, claimed_at, workflow }` via `args`. The script runs **one pipeline per issue**, all in `parallel()` (capped at `workflow.max_parallel`). Each pipeline is the end-to-end solo lifecycle for that one issue:

#### Pipeline stage A — Claim (atomic)

The orchestrator (script body, **not** an agent) does this synchronously per issue so the flip+branch+worktree creation is one logical step before any agent runs:

1. `gh issue edit <n> --remove-label status:planned --add-label status:in-progress` — atomic ownership flip.
2. Compute `branch = <prefix>/<n>-<slug>`. `<prefix>` is resolved from the `type:*` label per the conventional-commits mapping in `commands/start.md` step 5 — `feat` for `type:feature`, `fix` for `type:bug`, `chore` for `type:task`/`type:idea`, `spike` for `type:research`. `<slug>` comes from the title — lowercased, non-alphanumeric → `-`, collapse repeats, trim to ~40 chars.
3. `worktree_path = <repo>/<workflow.worktree_root>/<n>`.
4. `git worktree add "<worktree_path>" -b "<branch>" "<trunk>"` — branch + dedicated worktree created off the just-synced trunk.
5. Fetch the issue body, set `started: <claimed_at>` (the orchestrator-stamped value passed in via `args`, **not** a freshly resolved "today") and `branch: <branch>` in the `<!-- solo:metadata -->` block, `gh issue edit --body-file`.

If any step in Claim fails for a given issue, that issue's pipeline fails immediately with the partial state recorded. Other pipelines are unaffected.

**Crash safety:** an orchestrator killed before the `gh issue edit` flip leaves the issue as `planned`; killed after the flip but before worktree creation leaves the issue as `in-progress` with no worktree — that's the cost of an atomic flip we don't try to roll back. Re-runs of `/solo:workflow` will skip the issue (it's no longer `planned`), so the user fixes manually.

#### Pipeline stage B — Plan agent

`agent(prompt, { schema: SUBTASK_SCHEMA, model: workflow.plan_model })` invoked with `cwd: worktree_path` so it sees the same trunk snapshot the implement agent will edit. Reads the issue's `## What` + `## Acceptance` + `## Test Plan` and returns:

```json
{ "subtasks": [{ "id": "...", "summary": "...", "covers": [0, 2] }] }
```

`covers` is the list of `## Acceptance` indices each subtask satisfies. The orchestrator validates that every Acceptance index appears in at least one subtask's `covers`; on miss it re-prompts the agent **once** with the gap list. On a second miss this issue's pipeline fails with `plan-coverage-incomplete`.

#### Pipeline stage C — Implement agent

`agent(prompt, { model: workflow.implement_model })` invoked with `cwd: worktree_path` — works the subtasks serially in the issue's own worktree (no `isolation: 'worktree'` because we already gave it a dedicated worktree path). The agent's prompt instructs it to:

- Stay inside the worktree.
- Commit per subtask with a message that references the parent issue (`<subtask summary> (#<n>)`).
- Return `{ commits: ["<sha>", …], notes: "<one-line summary>" }`.

#### Pipeline stage D — Verify agent

`agent(prompt, { schema: VERIFY_SCHEMA, model: workflow.verify_model })` invoked with `cwd: worktree_path`. Walks the issue body's `## Test Plan` items in the spirit of `/solo:test` — proposes a check per item, runs it via Bash inside the worktree, and returns:

```json
{ "results": [{ "index": 0, "passed": true, "evidence": "..." }] }
```

Then the orchestrator decides:

- **All passed** → continue to stage E (Done).
- **Any failed** AND retry count < `workflow.max_retries` → loop back to stage C with only the failing Test Plan indices in the implement prompt. Bump retry counter.
- **Any failed** AND retry exhausted → pipeline fails with the unticked indices + last evidence.

#### Pipeline stage E — Done + PR

Orchestrator (synchronous, not an agent):

1. Rewrite the issue body so every `## Acceptance` and `## Test Plan` line that is `- [ ]` becomes `- [x]`.
2. Append to `## Notes`: `- <claimed_at>: [workflow] auto-closed (N implement→verify rounds, <commits> commits)`.
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
   Source data: the issue body **after** step 1-4 of this stage applied (ticks, `[workflow]` Notes line, `completed:` metadata). That way the PR mirrors what just shipped to the issue.
9. Return `{ status: "green", issue: <n>, branch, worktree_path, pr_url, rounds: <retry+1> }`.

If the PR call surfaces "a pull request already exists" (e.g. a previous failed re-run), fetch the URL with `gh pr view --repo <owner/repo> --head <branch> --json url -q .url` and use it.

#### Pipeline failure shape

Any stage failure returns `{ status: "red", issue: <n>, branch, worktree_path, reason, evidence }`. Failed pipelines leave the issue at `status:in-progress`, the worktree intact, and no PR — the user picks up manually from the worktree.

### 7. Summary

After the Workflow returns, print a per-issue summary:

```
🤖 /solo:workflow finished — <P> green / <F> red

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

### 8. Re-run safety

`/solo:workflow` is safe to re-run after partial failure:

- Green issues are already `status:done` and closed → out of the source filter.
- Red issues are `status:in-progress` → out of the source filter.
- Only fresh `status:planned` issues get picked up.

To retry a red issue end-to-end, manually flip it back: `gh issue edit <n> --remove-label status:in-progress --add-label status:planned`. The orchestrator will then create a new worktree (different branch suffix if the previous branch still exists) — you're expected to clean the old worktree yourself first with `git worktree remove`.

## Design constraints

- **One worktree per issue, user-facing.** `.solo/worktrees/<n>/` is the canonical place — survives Workflow lifecycle, the user can `cd` into it, branches are real local branches not Workflow-runtime throwaways. The implement agent gets a `cwd` to that path; it does **not** use `isolation: 'worktree'`.
- **Atomic claim, no rollback.** The status flip is the ownership token. We never try to "un-claim" on later failure — the issue stays `in-progress` with its worktree so the human can finish or recycle.
- **No batch-level mutation before per-pipeline claim.** Refusals (step 3) check everything up front; if any pipeline fails after, the rest still run.
- **Per-pipeline isolation, batch-level reporting.** One red pipeline does not abort the run. The summary surfaces every outcome with enough breadcrumbs (`worktree_path`, `pr_url`, failure stage) to pick up.
- **Solo skill semantics, not new ones.** Pipeline stages mirror `/solo:start` + `/solo:test` + `/solo:done` behaviour. If those commands evolve, this command's stages should evolve with them — keep them in sync.
