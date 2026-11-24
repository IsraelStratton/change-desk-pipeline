# Cost sheet

Made by `scripts/cost_sheet.py` from the run log (`changedesk.run_log`) and the price table. Every call the AI steps made is in it, failed ones too. No paid plan: calls are billed to the build's capped Claude key (workspace gtm-pipeline, US$10 monthly limit).

| What | Model | Calls | Cost per call (US$) | Total (US$) | Average tokens in / out |
|---|---|---|---|---|---|
| Triage eval (labelled requests) | claude-haiku-5-5 | 360 | 0.000875 | 0.314867 | 6903 / 369 |
| Triage, run by hand from Python | claude-haiku-5-5 | 12 | 0.000882 | 0.010585 | 7021 / 360 |

All calls: 372, US$0.325452.

Prices used (per million tokens):

- claude-haiku-5-5: US$0.10 in, US$0.50 out (read 2026-11-23, https://platform.claude.com/docs/en/about-claude/pricing)
- claude-sonnet-5-5: US$2.00 in, US$10.00 out (read 2026-11-23, https://platform.claude.com/docs/en/about-claude/pricing)

Every request is made up. The figures show direction, not size.
