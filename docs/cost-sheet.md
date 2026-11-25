# Cost sheet

Made by `scripts/cost_sheet.py` from the run log (`changedesk.run_log`) and the price table, through `docs/cost-sheet.json`. Every call the AI steps made is in it, failed ones too. No paid plan: calls are billed to the build's capped Claude key (workspace gtm-pipeline, US$10 monthly limit). Every request is made up.

## The cost of one triage and one update (R30)

- **One triage: US$0.000877** (Haiku 5.5; the average of 466 triage calls, the evals included).
- **One update: US$0.000789** (Haiku 5.5; the average of 28 update drafter calls). A drafting run for one forecast drafts one update for each reader: each requester with an item that moved, the manager and the executive.

## Every call, by step

| What | Model | Calls | Failed | Cost per call (US$) | Total (US$) | Average tokens in / out |
|---|---|---|---|---|---|---|
| Updates for three audiences (stage 5) | claude-haiku-5-5 | 28 | 1 | 0.000789 | 0.022084 | 3170 / 943 |
| Triage eval, the 40 tuned cases (stage 1, 3 playbooks x 3 rounds) | claude-haiku-5-5 | 363 | 2 | 0.000875 | 0.317463 | 6904 / 368 |
| Triage eval, the 30 fresh cases (stage 6, playbook 1.0.2 once, 3 rounds) | claude-haiku-5-5 | 90 | 0 | 0.000885 | 0.079685 | 7012 / 368 |
| Triage, run from the n8n form | claude-haiku-5-5 | 1 | 0 | 0.000870 | 0.000870 | 6977 / 345 |
| Triage, run by hand from Python | claude-haiku-5-5 | 12 | 0 | 0.000882 | 0.010585 | 7021 / 360 |
| Close message drafts (decide list) | claude-haiku-5-5 | 4 | 0 | 0.000169 | 0.000674 | 851 / 167 |
| Close message drafter probe, from Python (no draft stored) | claude-haiku-5-5 | 12 | 0 | 0.000168 | 0.002022 | 864 / 164 |

## The update drafter's runs (stage 5)

| Run | Drafter | Calls | Failed | Drafts that passed every check | Total (US$) |
|---|---|---|---|---|---|
| `up-20261125T001949Z` | 1.0.0 | 7 | 1 | 2 | 0.005976 |
| `up-20261125T002810Z` | 1.0.1 | 7 | 0 | 6 | 0.005488 |
| `up-20261125T002910Z` | 1.0.1 | 7 | 0 | 6 | 0.005605 |
| `up-20261125T003014Z` | 1.0.2 | 7 | 0 | 6 | 0.005016 |

All calls: 510, US$0.433383. One stage 1 eval run of about US$0.10 is not in the run log (lost to a path bug before its results were saved; stage 1 notes).

Prices used (per million tokens):

- claude-haiku-5-5: US$0.10 in, US$0.50 out (read 2026-11-23, https://platform.claude.com/docs/en/about-claude/pricing)
- claude-sonnet-5-5: US$2.00 in, US$10.00 out (read 2026-11-23, https://platform.claude.com/docs/en/about-claude/pricing)

Read from changedesk.call_cost (the run log with the price table) at 2026-11-25T01:14:40Z.
