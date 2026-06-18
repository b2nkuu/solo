# Watch window — issue #50 (trim unused solo skills)

Tracking the 2-week observation window committed to in issue #50's Acceptance
checklist item 1. Mirrored here in-repo so the watch period and per-skill
decisions live alongside the code that will be cut.

## Window

- **Start:** 2026-06-18
- **End:**   2026-07-02 (14 days, inclusive of start, exclusive of end)

## Skills under observation

| Surface | What it does | Hypothesis going in |
|---|---|---|
| `/solo:note` | Append a timestamped note to an issue | Overlaps with `/solo:test` + `/solo:done` writebacks |
| `/solo:week` | Past 7 days summary | Survey-only; rarely re-invoked solo |
| `/solo:status` | Project snapshot | Survey-only; overlaps `/solo:today` |
| `/solo:block` | Mark blocked with reason | Exception handler; fires only on real blockers |
| `/solo:unblock` | Resume a blocked task | Pair of `/solo:block` — same trigger |
| `/solo:assistant` (skill) | Natural-language → `/solo:*` suggestions | Discoverability helper; cold after day 1 |
| `/solo:how-to` (skill) | Onboarding / cheat-sheet | Discoverability helper; cold after day 1 |
| `/solo:plan milestone` | Milestone sub-command of `/solo:plan` | Unused — repo runs without milestones |

## Notes

- 2026-06-18 — Watch window opened. Eight surfaces above are under observation
  until 2026-07-02. Decision rubric per skill is in the issue body's "Proposed
  approach" section; one-line rationale per skill will be appended at window
  close.
