# The rule test: three order rules on the sample history

Made by `scripts/rule_test.py`; every week of every replay is planned by the planner's `plan_week()` (R13). Every ticket is made up: the figures show direction, not size.

**On the sample history (seed 172, 12 weeks, 159 requests):**

| Measure | Highest score first | Value per hour first | Lanes |
|---|---|---|---|
| Small items done | 91.1% | 100% | 100% |
| Oldest small item still waiting | 12 weeks | 0 weeks | 1.6 weeks |
| Fixed dates met | 40% | 100% | 100% |
| Oldest standard item still waiting | 17.6 weeks | 25.9 weeks | 8.9 weeks |
| Items open at the end | 30 | 17 | 31 |
| Value delivered (first column = 100) | 100 | 110 | 100 |

**The same test on the histories of seeds 163 to 172:** the median, with the lowest and highest in brackets.

| Measure | Highest score first | Value per hour first | Lanes |
|---|---|---|---|
| Small items done | 95.6% (89.6% to 100%) | 100% | 100% |
| Oldest small item still waiting | 10 weeks (0.4 weeks to 12 weeks) | 0 weeks | 1.2 weeks (0 weeks to 2.4 weeks) |
| Fixed dates met | 42.9% (0% to 80%), 9 of 10 seeds | 75% (0% to 100%), 9 of 10 seeds | 100%, 9 of 10 seeds |
| Oldest standard item still waiting | 28 weeks (17.6 weeks to 32.9 weeks) | 26.9 weeks (19.4 weeks to 35 weeks) | 10.2 weeks (8.7 weeks to 11.9 weeks) |
| Items open at the end | 24.5 (13 to 30) | 17 (11 to 21) | 26 (19 to 38) |
| Value delivered (first column = 100) | 100 | 106 (103 to 110) | 96.5 (93 to 101) |

Settings: the starting values in `settings/settings.json` (40 hours a week; urgent buffer 10%, small 20%, standard 70%; 0.25 points a week waited); latest safe start, the due date less 7 days. The "highest score first" replay gives back the history's own work log hour for hour on every history (11 of 11 checked).

## Each seed

| Seed | Fixed-date items | Rule | Small items done | Oldest small item still waiting | Fixed dates met | Oldest standard item still waiting | Items open at the end | Value delivered (first column = 100) |
|---|---|---|---|---|---|---|---|---|
| 163 | 3 | highest score first | 89.6% | 10 weeks | 0% | 21.6 weeks | 26 | 100 |
| 163 | 3 | value per hour first | 100% | 0 weeks | 0% | 21.6 weeks | 15 | 109 |
| 163 | 3 | lanes | 100% | 0 weeks | 100% | 8.7 weeks | 23 | 101 |
| 164 | 11 | highest score first | 96.6% | 6.4 weeks | 37.5% | 25.7 weeks | 25 | 100 |
| 164 | 11 | value per hour first | 100% | 0 weeks | 50% | 32.9 weeks | 20 | 107 |
| 164 | 11 | lanes | 100% | 1.9 weeks | 100% | 9.4 weeks | 38 | 93 |
| 165 | 8 | highest score first | 100% | 0.4 weeks | 80% | 26.4 weeks | 16 | 100 |
| 165 | 8 | value per hour first | 100% | 0 weeks | 100% | 26.4 weeks | 13 | 103 |
| 165 | 8 | lanes | 100% | 0.4 weeks | 100% | 8.9 weeks | 19 | 99 |
| 166 | 2 | highest score first | 96.4% | 12 weeks | none fell due | 27.6 weeks | 21 | 100 |
| 166 | 2 | value per hour first | 100% | 0 weeks | none fell due | 35 weeks | 17 | 105 |
| 166 | 2 | lanes | 100% | 1.4 weeks | none fell due | 10.9 weeks | 27 | 97 |
| 167 | 6 | highest score first | 98.1% | 7.9 weeks | 75% | 29.4 weeks | 13 | 100 |
| 167 | 6 | value per hour first | 100% | 0 weeks | 75% | 19.4 weeks | 11 | 103 |
| 167 | 6 | lanes | 100% | 1 weeks | 100% | 9.4 weeks | 21 | 96 |
| 168 | 10 | highest score first | 94.5% | 9.7 weeks | 42.9% | 28.4 weeks | 30 | 100 |
| 168 | 10 | value per hour first | 100% | 0 weeks | 28.6% | 34.4 weeks | 21 | 107 |
| 168 | 10 | lanes | 100% | 2.4 weeks | 100% | 11.9 weeks | 37 | 93 |
| 169 | 6 | highest score first | 97.8% | 11.7 weeks | 25% | 30 weeks | 17 | 100 |
| 169 | 6 | value per hour first | 100% | 0 weeks | 100% | 23.7 weeks | 14 | 105 |
| 169 | 6 | lanes | 100% | 1.6 weeks | 100% | 11.9 weeks | 25 | 95 |
| 170 | 11 | highest score first | 90.5% | 10 weeks | 55.6% | 28.4 weeks | 24 | 100 |
| 170 | 11 | value per hour first | 100% | 0 weeks | 77.8% | 27.4 weeks | 19 | 103 |
| 170 | 11 | lanes | 100% | 0 weeks | 100% | 11.4 weeks | 23 | 96 |
| 171 | 7 | highest score first | 94.7% | 11.7 weeks | 75% | 32.9 weeks | 29 | 100 |
| 171 | 7 | value per hour first | 100% | 0 weeks | 50% | 32.6 weeks | 21 | 109 |
| 171 | 7 | lanes | 100% | 0 weeks | 100% | 11.4 weeks | 27 | 99 |
| 172 | 7 | highest score first | 91.1% | 12 weeks | 40% | 17.6 weeks | 30 | 100 |
| 172 | 7 | value per hour first | 100% | 0 weeks | 100% | 25.9 weeks | 17 | 110 |
| 172 | 7 | lanes | 100% | 1.6 weeks | 100% | 8.9 weeks | 31 | 100 |

Fixed-date items per seed: [3, 11, 8, 2, 6, 10, 6, 11, 7, 7]. A seed with few fixed dates moves the "fixed dates met" figure a lot: one missed date out of three is 67%.
