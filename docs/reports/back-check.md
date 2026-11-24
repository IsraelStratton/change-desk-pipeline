# The back-check: the forecast from week 8 against what happened

Made by `scripts/back_check.py` from `sample/history.json`, with the forecast's own code (`planner.simulate`, `plan_week`, `forecast.forecast_rows`). Every ticket is made up: the figures show direction, not size.

Forecast from the end of week 8 (25/10/2026), by the rule the history was worked by (highest score first), 1000 runs, seed 163, compared with weeks 9 to 12:

- **Standard and urgent work: 4 of 4 items (100%) finished inside their 85% range** (done on or before their 85% date). 4 more are still open with an 85% date after week 12: not yet known.
- 7 standard items got no 85% date (the tail of a lane growing under the old rule): 7 of them were still open at the end of week 12.
- The other levels, as a check of the spread: 75% done by their 50% date (3 of 4); 100% done by their 85% date (4 of 4); 100% done by their 95% date (4 of 4).
- Fixed dates open at week 8: CD-0046 due 28/10, given a 0% chance, missed; CD-0060 due 27/10, given a 0% chance, missed; CD-0089 due 04/11, given a 0% chance, missed.
- Small items that arrived in weeks 9 to 12, against the forecast's service level (85% within 2 days): 18 of 24 (75%) were done within 2 days.

## Each item open at the end of week 8

| Item | Lane | 50% | 85% | 95% | Done | Verdict (85%) |
|---|---|---|---|---|---|---|
| CD-0046 Test our automations before the platform release on 28/10/2026 | Fixed date | no date | no date | no date | still open | chance 0%; missed |
| CD-0060 Seat count for the renewal on 27/10/2026 | Fixed date | 06/04/2027 | no date | no date | still open | chance 0%; missed |
| CD-0089 Seat count for the renewal on 04/11/2026 | Fixed date | no date | no date | no date | still open | chance 0%; missed |
| CD-0029 Two-minute guide to merging Opportunity records | Small and quick | | | still open | service level (below) |
| CD-0035 Alert when Account records go stale | Small and quick | | | still open | service level (below) |
| CD-0037 Check who still uses their CRM seat | Small and quick | | | still open | service level (below) |
| CD-0051 Typo on the quote document footer | Small and quick | | | 20/11/2026 | service level (below) |
| CD-0052 Check who still uses their CRM seat | Small and quick | | | 06/11/2026 | service level (below) |
| CD-0054 Cannot save one Lead record after the last update | Small and quick | | | still open | service level (below) |
| CD-0080 Order record shows the wrong Order type | Small and quick | | | 06/11/2026 | service level (below) |
| CD-0086 Cannot save one Quote record after the last update | Small and quick | | | still open | service level (below) |
| CD-0010 Route new Leads by region instead of round robin | Standard | 30/10/2026 | 11/11/2026 | 19/11/2026 | 03/11/2026 | inside |
| CD-0025 Create a renewal Opportunity 90 days before each contract ends | Standard | 06/11/2026 | 20/11/2026 | 01/12/2026 | 05/11/2026 | inside |
| CD-0009 A queue and escalation rule for billing questions | Standard | 20/11/2026 | 10/12/2026 | 25/12/2026 | 18/11/2026 | inside |
| CD-0048 Raise the discount that needs a director's approval | Standard | 27/11/2026 | 18/12/2026 | 07/01/2027 | 20/11/2026 | inside |
| CD-0073 Add the Team plan to the price book | Standard | 04/12/2026 | 29/12/2026 | 15/01/2027 | still open | not yet known |
| CD-0050 Pipeline report does not match finance's total | Standard | 31/12/2026 | 09/02/2027 | 12/03/2027 | still open | not yet known |
| CD-0049 Dashboard for the support backlog by queue | Standard | 07/01/2027 | 18/02/2027 | 19/03/2027 | still open | not yet known |
| CD-0063 Forecast categories to match finance's definitions | Standard | 12/02/2027 | 16/04/2027 | no date | still open | not yet known |
| CD-0016 Clean up duplicate Order records | Standard | no date | no date | no date | still open | no date, still open |
| CD-0020 Refresh the test sandbox | Standard | no date | no date | no date | still open | no date, still open |
| CD-0075 Tidy up admin rights | Standard | 23/04/2027 | no date | no date | still open | no date, still open |
| CD-0076 Dashboard for the support backlog by queue | Standard | no date | no date | no date | still open | no date, still open |
| CD-0078 Retire the old welcome-email workflow | Standard | no date | no date | no date | still open | no date, still open |
| CD-0090 Raise the discount that needs a director's approval | Standard | no date | no date | no date | still open | no date, still open |
| CD-0099 Retire the old welcome-email workflow | Standard | no date | no date | no date | still open | no date, still open |

Items a person closed or merged after week 8, left out: CD-0006.

## Each lane in the forecast

- **Urgent**: 1.5 hours a week arrive in the run and 1.5 are worked.
- **Fixed date**: 5.1 hours a week arrive in the run and 3.1 are worked; it takes in more than it puts out, so its queue grows: 3 of its 3 open items get no 85% date (the tail). 3 open; average chance of the date 0%. Its 3 open items are done within 26 weeks in 20% of item-runs.
- **Small and quick**: 8.4 hours a week arrive in the run and 8.5 are worked. Service level: 85% of the small items that arrive in the run are done within 2 days. Its 8 open items are done within 26 weeks in 94% of item-runs.
- **Standard**: 27.9 hours a week arrive in the run and 26.9 are worked; it takes in more than it puts out, so its queue grows: 8 of its 16 open items get no 85% date (the tail). Its 16 open items are done within 26 weeks in 59% of item-runs.
