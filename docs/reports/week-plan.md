# The week's plan: week of 23/11/2026

Made by `scripts/plan_week.py` (a plain script, not a model; planner 1.0.0), plan `plan-20261123-001854`. Every ticket is made up.

## The settings it used (changedesk.settings)

| Setting | Value |
|---|---|
| Hours of work a week | 36 |
| Urgent buffer | 10% (3.6 hours) |
| Small and quick share | 22.5% (8.1 hours) |
| Standard share | 67.5% (24.3 hours) |
| Points for each week waited | 0.25 |
| Latest safe start | the due date less 7 days: the time fixed-date work has needed 85% of the time (4 done items in the work log, spans [7, 7, 7, 7] days) |

## The working, step by step (a hand check follows it line by line)

| Step | Hours it may take | Hours it took | Note |
|---|---|---|---|
| 1. Urgent, one at a time, oldest first | 3.6 | 4 | took 0.4 hours beyond the 3.6-hour buffer |
| 2. Fixed dates from their latest safe start (due date less 7 days) | 22 | 22 | 4 items at or past their latest safe start; 1 not yet |
| 3. Small and quick, 22.5% of the week, oldest first | 8.1 | 8.1 |  |
| 4. Standard, 67.5% of the week, by score plus age | 1.9 | 1.9 |  |
| 5. Unused hours flow to the other lanes | 0 | 0 | 0 hours left unplanned |
| **The week** | **36** | **36** | 0 hours left |

## The plan

| # | Item | Lane | Hours | Why it is here |
|---|---|---|---|---|
| 1 | CD-0148 Invoices stopped reaching the billing system this morning | Urgent | 4 | urgent: harm is growing now |
| 2 | CD-0060 Seat count for the renewal on 27/10/2026 | Fixed date | 10 | fixed date 27/10/2026 has passed; still open |
| 3 | CD-0046 Test our automations before the platform release on 28/10/2026 | Fixed date | 5 | fixed date 28/10/2026 has passed; still open |
| 4 | CD-0089 Seat count for the renewal on 04/11/2026 | Fixed date | 5 | fixed date 04/11/2026 has passed; still open |
| 5 | CD-0149 Remove CRM access for a contractor whose contract ends on 4 December | Fixed date | 2 | fixed date 04/12/2026: latest safe start 27/11/2026 |
| 6 | CD-0035 Alert when Account records go stale | Small and quick | 1 | small: the lane's reserved share, oldest first |
| 7 | CD-0054 Cannot save one Lead record after the last update | Small and quick | 1 | small: the lane's reserved share, oldest first |
| 8 | CD-0086 Cannot save one Quote record after the last update | Small and quick | 1.5 | small: the lane's reserved share, oldest first |
| 9 | CD-0128 Cannot save one Lead record after the last update | Small and quick | 1.5 | small: the lane's reserved share, oldest first |
| 10 | CD-0139 Typo on the quote document footer | Small and quick | 0.5 | small: the lane's reserved share, oldest first |
| 11 | CD-0145 Check who still uses their CRM seat | Small and quick | 1.5 | small: the lane's reserved share, oldest first |
| 12 | CD-0150 Add 'Partner referral' to the Lead Source list | Small and quick | 1.1 | small: the lane's reserved share, oldest first |
| 13 | CD-0016 Clean up duplicate Order records | Standard | 1.9 | do it next (decide list) |

## Open work not in this week's plan

| Lane | Items | Hours left |
|---|---|---|
| Urgent | 0 | 0 |
| Fixed date | 1 | 6 |
| Small and quick | 4 (and 1 planned in part) | 6.5 |
| Standard | 25 (and 1 planned in part) | 189.5 |

## Fixed dates already missed

3 fixed-date items are past their date and still open (CD-0046 due 28/10/2026, CD-0060 due 27/10/2026, CD-0089 due 04/11/2026). They were missed under the old rule, before the lanes. Past their latest safe start, the rule plans them at once. They are on the decide list (a build addition to R16, 25/11/2026): a person says whether each is still needed.
