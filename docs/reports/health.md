# Pipe health, as of 25/11/2026

Made by `scripts/health_report.py` from the view `changedesk.lane_health` (R15), the decide list (R16) and the lane growth flag (R17). Counts are items; a week runs Monday to Sunday. Every ticket is made up.

Made at the settings in the store on 25/11/2026: **36 hours a week**, small and quick 22.5%, standard 67.5%. Each past week's urgent hours beyond the buffer use the buffer of that week (changedesk.setting_num_at): 4 hours at 40 hours a week, 3.6 at 36.

## Each lane in the last complete week (16/11 to 22/11/2026)

| Lane | In | Out | Open at the end | Oldest open (days) | Past the age limit | Fixed dates met | Urgent hours beyond the buffer |
|---|---|---|---|---|---|---|---|
| Urgent | 2 | 1 | 1 | 0 |  |  | 0 |
| Fixed date | 1 | 0 | 4 | 67 |  | 0 of 0 |  |
| Small and quick | 5 | 4 | 9 | 84 | 5 |  |  |
| Standard | 3 | 4 | 19 | 123 | 2 |  |  |

## In against out, the last 6 complete weeks (in / out)

| Lane | 12/10 | 19/10 | 26/10 | 02/11 | 09/11 | 16/11 | Weeks running with more in than out |
|---|---|---|---|---|---|---|---|
| Urgent | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | **2 / 1** | 1 |
| Fixed date | 0 / 0 | 1 / 1 | 1 / 1 | 0 / 0 | 0 / 0 | **1 / 0** | 1 |
| Small and quick | 7 / 7 | **7 / 6** | 7 / 8 | 9 / 10 | **3 / 2** | **5 / 4** | 2 |
| Standard | 3 / 3 | 0 / 2 | 3 / 3 | **3 / 2** | **6 / 3** | 3 / 4 | 0 |

Bold: more in than out that week.

## Lane growth flag (R17): more in than out, 3 weeks running

No lane is flagged: none took in more than it put out for 3 complete weeks running. Urgent 1; Fixed date 1; Small and quick 2; Standard 0 weeks running now.

Over all 12 complete weeks: Urgent 5 in, 4 out; Fixed date 8 in, 4 out; Small and quick 75 in, 72 out; Standard 38 in, 37 out.

## The decide list (R16): 7 items, 4 past their lane's age limit and 3 past their fixed date

| Item | Lane | Why it is here | Age (days) | Limit | Days over |
|---|---|---|---|---|---|
| CD-0060 Seat count for the renewal on 27/10/2026 | Fixed date | its fixed date has passed | 64 | due 27/10/2026 | 29 |
| CD-0046 Test our automations before the platform release on 28/10/2026 | Fixed date | its fixed date has passed | 70 | due 28/10/2026 | 28 |
| CD-0089 Seat count for the renewal on 04/11/2026 | Fixed date | its fixed date has passed | 49 | due 04/11/2026 | 21 |
| CD-0035 Alert when Account records go stale | Small and quick | past the age limit | 76 | 30 | 46 |
| CD-0054 Cannot save one Lead record after the last update | Small and quick | past the age limit | 64 | 30 | 34 |
| CD-0086 Cannot save one Quote record after the last update | Small and quick | past the age limit | 49 | 30 | 19 |
| CD-0020 Refresh the test sandbox | Standard | past the age limit | 105 | 90 | 15 |

Each is decided on the n8n decide form: do it next, merge it, or close it with a reason. A fixed-date item whose date has passed is listed at once, whatever its age (a build addition to R16, Israel's decision of 25/11/2026): a person says whether it is still needed.

## Fixed dates still open

| Item | Due | Latest safe start | |
|---|---|---|---|
| CD-0060 Seat count for the renewal on 27/10/2026 | 27/10/2026 | 20/10/2026 | the date has passed |
| CD-0046 Test our automations before the platform release on 28/10/2026 | 28/10/2026 | 21/10/2026 | the date has passed |
| CD-0089 Seat count for the renewal on 04/11/2026 | 04/11/2026 | 28/10/2026 | the date has passed |
| CD-0149 Remove CRM access for a contractor whose contract ends on 4 December | 04/12/2026 | 27/11/2026 | at or past its latest safe start: planned first |
| CD-0159 Set up the new financial year before 1 January | 31/12/2026 | 24/12/2026 | not yet |

## This week's plan (week of 23/11/2026, plan plan-20261123-001854)

| Lane | Items | Hours |
|---|---|---|
| Urgent | 1 | 4 |
| Fixed date | 4 | 22 |
| Small and quick | 7 | 8.1 |
| Standard | 1 | 1.9 |

The working of every step: [week-plan.md](week-plan.md).

## The latest forecast, by lane (run fc-20261125T001928Z)

- **Urgent**: 1.3 hours a week arrive in the run and 1.4 are worked. Its 1 open items are done within 26 weeks in 100% of item-runs.
- **Fixed date**: 3.9 hours a week arrive in the run and 4.2 are worked. 5 open; average chance of the date 40%. Its 5 open items are done within 26 weeks in 100% of item-runs.
- **Small and quick**: 8.1 hours a week arrive in the run and 7.9 are worked; it takes in more than it puts out, so its queue grows and its wait gets longer. Service level: 85% of the small items that arrive in the run are done within 15 days. Under the old rule, 85% of small items were done within 3 days, but 7 of 74 were never done and are still waiting. Its 11 open items are done within 26 weeks in 100% of item-runs.
- **Standard**: 30.8 hours a week arrive in the run and 22.5 are worked; it takes in more than it puts out, so its queue grows. All 26 of its open items still get dates, because points for waiting lift them above new work; the new work behind them is the tail, and it waits longer and longer. Its 26 open items are done within 26 weeks in 100% of item-runs.

Every item's forecast: [forecast.md](forecast.md).

<details><summary>Every lane, every week</summary>

| Week | Lane | In | Out | Open | Oldest (days) | Past limit | Fixed due | Fixed met | Urgent beyond buffer |
|---|---|---|---|---|---|---|---|---|---|
| 31/08/2026 | Urgent | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 31/08/2026 | Fixed date | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 31/08/2026 | Small and quick | 5 | 6 | 5 | 31 | 1 | 0 | 0 | 0 |
| 31/08/2026 | Standard | 2 | 4 | 16 | 184 | 9 | 0 | 0 | 0 |
| 07/09/2026 | Urgent | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 07/09/2026 | Fixed date | 1 | 1 | 0 |  | 0 | 0 | 0 | 0 |
| 07/09/2026 | Small and quick | 4 | 3 | 6 | 38 | 1 | 0 | 0 | 0 |
| 07/09/2026 | Standard | 3 | 3 | 16 | 191 | 8 | 0 | 0 | 0 |
| 14/09/2026 | Urgent | 1 | 1 | 0 |  | 0 | 0 | 0 | 0 |
| 14/09/2026 | Fixed date | 1 | 0 | 1 | 4 | 0 | 0 | 0 | 0 |
| 14/09/2026 | Small and quick | 4 | 4 | 6 | 45 | 1 | 0 | 0 | 0 |
| 14/09/2026 | Standard | 2 | 2 | 16 | 198 | 9 | 0 | 0 | 0 |
| 21/09/2026 | Urgent | 1 | 1 | 0 |  | 0 | 0 | 0 | 1 |
| 21/09/2026 | Fixed date | 1 | 0 | 2 | 11 | 0 | 1 | 1 | 0 |
| 21/09/2026 | Small and quick | 10 | 9 | 7 | 28 | 0 | 0 | 0 | 0 |
| 21/09/2026 | Standard | 3 | 5 | 14 | 187 | 6 | 0 | 0 | 0 |
| 28/09/2026 | Urgent | 1 | 1 | 0 |  | 0 | 0 | 0 | 0 |
| 28/09/2026 | Fixed date | 0 | 0 | 2 | 18 | 0 | 0 | 0 | 0 |
| 28/09/2026 | Small and quick | 5 | 6 | 6 | 35 | 1 | 0 | 0 | 0 |
| 28/09/2026 | Standard | 4 | 3 | 15 | 194 | 5 | 0 | 0 | 0 |
| 05/10/2026 | Urgent | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 05/10/2026 | Fixed date | 2 | 1 | 3 | 25 | 0 | 0 | 0 | 0 |
| 05/10/2026 | Small and quick | 9 | 7 | 8 | 42 | 3 | 0 | 0 | 0 |
| 05/10/2026 | Standard | 6 | 3 | 18 | 156 | 5 | 0 | 0 | 0 |
| 12/10/2026 | Urgent | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 12/10/2026 | Fixed date | 0 | 0 | 3 | 32 | 0 | 0 | 0 | 0 |
| 12/10/2026 | Small and quick | 7 | 7 | 8 | 49 | 3 | 0 | 0 | 0 |
| 12/10/2026 | Standard | 3 | 3 | 18 | 158 | 4 | 0 | 0 | 0 |
| 19/10/2026 | Urgent | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 19/10/2026 | Fixed date | 1 | 1 | 3 | 39 | 0 | 0 | 0 | 0 |
| 19/10/2026 | Small and quick | 7 | 6 | 9 | 56 | 6 | 0 | 0 | 0 |
| 19/10/2026 | Standard | 0 | 2 | 16 | 165 | 4 | 0 | 0 | 0 |
| 26/10/2026 | Urgent | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 26/10/2026 | Fixed date | 1 | 1 | 3 | 46 | 0 | 3 | 1 | 0 |
| 26/10/2026 | Small and quick | 7 | 8 | 8 | 63 | 6 | 0 | 0 | 0 |
| 26/10/2026 | Standard | 3 | 3 | 16 | 164 | 3 | 0 | 0 | 0 |
| 02/11/2026 | Urgent | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 02/11/2026 | Fixed date | 0 | 0 | 3 | 53 | 0 | 1 | 0 | 0 |
| 02/11/2026 | Small and quick | 9 | 10 | 7 | 70 | 6 | 0 | 0 | 0 |
| 02/11/2026 | Standard | 3 | 2 | 17 | 171 | 2 | 0 | 0 | 0 |
| 09/11/2026 | Urgent | 0 | 0 | 0 |  | 0 | 0 | 0 | 0 |
| 09/11/2026 | Fixed date | 0 | 0 | 3 | 60 | 0 | 0 | 0 | 0 |
| 09/11/2026 | Small and quick | 3 | 2 | 8 | 77 | 6 | 0 | 0 | 0 |
| 09/11/2026 | Standard | 6 | 3 | 20 | 178 | 3 | 0 | 0 | 0 |
| 16/11/2026 | Urgent | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 16/11/2026 | Fixed date | 1 | 0 | 4 | 67 | 0 | 0 | 0 | 0 |
| 16/11/2026 | Small and quick | 5 | 4 | 9 | 84 | 5 | 0 | 0 | 0 |
| 16/11/2026 | Standard | 3 | 4 | 19 | 123 | 2 | 0 | 0 | 0 |
| 23/11/2026 | Urgent | 0 | 0 | 1 | 7 | 0 | 0 | 0 | 0 |
| 23/11/2026 | Fixed date | 1 | 0 | 5 | 74 | 0 | 0 | 0 | 0 |
| 23/11/2026 | Small and quick | 4 | 2 | 11 | 80 | 3 | 0 | 0 | 0 |
| 23/11/2026 | Standard | 8 | 1 | 26 | 130 | 2 | 0 | 0 | 0 |

</details>
