---
description: Health check for this solo repo — config, labels, cache-lag, auth + orphans
allowed-tools: [Bash]
---

# /solo:doctor

A read-only diagnostic. `/solo:doctor` runs a fixed set of checks and prints one `✓ pass` / `⚠ warn` / `✗ fail` line per check, then a one-line summary. It answers "is this repo (and this install) set up the way solo expects?" without touching anything.

**Read-only invariant.** `/solo:doctor` **never mutates**. It creates no labels, edits no issues, writes no config, makes no git changes, and opens no PRs. Every check below is a pure read (`gh ... list`/`view`/`api`, `git ... --list`, file reads). If a check finds a problem it *reports the fix in prose* — it never applies it. Do not add a mutating step to this command.

Takes no arguments.

## Steps

### 1. Pre-flight + resolve repo

- Run `gh auth status`. On failure: record it as a **fail** for the auth check (step 5) and stop — nothing else can run without auth. Tell the user to run `gh auth login`.
- Resolve repo: `.solo/config.yml` `repo:` field → fallback `gh repo view --json nameWithOwner -q .nameWithOwner` → ask user. If the repo cannot be resolved at all, that is a **fail** for the auth check and the config check.
- Read `.solo/config.yml` in full — the config check (step 2), milestone checks (step 2, step 5), and everything downstream reuse this single read.

### 2. Config check — `.solo/config.yml`

Emit one or more lines under a **Config** group.

1. **Presence.** If `.solo/config.yml` does not exist → **fail**: `✗ config: .solo/config.yml missing — run /solo:init`. Skip the rest of this step.
2. **Required keys.** The file must have a top-level `repo:` and a `trunk.name:`. Missing either → **fail** naming the missing key (e.g. `✗ config: trunk.name missing`). These two are the minimum other commands assume.
3. **Milestone consistency** (only when the file parses and `milestone:` exists):
   - `milestone.required: true` **and** `milestone.current` unset or empty → **warn**: `⚠ config: milestone.required is true but milestone.current is empty — /solo:capture will refuse to create issues`.
   - `milestone.current` set **but** not an open milestone on the repo → **warn**: `⚠ config: milestone.current "<name>" is not an open milestone on <owner/repo>`. Check with:
     ```bash
     gh api "repos/<owner/repo>/milestones?state=open" \
       --jq '.[] | select(.title=="<milestone.current>") | .title'
     ```
     An empty result means no match. (This mirrors the same lookup `/solo:today` does for its `📦` line.)

If none of 1–3 tripped, emit `✓ config: .solo/config.yml valid (repo, trunk.name present)` plus, when milestones are configured cleanly, `✓ config: milestone.current "<name>" is open`.

### 3. Label check — canonical taxonomy

Fetch the repo's labels once and diff against the canonical solo set (the exact set `/solo:init` creates — keep these in sync with `commands/init.md`):

```bash
gh label list --repo <owner/repo> --limit 200 --json name -q '.[].name'
```

The canonical set (18 labels):

- `status:*` — `status:inbox`, `status:planned`, `status:in-progress`, `status:blocked`, `status:done`
- `type:*` — `type:feature`, `type:bug`, `type:task`, `type:idea`, `type:research`
- `priority:*` — `priority:high`, `priority:medium`, `priority:low`
- `size:*` — `size:xs`, `size:s`, `size:m`, `size:l`, `size:xl`

Under a **Labels** group:

- All 18 present → **pass**: `✓ labels: all 18 canonical labels present`.
- Any missing → **warn** (not fail — solo still works, but planning/capture chips break): `⚠ labels: N missing — <comma-list> — run /solo:init to create them`. List every missing label by exact name.

Extra labels beyond the canonical set are fine and never reported — this check only flags **missing** ones.

### 4. Cache-lag check (headline)

This is the check most likely to explain "I edited a command spec but `/solo:*` didn't change." `/solo:*` commands execute from the **installed plugin snapshot**, not from this working repo — so a merged/released spec change is not live until the plugin is updated and reloaded.

Compute three versions:

1. **Installed** — read `~/.claude/plugins/installed_plugins.json` and find the `solo@<owner>` entry (the plugins map key is `solo@<owner>`, e.g. `solo@b2nkuu`). Take that entry's `version` and `installPath`. If there is no solo entry, that is itself a **warn**: `⚠ cache-lag: solo not found in installed_plugins.json — is the plugin installed?`.
2. **Latest released tag** — `git tag --list --sort=-v:refname | head -1` in this working repo.
3. **Working manifest** — `.claude-plugin/plugin.json` `version` (the version this repo *would* publish).

Compare under a **Cache-lag** group:

Compare by **match, not by ordering** — the newest tag is whatever `git tag --sort=-v:refname | head -1` returns (that flag sorts version-aware, so it works for both `YYYY.MM.DD` CalVer and `vX.Y.Z` semver without any manual string comparison). Then:

- **Installed == latest tag** → **pass**: `✓ cache-lag: installed <version> matches latest release`.
- **Installed != latest tag** (a different — almost always newer — release exists than what's installed) → **warn** with the exact fix and the reason:
  ```
  ⚠ cache-lag: installed <installed> does not match latest release <tag>
      /solo:* runs from the installed snapshot, not this repo — a merged/released
      spec change is NOT live until you update the plugin.
      Fix:  /plugin        (update solo)
            /reload-plugins
      Verify it stuck: installed_plugins.json solo@<owner> now shows version <tag>
      at installPath .../solo/<tag>, and that installPath's commands/ dir reflects
      any renamed or added command specs.
  ```
- **Working manifest != latest tag** (this repo's `plugin.json` version is not among the tags — an unreleased bump waiting to ship) → **warn** (informational, distinct from the install lag): `⚠ cache-lag: working plugin.json <manifest> is not yet released (latest tag <tag>) — cut a release (/solo:release) so the change can be installed`.

Deliberately avoid manual `<`/`>` string comparison of versions — lexical ordering is wrong for semver (`v0.10.0` sorts before `v0.4.0`), and equality-vs-newest-tag is all this check needs. When a version can't be read (e.g. `version: "unknown"`, no tags yet), report a **warn** stating it couldn't be compared rather than guessing.

### 5. Auth + orphan check

Under an **Auth** group:

- `gh auth status` passed in step 1 and the repo resolved → **pass**: `✓ auth: gh authenticated, repo <owner/repo> resolves`. Otherwise the **fail** recorded in step 1 surfaces here (`✗ auth: gh auth status failed — run gh auth login`, or `✗ auth: could not resolve repo`).

Then fetch open issues once and report **orphans** under an **Issues** group:

```bash
gh issue list --repo <owner/repo> --state open --limit 200 \
  --json number,title,labels,milestone
```

- **No `status:*` label.** Count open issues whose `labels[].name` contains none of the five `status:*` labels. These are invisible to `/solo:today` and `/solo:plan` (both bucket by `status:*`). If the count is > 0 → **warn**: `⚠ issues: N open issue(s) with no status:* label (invisible to /solo:today, /solo:plan): #a, #b, …` (list the numbers). Zero → **pass**: `✓ issues: every open issue has a status:* label`.
- **No milestone** (only when `milestone.required: true`). Count open issues with `milestone == null`. If > 0 → **warn**: `⚠ issues: N open issue(s) with no milestone (milestone.required is true): #a, #b, …`. Zero → no line (the milestone-required "all good" case is covered by the config check's `✓`). When `milestone.required` is false, skip this sub-check entirely.

### 6. Summary

After all groups, print one summary line counting every `✓`/`⚠`/`✗` emitted above:

```
N passed · M warnings · K failures
```

Then a one-line verdict:

- `K > 0` (any failure) → `✗ solo has blocking issues — fix the failures above.`
- `K == 0` and `M > 0` → `⚠ solo is usable but has warnings.`
- `K == 0` and `M == 0` → `✓ solo is healthy.`

Keep the whole output compact — one line per check, grouped by the headings above, no extra blank lines beyond a single blank between groups. Nothing here writes back: `/solo:doctor` reports and stops.
