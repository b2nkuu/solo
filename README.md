<div align="center">
  <img src="assets/logo.png" alt="solo" width="200" />
  <h1>solo</h1>
</div>

Lightweight task management for solopreneurs using GitHub Issues, from inside Claude Code.

Capture an idea, work it, ship it, reflect on the week — all without opening the GitHub web UI.

## Why

You already use GitHub. You're working alone. You don't need a Jira clone — you need to add a task in 5 seconds, know what to do next in 5 seconds, and close it in 5 seconds. solo keeps the data in Issues (single source of truth) and gives you a small set of slash commands that do exactly that.

## Prerequisites

- [Claude Code](https://docs.claude.com/en/docs/claude-code)
- [`gh` CLI](https://cli.github.com) installed and authenticated:

  ```bash
  gh auth status   # must pass
  # if not:
  gh auth login
  ```

- A GitHub repository for the project.

## Install

Clone or symlink this directory and load it as a Claude Code plugin. Once installed, `/solo:*` commands appear in the slash menu.

## Quickstart

```bash
cd path/to/your-repo
```

In Claude Code:

```
/solo:init                                   # one-time: create labels + .solo/config.yml
/solo:capture "fix login redirect bug"       # captures to Inbox as type:bug
/solo:today                                  # see in-progress, suggested, blocked
/solo:start 42                               # flip to in-progress + create branch
/solo:test 42                                # walk the test plan, tick what passes
/solo:done 42                                # close + record outcome
```

You don't need `/solo:init` to start capturing — `/solo:capture` works out of the box and creates any missing labels on demand.

## Commands

| Command | Purpose | Args |
|---|---|---|
| `/solo:capture` | Capture a task or idea to the Inbox | `"text"` |
| `/solo:today` | Show today's focus list | — |
| `/solo:start` | Mark in-progress + create branch (single issue) | `<issue#> [--force]` |
| `/solo:fast-track` | Capture + plan + start in one shot (size:xs / size:s only) | `"<title>" [<priority> <size>]` |
| `/solo:loop` | Run every planned issue end-to-end autonomously (start → implement → test → done + PR) | — |
| `/solo:test` | Walk the test plan, run or verify each item, tick passed | `<issue#>` |
| `/solo:done` | Record outcome + close + open a rich PR (Summary + AC + Test Plan + Notes); refuses on unticked AC/Test Plan unless `--force` | `<issue#> [--force]` |
| `/solo:plan` | Triage the Inbox into planned work | — |
| `/solo:retro` | Reflect on closed work — cycle time + rework from issue metadata | `[<milestone> \| --since <date> \| --last <N>]` |
| `/solo:release` | Tag from trunk, generate notes, close milestone | `[--dry-run]` |
| `/solo:init` | Idempotent setup (labels + config) | — |
| `/solo:cleanup` | Sweep stale local branches + worktrees whose issue is closed / PR was merged | — |

## How it models work

- **State** is stored as GitHub Issue labels — no separate database.
- **Status** is mutually exclusive via `status:inbox`, `status:planned`, `status:in-progress`, `status:blocked`, `status:done` (the last one also closes the issue).
- **Type** is one of `type:feature`, `type:bug`, `type:task`, `type:idea`, `type:research`.
- **Priority** is `priority:high|medium|low`. **Size** is `size:xs|s|m|l|xl`. Set during `/solo:plan`.
- **Decisions** are lines prefixed `[decision]` in the issue body's `## Notes` section — write them directly (issue comment or body edit) and they survive into the PR body verbatim through `/solo:done`.

### Status stays in sync when PRs auto-close issues

When a PR with `Closes #<n>` merges, GitHub closes the issue but leaves the `status:*` label alone — so `status:in-progress` (or `status:blocked`) sticks around and the closed issue keeps showing up in `/solo:today` and `/solo:status` buckets it doesn't belong in. solo handles this two ways:

- **`/solo:done <n>` detects already-closed issues** — if the issue is already `CLOSED` when you run `/solo:done`, the command skips the close call but still swaps any existing `status:*` label to `status:done`. Safe when no `status:*` label is present.
- **Optional GitHub Actions workflow** — drop [`examples/workflows/solo-auto-flip-status.yml`](./examples/workflows/solo-auto-flip-status.yml) into your repo's `.github/workflows/` to flip the label automatically on every `issues.closed` event. Useful when you sometimes merge a PR and walk away without running `/solo:done`.

## Acceptance & Test Plan

Every issue body has an `## Acceptance` and `## Test Plan` section. They start blank from `/solo:capture` and stay out of your way until you're ready to think about the work.

- **At plan time.** `/solo:plan` asks once per item if you want it to suggest Acceptance Criteria and a Test Plan from the title, the `## What` line, and the issue's `type:*`. You can accept (`Y`), paste your own (`edit`), or skip — nothing is written without confirmation.
- **At start time.** `/solo:start` prints both sections after creating the branch so you see the goalposts and verification steps as you switch into the work.
- **At verify time.** `/solo:test <n>` walks the `## Test Plan` one item at a time, suggests a concrete way to verify each (a command to run, or "manual — verify yourself" for UI checks), and ticks what passes. Failures stay unticked and get a one-line note in `## Notes`. No status label changes — this is a verification pass, not a lifecycle step.
- **At close time.** `/solo:done` lists every remaining unticked checklist item alongside the outcome prompt and offers `Tick all? [Y/edit/n]` — the common "everything done" case is one keystroke; `edit` lets you tick a subset per section. If any AC or Test Plan item is still `- [ ]` after the prompt, `/solo:done` refuses to close — "closed" means the work and its verification both completed. Pass `--force` to override (e.g. an AC item that has genuinely gone obsolete); the slip is recorded in `## Notes` as `[done-forced]`.

The sections stay parseable Markdown checkboxes, so the issue page on GitHub doubles as the audit trail for what was promised, what was tested, and what shipped.

### Reflect (retro)

`/solo:capture → plan → start → test → done` covers intent through ship. `/solo:retro` closes the loop by looking **backward** across work that already shipped — so the next planning round starts from evidence, not memory.

It is read-only by default and invents no new data: it re-reads the `started` / `completed` metadata and the `[blocked]` / `[done-forced]` Notes that solo already wrote, then reports **cycle time** (per issue and averaged by size) and **rework signals** (how often work stalled or closed with items unticked). The closed Issues are the source of truth — no separate metrics store.

```
/solo:retro                       # default: current milestone, or the last 7 days
/solo:retro v0.4                  # everything in a milestone
/solo:retro --since 2026-06-20    # closed on or after a date
/solo:retro --last 10             # the 10 most-recently-closed issues
```

Run it per week, per milestone, or just before `/solo:release`. The aggregate report is chat-only; an opt-in prompt can stamp each issue with a `[retro]` note recording its own cycle time, keeping the reflection on the issue where the rest of its audit trail lives.

### xl breakdown

`/solo:plan` won't let `size:xl` items slip through silently. When you mark one xl, it offers a third option alongside `[k]eep` / `[s]kip`:

- `[b]reakdown` — generate 2–4 sub-issue proposals from the parent's `## What`, create the ones you pick as `status:planned` (with `Split from #<parent>` in their Notes), and optionally close the parent. The new sub-issues feed straight into the same AC + test plan pass as the originals.

This keeps the trunk-based rule "short-lived branches only" honest without adding a separate epic concept.

### Fast-track (xs/s only)

For truly trivial chores — a one-line version bump, a typo fix, a config tweak — the three-step `capture → plan → start` ceremony costs more than the work. `/solo:fast-track` collapses all three into one call:

```
/solo:fast-track "bump plugin.json to 2026.06.14" high xs
```

Result: a `type:task` issue created with `priority:high`, `size:xs`, and `status:in-progress` applied in a single labels call (no `status:inbox` intermediate), and the `chore/<n>-bump-plugin-json-to-2026-06-14` branch checked out off trunk. No AC/Test Plan generation prompt — the title is the acceptance criterion. Add detail mid-flight with `/solo:note <n> "..."` if needed.

- Args: `"<title>" [<priority> <size>]`. Defaults are `medium s` when omitted. Defaults never recover from a malformed arg — supply both or neither.
- Hard-scoped to `size:xs` / `size:s`. `size:m`, `size:l`, and `size:xl` are rejected with a one-liner pointing at `/solo:capture` + `/solo:plan`, so design pressure on larger work is preserved.
- All `/solo:start` preflight guards (dirty working tree, trunk out of sync, branch already exists) still fire — and they fire *before* issue creation, so a rejection never leaves an orphan issue behind.

### Autonomous loop

When the planned backlog is small but non-trivial — a typical solo sprint — there's no point driving one issue at a time. `/solo:loop` picks every `status:planned` issue in `milestone.current` and runs each one end-to-end through its full solo lifecycle in parallel:

```
/solo:loop
```

One pipeline per issue, all in parallel (capped at `loop.max_parallel`, default 4):

1. **Claim** — atomically flip `status:planned` → `status:in-progress`, create a `<prefix>/<n>-<slug>` branch off trunk (`feat`/`fix`/`chore` per type — see the Branch conventions section), and a dedicated worktree at `.solo/worktrees/<n>/`. Issues are claimed only as a slot frees up, so killing the loop mid-batch leaves uncalled issues untouched.
2. **Plan** — derive a subtask list from the issue's `## What` + `## Acceptance` + `## Test Plan`; refuse to proceed unless every Acceptance item is covered.
3. **Implement** — work the subtasks serially inside the issue's own worktree (no cross-issue file conflicts when other pipelines run in parallel).
4. **Verify** — walk `## Test Plan` like `/solo:test`, then run the repo-invariant `verify.commands` (if configured) inside the worktree; every hard command must exit `0`. Tick `[x]` for pass, loop back to Implement (up to `loop.max_retries`) for fail.
5. **Done + PR** — tick remaining AC, set `completed`, flip status to `done`, close the issue, push the branch, open a PR back to trunk. The worktree stays at `.solo/worktrees/<n>/` for you to inspect or clean.

Refusals are up front: empty source list, any `size:xl` in the batch, or any issue missing AC / Test Plan → batch aborts before mutating anything. Per-pipeline failures are isolated — one red issue does not kill the others, the failed issue flips to `status:blocked` with its worktree intact (so `/solo:today` surfaces it), and the green pipelines still close + PR. To pick up a red issue, `cd .solo/worktrees/<n>/` (the branch is already checked out there — no `git switch` needed) and continue with `/solo:test` / `/solo:done`.

`/solo:start <n>` (single-issue) is unaffected — it never fans out into parallel pipelines.

#### Unattended mode

Set `loop.auto_confirm: true` and `/solo:loop` runs without a human keypress — safe to drive from cron or GitHub Actions (`claude -p "/solo:loop"`). `auto_confirm` removes only the step-4 confirm; every safety gate still applies:

- **Refusals** (empty list, `size:xl`, missing AC/Test Plan) still abort the batch.
- **Author filter** — only issues authored by the repo owner or a collaborator enter the run, so a public-repo stranger can't feed instructions into an unattended agent. `/solo:plan` remains the human content gate.
- **`loop.max_issues_per_run`** (default 5) caps the batch per run, independent of `max_parallel`.
- **Hard verify gate** — a non-zero `verify.commands` exit fails the round; a missing toolchain fails fast as `env-missing` rather than burning retries.

Each pipeline posts its summary to `loop.report_issue`; red pipelines end at `status:blocked`. A ready-to-adapt schedule lives at [`examples/workflows/solo-nightly-loop.yml`](./examples/workflows/solo-nightly-loop.yml).

**Runner permissions.** The loop's token needs to push branches, edit issues, and open PRs — **never merge**. Enable branch protection on trunk so code lands only through a reviewed PR; in unattended mode this must be a mechanical guarantee, not a spec promise. Merging stays a human action.

## Configuration

`.solo/config.yml` is created by `/solo:init`:

```yaml
version: 1
repo: "owner/repo"

# Discussion language for generated prose (AC + Test Plan items, PR Summary).
# Default: "english" when unset. Accepts any freeform string (e.g. "thai", "en", "th").
language: "english"

defaults:
  inbox_label: "status:inbox"
  capture_type_guessing: true

branch:
  enabled: true
  pattern: "{prefix}/{issue}-{slug}"

note:
  storage: "comment"
  decision_prefix: "[decision]"

display:
  today_suggested_limit: 5
  date_format: "%Y-%m-%d"

# Milestone OKR summary (see Releases & milestones → OKRs).
okr:
  stale_days: 7                # /solo:today flags KRs not measured for more than this many days

# /solo:loop — all optional; shown with defaults.
loop:
  max_parallel: 4              # concurrent pipelines (soft cap)
  max_retries: 3               # implement→verify rounds per issue
  auto_confirm: false          # true → unattended: skip the confirm prompt (refusals still gate)
  max_issues_per_run: 5        # budget cap per unattended run
  report_issue: ""             # issue number where unattended run summaries are posted

# Repo invariants the loop's hard verify gate runs in each worktree (opt-in).
verify:
  commands: []                 # e.g. ["flutter analyze", "flutter test"] or ["npm run lint", "npm test"]
```

No secrets for the normal flow — auth is via `gh`. Unattended `/solo:loop` on a runner additionally needs `ANTHROPIC_API_KEY` (see the example workflow).

### Language

`language:` controls the language solo uses when it generates fresh user-facing prose:

- `/solo:plan` — AC + Test Plan suggestions are written in this language.
- `/solo:done` — the PR body's `## Summary` paragraph is written in this language.

Default behavior when the field is unset or missing is identical to today: English.

**Section headings stay English regardless.** `## What`, `## Acceptance`, `## Test Plan`, `## Notes`, `## Summary`, and the `Closes #<n>` line are part of solo's parser contract — they never translate. Technical English terms (file paths, identifiers, command names, code) also stay verbatim. Only the prose inside the items / paragraph is generated in the configured language.

Verbatim content is not retranslated. `/solo:done` copies the issue's `## Acceptance`, `## Test Plan`, and `## Notes` blocks into the PR body as-is — whatever language they were written in is the language they ship in. Existing issues + PRs are never rewritten by changing `language:`.

## Trunk-based development

solo assumes [trunk-based development](https://trunkbaseddevelopment.com/) — a single long-lived `trunk` branch (`main` by default) and short-lived, small feature branches that merge back fast. The plugin bakes the principles in:

- **Branch from trunk, always.** `/solo:start` updates `trunk` and branches off it — never off another feature branch.
- **Short-lived branches.** Target ≤ 2 days. `/solo:today` warns when an in-progress task is older than `trunk.max_branch_age_days` (configurable).
- **Small scope.** `/solo:plan` and `/solo:start` flag `size:xl` and suggest breakdown before work begins.
- **Ship fast.** `/solo:done` offers to push the branch and open a PR back to trunk in one step.
- **One issue → one branch → one PR.** No bundling of unrelated work. `/solo:today` warns with a soft `⚠` when the current branch's commits look drifted from the issue it's named for (zero title-keyword overlap, or a commit referencing a different `#issue`).
- **Feature flags > long branches.** For multi-week work, gate behind a flag and keep merging to trunk.

Configure the trunk name and branch-age threshold in `.solo/config.yml`:

```yaml
trunk:
  name: "main"
  max_branch_age_days: 2
```

### Branch conventions

solo uses five branch prefixes — aligned with Conventional Commits — so a glance at a branch name tells you what kind of work it carries:

| type label | prefix | What it's for |
|---|---|---|
| `type:feature` | `feat/` | New behaviour, observable to users |
| `type:bug` | `fix/` | Defect repair |
| `type:task`, `type:idea` | `chore/` | Specs, refactors, docs, misc plumbing |
| `type:research` | `spike/` | Exploration, time-boxed, may not ship |
| — | `release/` | Reserved for `/solo:release`'s manifest bump branch (`release/<version>`) |

Per-issue work branches are built from `{prefix}/{issue}-{slug}` (see the `branch.pattern` config). The `<prefix>` is resolved from the issue's `type:*` label at branch-creation time by `/solo:start` and `/solo:loop`. `release/<version>` is created only by `/solo:release` when a manifest bump is needed (see `commands/release.md` step 9) — it never carries an issue number.

If you set a custom `branch.pattern` that still uses the legacy `{type}` placeholder, the raw type name (`feature`, `bug`, `task`, …) is substituted for backward compatibility, but new repos should use `{prefix}`.

## Releases & milestones

solo treats a release as a **snapshot of trunk** — a git tag plus a GitHub Release. No release branches. Hotfixes are new commits on trunk with a new patch tag. Multi-week work that can't ship goes behind a feature flag, not a long-lived branch.

**Milestones group issues by intended release.** GitHub Milestones are the source of truth — solo just keeps `milestone.current` in `.solo/config.yml` pointing at the active one, so `/solo:capture` can attach it automatically.

### OKRs on a milestone

A milestone can carry an **Objective and Key Results** block right in its GitHub **description** — no new command, no new issue metadata. The description holds two headings, `## Objective` and `## Key Results`, and each KR is a checklist line in this exact form:

```markdown
## Objective
Ship a delightful dark mode that users keep switched on.

## Key Results
- [ ] KR1: weekly dark-mode active users — current: 120 / target: 500 (measured: 2026-07-01)
- [ ] KR2: accessibility contrast issues — current: 3 / target: 0 (measured: 2026-07-05)
```

The `current: <x> / target: <y>` fragment is what solo parses for progress, and `(measured: YYYY-MM-DD)` records when each number was last checked. **Updating a KR is just editing the milestone description directly** — tick the box or bump the numbers in GitHub; there's no `/solo:*` command that writes here.

Two nudges read this block (nothing else touches it):

- **`/solo:today`** shows a one-line KR summary under the milestone progress line — `🎯 v0.4: KR1 120/500 · KR2 3/0` — and appends `— ⏰ not measured for <N> days` when the oldest `measured:` date is more than `okr.stale_days` (default `7`) old. No block on the milestone → no line.
- **`/solo:release`** prints the KR block right before closing the milestone and asks once whether the final values are updated. It's a nudge, never a gate — the release proceeds regardless. A milestone landing at ~70% attainment usually means the targets were set right; a missed KR is data about scope, not a failure to block on.

### Flow

```
# Open v0.4 in GitHub (web UI or `gh api`), then point .solo/config.yml
# `milestone.current: "v0.4"` at it.
/solo:capture "add dark mode"          # → attached to v0.4
…
/solo:release --dry-run                # preview the tag + notes
/solo:release                          # tag, push, release, close v0.4
```

`/solo:release` will:

1. Refuse to run unless you're on trunk, working tree is clean, and trunk is in sync with `origin`.
2. Suggest the next version (patch bump from the latest tag, or `release.initial_version` if none).
3. Generate notes from issues closed since the previous tag, grouped by type (`Features`, `Fixes`, `Other`).
4. Tag, push, create a GitHub Release, close the chosen milestone, and offer to open the next one.

### Strict mode (default)

`milestone.required: true` is the default — every issue must carry a milestone, and `/solo:release` blocks if anything in the milestone is unfinished. Solo treats releases as the unit of work; tying issues to a milestone keeps that unit honest.

With `required: true` (default):

- `/solo:capture` refuses to create an issue when no active milestone is set.
- `/solo:plan` offers a backfill pass for any open issues missing a milestone.
- `/solo:today` warns loudly about issues without a milestone.
- `/solo:release` blocks if the milestone still has unfinished issues, or if any closed issue since the last tag has no milestone.

To opt out (looser flow — e.g. a personal scratch repo where you don't cut releases), flip the flag:

```yaml
milestone:
  current: "v0.4"
  required: false
```

With `required: false`, milestones are optional and `/solo:release` only warns about closed issues that slipped through without one.

### Migration

If you're upgrading an existing solo project:

1. Re-run `/solo:init` — it adds the `release:` and `milestone:` config blocks without touching the rest.
2. Create your first milestone in GitHub (web UI or `gh api repos/<owner/repo>/milestones -f title="v0.1"`), then set `milestone.current: "v0.1"` in `.solo/config.yml`.
3. Use `/solo:plan` to backfill milestones on existing open issues. Strict mode is on by default — `/solo:plan` will offer a backfill pass for anything missing a milestone.
4. Flip `milestone.required: false` only if you'd rather skip the discipline (looser flow without releases).

## Design philosophy

- **Frictionless capture.** One line in, one line out.
- **Single source of truth.** GitHub Issues hold the real state.
- **Terminal-first.** No browser needed for daily work.
- **Small surface area.** A few commands, each doing one thing well.
- **Trunk-based.** Short-lived branches, merged back fast (see above).
- **Tag, don't branch.** Releases are snapshots of trunk, not parallel lines of history.
- **Solo by design.** No team features, no assignment juggling.

## License

MIT — see [LICENSE](./LICENSE).
