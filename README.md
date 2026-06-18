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
| `/solo:workflow` | Run every planned issue end-to-end through an autonomous Workflow (start → implement → test → done + PR) | — |
| `/solo:test` | Walk the test plan, run or verify each item, tick passed | `<issue#>` |
| `/solo:done` | Record outcome + close + open a rich PR (Summary + AC + Test Plan + Notes); refuses on unticked AC/Test Plan unless `--force` | `<issue#> [--force]` |
| `/solo:plan` | Triage the Inbox into planned work | — |
| `/solo:release` | Tag from trunk, generate notes, close milestone | `[--dry-run]` |
| `/solo:init` | Idempotent setup (labels + config) | — |
| `/solo:cleanup` | Sweep stale local branches + worktrees whose issue is closed / PR was merged | — |

## How it models work

- **State** is stored as GitHub Issue labels — no separate database.
- **Status** is mutually exclusive via `status:inbox`, `status:planned`, `status:in-progress`, `status:blocked`, `status:done` (the last one also closes the issue).
- **Type** is one of `type:feature`, `type:bug`, `type:task`, `type:idea`, `type:research`.
- **Priority** is `priority:high|medium|low`. **Size** is `size:xs|s|m|l|xl`. Set during `/solo:plan`.
- **Decisions** are lines prefixed `[decision]` in the issue body's `## Notes` section — write them directly (issue comment or body edit) and they survive into the PR body verbatim through `/solo:done`.

## Acceptance & Test Plan

Every issue body has an `## Acceptance` and `## Test Plan` section. They start blank from `/solo:capture` and stay out of your way until you're ready to think about the work.

- **At plan time.** `/solo:plan` asks once per item if you want it to suggest Acceptance Criteria and a Test Plan from the title, the `## What` line, and the issue's `type:*`. You can accept (`Y`), paste your own (`edit`), or skip — nothing is written without confirmation.
- **At start time.** `/solo:start` prints both sections after creating the branch so you see the goalposts and verification steps as you switch into the work.
- **At verify time.** `/solo:test <n>` walks the `## Test Plan` one item at a time, suggests a concrete way to verify each (a command to run, or "manual — verify yourself" for UI checks), and ticks what passes. Failures stay unticked and get a one-line note in `## Notes`. No status label changes — this is a verification pass, not a workflow step.
- **At close time.** `/solo:done` lists every remaining unticked checklist item alongside the outcome prompt and offers `Tick all? [Y/edit/n]` — the common "everything done" case is one keystroke; `edit` lets you tick a subset per section. If any AC or Test Plan item is still `- [ ]` after the prompt, `/solo:done` refuses to close — "closed" means the work and its verification both completed. Pass `--force` to override (e.g. an AC item that has genuinely gone obsolete); the slip is recorded in `## Notes` as `[done-forced]`.

The sections stay parseable Markdown checkboxes, so the issue page on GitHub doubles as the audit trail for what was promised, what was tested, and what shipped.

### xl breakdown

`/solo:plan` won't let `size:xl` items slip through silently. When you mark one xl, it offers a third option alongside `[k]eep` / `[s]kip`:

- `[b]reakdown` — generate 2–4 sub-issue proposals from the parent's `## What`, create the ones you pick as `status:planned` (with `Split from #<parent>` in their Notes), and optionally close the parent. The new sub-issues feed straight into the same AC + test plan pass as the originals.

This keeps the trunk-based rule "short-lived branches only" honest without adding a separate epic concept.

### Autonomous workflow

When the planned backlog is small but non-trivial — a typical solo sprint — there's no point driving one issue at a time. `/solo:workflow` picks every `status:planned` issue in `milestone.current` and runs each one end-to-end through its full solo lifecycle in parallel:

```
/solo:workflow
```

One pipeline per issue, all in parallel (capped at `workflow.max_parallel`, default 4):

1. **Claim** — atomically flip `status:planned` → `status:in-progress`, create a `<prefix>/<n>-<slug>` branch off trunk (`feat`/`fix`/`chore` per type — see the Branch conventions section), and a dedicated worktree at `.solo/worktrees/<n>/`. Issues are claimed only as a slot frees up, so killing the workflow mid-batch leaves uncalled issues untouched.
2. **Plan** — derive a subtask list from the issue's `## What` + `## Acceptance` + `## Test Plan`; refuse to proceed unless every Acceptance item is covered.
3. **Implement** — work the subtasks serially inside the issue's own worktree (no cross-issue file conflicts when other pipelines run in parallel).
4. **Verify** — walk `## Test Plan` like `/solo:test`; tick `[x]` for pass, loop back to Implement (up to `workflow.max_retries`) for fail.
5. **Done + PR** — tick remaining AC, set `completed`, flip status to `done`, close the issue, push the branch, open a PR back to trunk. The worktree stays at `.solo/worktrees/<n>/` for you to inspect or clean.

Refusals are up front: empty source list, any `size:xl` in the batch, or any issue missing AC / Test Plan → batch aborts before mutating anything. Per-pipeline failures are isolated — one red issue does not kill the others, the failed issue stays `status:in-progress` with its worktree intact, and the green pipelines still close + PR. To pick up a red issue, `cd .solo/worktrees/<n>/` (the branch is already checked out there — no `git switch` needed) and continue with `/solo:test` / `/solo:done`.

`/solo:start <n>` (single-issue) is unaffected — it never runs a Workflow.

## Configuration

`.solo/config.yml` is created by `/solo:init`:

```yaml
version: 1
repo: "owner/repo"

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
```

No secrets — auth is entirely via `gh`.

## Trunk-based development

solo assumes [trunk-based development](https://trunkbaseddevelopment.com/) — a single long-lived `trunk` branch (`main` by default) and short-lived, small feature branches that merge back fast. The plugin bakes the principles in:

- **Branch from trunk, always.** `/solo:start` updates `trunk` and branches off it — never off another feature branch.
- **Short-lived branches.** Target ≤ 2 days. `/solo:today` warns when an in-progress task is older than `trunk.max_branch_age_days` (configurable).
- **Small scope.** `/solo:plan` and `/solo:start` flag `size:xl` and suggest breakdown before work begins.
- **Ship fast.** `/solo:done` offers to push the branch and open a PR back to trunk in one step.
- **One issue → one branch → one PR.** No bundling of unrelated work.
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

Per-issue work branches are built from `{prefix}/{issue}-{slug}` (see the `branch.pattern` config). The `<prefix>` is resolved from the issue's `type:*` label at branch-creation time by `/solo:start` and `/solo:workflow`. `release/<version>` is created only by `/solo:release` when a manifest bump is needed (see `commands/release.md` step 9) — it never carries an issue number.

If you set a custom `branch.pattern` that still uses the legacy `{type}` placeholder, the raw type name (`feature`, `bug`, `task`, …) is substituted for backward compatibility, but new repos should use `{prefix}`.

## Releases & milestones

solo treats a release as a **snapshot of trunk** — a git tag plus a GitHub Release. No release branches. Hotfixes are new commits on trunk with a new patch tag. Multi-week work that can't ship goes behind a feature flag, not a long-lived branch.

**Milestones group issues by intended release.** GitHub Milestones are the source of truth — solo just keeps `milestone.current` in `.solo/config.yml` pointing at the active one, so `/solo:capture` can attach it automatically.

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
