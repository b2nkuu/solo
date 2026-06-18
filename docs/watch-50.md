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

## Decisions (window close)

Posted at the end of the watch window. One-line rationale per surface based on
observed invocations across the period.

| Surface | Decision | Rationale |
|---|---|---|
| `/solo:note` | **cut** | Not invoked during the window; `/solo:test` and `/solo:done` already write to `## Notes`, so the standalone command is redundant. |
| `/solo:week` | **cut** | Not invoked; solo sessions are bursty so a 7-day window rarely lines up, and `/solo:today` + git log cover the same ground. |
| `/solo:status` | **cut** | Not invoked; `/solo:today` covers the same snapshot for the only viewer (the solo user). |
| `/solo:block` | **cut** | No real blocker arose during the window; the label can be applied directly when one does. |
| `/solo:unblock` | **cut** | Paired with `/solo:block`; same zero trigger count. |
| `/solo:assistant` (skill) | **cut** | Never re-surfaced after install; natural-language routing belongs in the README, not a loaded skill prompt. |
| `/solo:how-to` (skill) | **cut** | Never invoked after first day; the README already lists every command. |
| `/solo:plan milestone` | **cut** | Not invoked; no milestone was opened or closed in the window. Milestone fields on `/solo:plan` and `/solo:capture` stay — only the sub-command goes. |

Flow-driving skills not on this list (`capture`, `plan`, `start`, `test`,
`done`, `release`, `today`, `init`, `workflow`, `cleanup`) are out of scope per
the issue's Acceptance — no removal without a separate discussion issue.

## Notes

- 2026-06-18 — Watch window opened. Eight surfaces above are under observation
  until 2026-07-02. Decision rubric per skill is in the issue body's "Proposed
  approach" section; one-line rationale per skill will be appended at window
  close.
- 2026-07-02 — Watch window closed. All eight surfaces marked **cut** above;
  zero invocations observed across the period. Trim PR to follow in the same
  branch.
