# The forecast by lane (what-if: demand x 2)

Made by `scripts/forecast.py`, run `wi-20261125T003435Z`: 1000 runs of the 26 weeks from 23/11/2026, seed 163, new arrivals from each lane's own 12 weeks of history, at 2 times the usual demand. Every week of every run is planned by the planner's `plan_week()`, the same code as the week's plan. Every ticket is made up.

Made at these settings (changedesk.settings when the run was made): **36 hours a week**; urgent buffer 10%, small and quick 22.5%, standard 67.5%.

## Each lane

| Lane | Hours in a week (run) | Hours worked a week (run) | Takes in more than it puts out | |
|---|---|---|---|---|
| Urgent | 2.5 | 2.5 | no | 2.5 hours a week arrive in the run and 2.5 are worked. Its 1 open items are done within 26 weeks in 100% of item-runs. |
| Fixed date | 7.8 | 7.4 | **yes** | 7.8 hours a week arrive in the run and 7.4 are worked; it takes in more than it puts out, so its queue grows. All 5 of its open items still get dates, because points for waiting lift them above new work; the new work behind them is the tail, and it waits longer and longer. 5 open; average chance of the date 40%. Its 5 open items are done within 26 weeks in 100% of item-runs. |
| Small and quick | 16.3 | 8 | **yes** | 16.3 hours a week arrive in the run and 8 are worked; it takes in more than it puts out, so its queue grows and its wait gets longer. No service level can be given. Under the old rule, 85% of small items were done within 3 days, but 7 of 74 were never done and are still waiting. Its 11 open items are done within 26 weeks in 100% of item-runs. |
| Standard | 61.8 | 18 | **yes** | 61.8 hours a week arrive in the run and 18 are worked; it takes in more than it puts out, so its queue grows: 3 of its 26 open items get no 85% date (the tail). Its 26 open items are done within 26 weeks in 90% of item-runs. |

## Urgent

| Item | 50% | 85% | 95% | |
|---|---|---|---|---|
| CD-0148 Invoices stopped reaching the billing system this morning | 23/11/2026 | 23/11/2026 | 23/11/2026 |  |

## Fixed date

| Item | Due | Chance of the date | Latest safe start | 85% done by |
|---|---|---|---|---|
| CD-0046 Test our automations before the platform release on 28/10/2026 | 28/10/2026 | 0% | 21/10/2026 | 25/11/2026 |
| CD-0060 Seat count for the renewal on 27/10/2026 | 27/10/2026 | 0% | 20/10/2026 | 24/11/2026 |
| CD-0089 Seat count for the renewal on 04/11/2026 | 04/11/2026 | 0% | 28/10/2026 | 26/11/2026 |
| CD-0149 Remove CRM access for a contractor whose contract ends on 4 December | 04/12/2026 | 100% | 27/11/2026 | 26/11/2026 |
| CD-0159 Set up the new financial year before 1 January | 31/12/2026 | 100% | 24/12/2026 | 23/12/2026 |

## Small and quick

11 open small items; no date for each (KB-136 section 6.4). No service level: too many small items are not done within the horizon. The small and quick lane takes in more than it puts out in this run (16.3 hours a week arrive in the run and 8 are worked): no finish date is given for the tail.

## Standard

| Item | 50% | 85% | 95% | |
|---|---|---|---|---|
| CD-0016 Clean up duplicate Order records | 03/12/2026 | 03/12/2026 | 03/12/2026 |  |
| CD-0020 Refresh the test sandbox | 04/12/2026 | 04/12/2026 | 08/12/2026 |  |
| CD-0050 Pipeline report does not match finance's total | 08/12/2026 | 09/12/2026 | 09/12/2026 |  |
| CD-0049 Dashboard for the support backlog by queue | 09/12/2026 | 10/12/2026 | 10/12/2026 |  |
| CD-0073 Add the Team plan to the price book | 10/12/2026 | 10/12/2026 | 11/12/2026 |  |
| CD-0155 Pipeline-by-region report before the sales meeting on 2 December | 10/12/2026 | 11/12/2026 | 11/12/2026 |  |
| CD-0063 Forecast categories to match finance's definitions | 15/12/2026 | 17/12/2026 | 17/12/2026 |  |
| CD-0152 One dashboard for the support backlog by queue | 17/12/2026 | 18/12/2026 | 24/12/2026 |  |
| CD-1119 A queue for billing questions | 18/12/2026 | 25/12/2026 | 30/12/2026 |  |
| CD-1120 Agree field mapping and duplicate-match rules with marketing ops | 24/12/2026 | 29/12/2026 | 31/12/2026 |  |
| CD-0075 Tidy up admin rights | 30/12/2026 | 01/01/2027 | 07/01/2027 |  |
| CD-0090 Raise the discount that needs a director's approval | 01/01/2027 | 08/01/2027 | 15/01/2027 |  |
| CD-0099 Retire the old welcome-email workflow | 06/01/2027 | 14/01/2027 | 19/01/2027 |  |
| CD-1121 Build and configure the marketing platform connector to create Leads with campaign recorded | 08/01/2027 | 15/01/2027 | 22/01/2027 |  |
| CD-1122 Sandbox test with realistic data, duplicate check, and team guide | 12/01/2027 | 20/01/2027 | 27/01/2027 |  |
| CD-0078 Retire the old welcome-email workflow | 14/01/2027 | 27/01/2027 | 02/02/2027 |  |
| CD-0076 Dashboard for the support backlog by queue | 05/02/2027 | 19/02/2027 | 26/02/2027 |  |
| CD-0119 Pipeline report does not match finance's total | 17/02/2027 | 04/03/2027 | 12/03/2027 |  |
| CD-0121 Try a meeting-scheduler app from the marketplace | 10/03/2027 | 26/03/2027 | 07/04/2027 |  |
| CD-0133 Load event attendees from a spreadsheet | 26/03/2027 | 16/04/2027 | 29/04/2027 |  |
| CD-0141 Raise the discount that needs a director's approval | 08/04/2027 | 27/04/2027 | 07/05/2027 |  |
| CD-0107 Clean up duplicate Quote records | 14/04/2027 | 30/04/2027 | 13/05/2027 |  |
| CD-0120 Retire the old welcome-email workflow | 16/04/2027 | 06/05/2027 | 20/05/2027 |  |
| CD-0132 Load event attendees from a spreadsheet | no date | no date | no date | Not done within 26 weeks in too many runs: no 50%, 85%, 95% date. The standard lane takes in more than it puts out in this run (61.8 hours a week arrive in the run and 18 are worked): no finish date is given for the tail. |
| CD-0142 Lead source is lost when a Lead is converted | no date | no date | no date | Not done within 26 weeks in too many runs: no 50%, 85%, 95% date. The standard lane takes in more than it puts out in this run (61.8 hours a week arrive in the run and 18 are worked): no finish date is given for the tail. |
| CD-0156 The CRM is slow and annoying | no date | no date | no date | Not done within 26 weeks in too many runs: no 50%, 85%, 95% date. The standard lane takes in more than it puts out in this run (61.8 hours a week arrive in the run and 18 are worked): no finish date is given for the tail. |

## The update trigger (R20)

A what-if run triggers no update.
