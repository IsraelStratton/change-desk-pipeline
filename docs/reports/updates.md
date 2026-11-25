# The updates and the source of every figure: run up-20261125T003014Z

Made by `scripts/check_updates.py` (R23). Every figure in each update's subject and body is found by the code the drafter's own check uses (`engine/figures.js`), traced to a fact of the pack the update was drafted from, and the fact's source row is read again through `changedesk.fact_value`. For a requester, it also works out how each open item is answered (R25). Nothing here is sent to anyone: a person approves each update on the n8n approval form, and an approved update goes to the outbox table only. Every ticket is made up.

**7 updates, 173 figures: every figure found its row.**

| Update | For | Status | Figures | Check |
|---|---|---|---|---|
| `U-up-20261125T003014Z-req-account-executive` | Account executive (requester, status) | draft | 16 | every figure traced |
| `U-up-20261125T003014Z-req-billing-specialist` | Billing specialist (requester, status) | draft | 22 | every figure traced |
| `U-up-20261125T003014Z-req-campaign-manager` | Campaign manager (requester, status) | draft | 26 | every figure traced |
| `U-up-20261125T003014Z-req-finance-analyst` | Finance analyst (requester, status) | draft | 10 | every figure traced |
| `U-up-20261125T003014Z-req-head-of-operations` | Head of operations (requester, status) | draft | 34 | every figure traced |
| `U-up-20261125T003014Z-manager` | Desk manager (manager, status) | draft | 54 | every figure traced |
| `U-up-20261125T003014Z-executive` | Executive sponsor (executive, status) | draft | 11 | every figure traced |

## `U-up-20261125T003014Z-req-account-executive`

For **Account executive** (requester, status). Drafted by update_drafter from forecast run `fc-20261125T001928Z`. Status: **draft**.

> **Forecast update for your three open requests**
>
> Hello, Account executive. You have 3 items open. Each one is covered below.
>
> CD-0121: Try a meeting-scheduler app from the marketplace. We expect it between 29 January 2027 and 11 February 2027, and 85% likely by 5 February 2027. The 85% date has moved from 28 January 2027 to 5 February 2027.
>
> CD-0154: URGENT!!! New colour for the Opportunity page header. For small requests like this one, 85% are done within 15 days.
>
> CD-0157: Add a VIP checkbox to Accounts. For small requests like this one, 85% are done within 15 days.
>
> If the need has changed, you can raise a new request through the desk's intake form.

The drafter's code check found problems, so it can only be rejected: the drafter flagged possible_injection.

| Figure | Fact | Source row | Drafted | Now | |
|---|---|---|---|---|---|
| three | requests Account executive has open now | `requests` where status = Triaged or Planned or In progress, requester_role = Account executive: count of rows | 3 | 3 | ok |
| 3 | requests Account executive has open now | `requests` where status = Triaged or Planned or In progress, requester_role = Account executive: count of rows | 3 | 3 | ok |
| CD-0121 | CD-0121: the request id | `requests` where request_id = CD-0121: request_id | CD-0121 | CD-0121 | ok |
| 29 January 2027 | CD-0121: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0121: p50 | 2027-01-29 | 2027-01-29 | ok |
| 11 February 2027 | CD-0121: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0121: p95 | 2027-02-11 | 2027-02-11 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 5 February 2027 | CD-0121: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0121: p85 | 2027-02-05 | 2027-02-05 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 28 January 2027 | CD-0121: its 85% date in the last forecast | `forecasts` where run_id = fc-20261125T000231Z, request_id = CD-0121: p85 | 2027-01-28 | 2027-01-28 | ok |
| 5 February 2027 | CD-0121: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0121: p85 | 2027-02-05 | 2027-02-05 | ok |
| CD-0154 | CD-0154: the request id | `requests` where request_id = CD-0154: request_id | CD-0154 | CD-0154 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 15 | CD-0154: small requests like it are done within this many days, 85% of the time | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0154: service_level_days | 15 | 15 | ok |
| CD-0157 | CD-0157: the request id | `requests` where request_id = CD-0157: request_id | CD-0157 | CD-0157 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 15 | CD-0154: small requests like it are done within this many days, 85% of the time | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0154: service_level_days | 15 | 15 | ok |

Every open item answered (R25):

| Item | Answer | Answered |
|---|---|---|
| CD-0121 Try a meeting-scheduler app from the marketplace | date range, moved | yes |
| CD-0154 URGENT!!! New colour for the Opportunity page header | service level | yes |
| CD-0157 Add a VIP checkbox to Accounts | service level | yes |

## `U-up-20261125T003014Z-req-billing-specialist`

For **Billing specialist** (requester, status). Drafted by update_drafter from forecast run `fc-20261125T001928Z`. Status: **draft**.

> **Forecast update for your open Billing requests**
>
> Hello, Billing specialist. You have 5 items open. CD-0060 Seat count for the renewal on 27/10/2026: its due date, 27 October 2026, has passed. A person is deciding whether it is still needed. If it is, it is in this week's plan, the week of 23 November 2026. CD-0073 Add the Team plan to the price book: we expect it between 9 December 2026 and 10 December 2026, and 85% likely by 10 December 2026. CD-0139 Typo on the quote document footer: for small requests like this one, 85% are done within 15 days. CD-0141 Raise the discount that needs a director's approval: we expect it between 12 February 2027 and 26 February 2027, and 85% likely by 24 February 2027. The 85% date has moved from 11 February 2027 to 24 February 2027. CD-0148 Invoices stopped reaching the billing system this morning: it is in this week's plan, the week of 23 November 2026, and we expect it to be finished this week. If the need has changed, you can raise a new request through the desk's intake form.

| Figure | Fact | Source row | Drafted | Now | |
|---|---|---|---|---|---|
| 5 | requests Billing specialist has open now | `requests` where status = Triaged or Planned or In progress, requester_role = Billing specialist: count of rows | 5 | 5 | ok |
| CD-0060 | CD-0060: the request id | `requests` where request_id = CD-0060: request_id | CD-0060 | CD-0060 | ok |
| 27 October 2026 | CD-0060: the date it must be done by | `requests` where request_id = CD-0060: due_date | 2026-10-27 | 2026-10-27 | ok |
| 23 November 2026 | the Monday of the week this week's plan covers | `week_plan` where plan_id = plan-20261123-001854: min(week_start) | 2026-11-23 | 2026-11-23 | ok |
| CD-0073 | CD-0073: the request id | `requests` where request_id = CD-0073: request_id | CD-0073 | CD-0073 | ok |
| 9 December 2026 | CD-0073: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0073: p50 | 2026-12-09 | 2026-12-09 | ok |
| 10 December 2026 | CD-0073: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0073: p85 | 2026-12-10 | 2026-12-10 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 10 December 2026 | CD-0073: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0073: p85 | 2026-12-10 | 2026-12-10 | ok |
| CD-0139 | CD-0139: the request id | `requests` where request_id = CD-0139: request_id | CD-0139 | CD-0139 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 15 | CD-0139: small requests like it are done within this many days, 85% of the time | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0139: service_level_days | 15 | 15 | ok |
| CD-0141 | CD-0141: the request id | `requests` where request_id = CD-0141: request_id | CD-0141 | CD-0141 | ok |
| 12 February 2027 | CD-0141: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0141: p50 | 2027-02-12 | 2027-02-12 | ok |
| 26 February 2027 | CD-0141: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0141: p95 | 2027-02-26 | 2027-02-26 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 24 February 2027 | CD-0141: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0141: p85 | 2027-02-24 | 2027-02-24 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 11 February 2027 | CD-0141: its 85% date in the last forecast | `forecasts` where run_id = fc-20261125T000231Z, request_id = CD-0141: p85 | 2027-02-11 | 2027-02-11 | ok |
| 24 February 2027 | CD-0141: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0141: p85 | 2027-02-24 | 2027-02-24 | ok |
| CD-0148 | CD-0148: the request id | `requests` where request_id = CD-0148: request_id | CD-0148 | CD-0148 | ok |
| 23 November 2026 | the Monday of the week this week's plan covers | `week_plan` where plan_id = plan-20261123-001854: min(week_start) | 2026-11-23 | 2026-11-23 | ok |

Every open item answered (R25):

| Item | Answer | Answered |
|---|---|---|
| CD-0060 Seat count for the renewal on 27/10/2026 | passed date, on the decide list | yes |
| CD-0073 Add the Team plan to the price book | date range | yes |
| CD-0139 Typo on the quote document footer | service level | yes |
| CD-0141 Raise the discount that needs a director's approval | date range, moved | yes |
| CD-0148 Invoices stopped reaching the billing system this morning | this week | yes |

## `U-up-20261125T003014Z-req-campaign-manager`

For **Campaign manager** (requester, status). Drafted by update_drafter from forecast run `fc-20261125T001928Z`. Status: **draft**.

> **Forecast update for your three open requests**
>
> Hello, Campaign manager. You have 3 items open. Each item below gives our latest forecast.
>
> CD-0133: Load event attendees from a spreadsheet. We expect it between 5 February 2027 and 19 February 2027, and 85% likely by 17 February 2027. The 85% date moved from 5 February 2027 to 17 February 2027.
>
> CD-0132: Load event attendees from a spreadsheet. We expect it between 23 March 2027 and 9 April 2027, and 85% likely by 2 April 2027. The 85% date moved from 17 March 2027 to 2 April 2027.
>
> CD-0142: Lead source is lost when a Lead is converted. We expect it between 12 March 2027 and 1 April 2027, and 85% likely by 25 March 2027. The 85% date moved from 10 March 2027 to 25 March 2027.
>
> If the need has changed, you can raise a new request through the desk's intake form.

| Figure | Fact | Source row | Drafted | Now | |
|---|---|---|---|---|---|
| three | requests Campaign manager has open now | `requests` where status = Triaged or Planned or In progress, requester_role = Campaign manager: count of rows | 3 | 3 | ok |
| 3 | requests Campaign manager has open now | `requests` where status = Triaged or Planned or In progress, requester_role = Campaign manager: count of rows | 3 | 3 | ok |
| CD-0133 | CD-0133: the request id | `requests` where request_id = CD-0133: request_id | CD-0133 | CD-0133 | ok |
| 5 February 2027 | CD-0133: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0133: p50 | 2027-02-05 | 2027-02-05 | ok |
| 19 February 2027 | CD-0133: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0133: p95 | 2027-02-19 | 2027-02-19 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 17 February 2027 | CD-0133: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0133: p85 | 2027-02-17 | 2027-02-17 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 5 February 2027 | CD-0133: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0133: p50 | 2027-02-05 | 2027-02-05 | ok |
| 17 February 2027 | CD-0133: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0133: p85 | 2027-02-17 | 2027-02-17 | ok |
| CD-0132 | CD-0132: the request id | `requests` where request_id = CD-0132: request_id | CD-0132 | CD-0132 | ok |
| 23 March 2027 | CD-0132: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0132: p50 | 2027-03-23 | 2027-03-23 | ok |
| 9 April 2027 | CD-0132: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0132: p95 | 2027-04-09 | 2027-04-09 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 2 April 2027 | CD-0132: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0132: p85 | 2027-04-02 | 2027-04-02 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 17 March 2027 | CD-0132: its 85% date in the last forecast | `forecasts` where run_id = fc-20261125T000231Z, request_id = CD-0132: p85 | 2027-03-17 | 2027-03-17 | ok |
| 2 April 2027 | CD-0132: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0132: p85 | 2027-04-02 | 2027-04-02 | ok |
| CD-0142 | CD-0142: the request id | `requests` where request_id = CD-0142: request_id | CD-0142 | CD-0142 | ok |
| 12 March 2027 | CD-0142: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0142: p50 | 2027-03-12 | 2027-03-12 | ok |
| 1 April 2027 | CD-0142: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0142: p95 | 2027-04-01 | 2027-04-01 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 25 March 2027 | CD-0142: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0142: p85 | 2027-03-25 | 2027-03-25 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 10 March 2027 | CD-0142: its 85% date in the last forecast | `forecasts` where run_id = fc-20261125T000231Z, request_id = CD-0142: p85 | 2027-03-10 | 2027-03-10 | ok |
| 25 March 2027 | CD-0142: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0142: p85 | 2027-03-25 | 2027-03-25 | ok |

Every open item answered (R25):

| Item | Answer | Answered |
|---|---|---|
| CD-0133 Load event attendees from a spreadsheet | date range, moved | yes |
| CD-0132 Load event attendees from a spreadsheet | date range, moved | yes |
| CD-0142 Lead source is lost when a Lead is converted | date range, moved | yes |

## `U-up-20261125T003014Z-req-finance-analyst`

For **Finance analyst** (requester, status). Drafted by update_drafter from forecast run `fc-20261125T001928Z`. Status: **draft**.

> **Update on CD-0119: pipeline report forecast**
>
> Hello, Finance analyst.
>
> You have 1 item open with us now.
>
> CD-0119: Pipeline report does not match finance's total. We expect it between 21 January 2027 and 29 January 2027, and 85% likely by 28 January 2027. This has moved from 20 January 2027, the 85% date in the last forecast, to 28 January 2027.
>
> If the need for this has changed, you can raise a new request through the desk's intake form.

| Figure | Fact | Source row | Drafted | Now | |
|---|---|---|---|---|---|
| CD-0119 | CD-0119: the request id | `requests` where request_id = CD-0119: request_id | CD-0119 | CD-0119 | ok |
| 1 | requests Finance analyst has open now | `requests` where status = Triaged or Planned or In progress, requester_role = Finance analyst: count of rows | 1 | 1 | ok |
| CD-0119 | CD-0119: the request id | `requests` where request_id = CD-0119: request_id | CD-0119 | CD-0119 | ok |
| 21 January 2027 | CD-0119: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0119: p50 | 2027-01-21 | 2027-01-21 | ok |
| 29 January 2027 | CD-0119: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0119: p95 | 2027-01-29 | 2027-01-29 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 28 January 2027 | CD-0119: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0119: p85 | 2027-01-28 | 2027-01-28 | ok |
| 20 January 2027 | CD-0119: its 85% date in the last forecast | `forecasts` where run_id = fc-20261125T000231Z, request_id = CD-0119: p85 | 2027-01-20 | 2027-01-20 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 28 January 2027 | CD-0119: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0119: p85 | 2027-01-28 | 2027-01-28 | ok |

Every open item answered (R25):

| Item | Answer | Answered |
|---|---|---|
| CD-0119 Pipeline report does not match finance's total | date range, moved | yes |

## `U-up-20261125T003014Z-req-head-of-operations`

For **Head of operations** (requester, status). Drafted by update_drafter from forecast run `fc-20261125T001928Z`. Status: **draft**.

> **Forecast update for your 5 open requests**
>
> Hello, Head of operations. You have 5 requests open. CD-0099 Retire the old welcome-email workflow: We expect it between 29 December 2026 and 1 January 2027, and 85% likely by 31 December 2026. CD-0107 Clean up duplicate Quote records: We expect it between 17 February 2027 and 3 March 2027, and 85% likely by 25 February 2027. Our 85% date moved from 12 February 2027 to 25 February 2027. CD-0120 Retire the old welcome-email workflow: We expect it between 19 February 2027 and 5 March 2027, and 85% likely by 3 March 2027. Our 85% date moved from 17 February 2027 to 3 March 2027. CD-0145 Check who still uses their CRM seat: For small requests like this one, 85% are done within 15 days. CD-0156 The CRM is slow and annoying: We expect it between 10 March 2027 and 26 March 2027, and 85% likely by 19 March 2027. Our 85% date moved from 5 March 2027 to 19 March 2027. If the need has changed, you can raise a new request through the desk's intake form.

| Figure | Fact | Source row | Drafted | Now | |
|---|---|---|---|---|---|
| 5 | requests Head of operations has open now | `requests` where status = Triaged or Planned or In progress, requester_role = Head of operations: count of rows | 5 | 5 | ok |
| 5 | requests Head of operations has open now | `requests` where status = Triaged or Planned or In progress, requester_role = Head of operations: count of rows | 5 | 5 | ok |
| CD-0099 | CD-0099: the request id | `requests` where request_id = CD-0099: request_id | CD-0099 | CD-0099 | ok |
| 29 December 2026 | CD-0099: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0099: p50 | 2026-12-29 | 2026-12-29 | ok |
| 1 January 2027 | CD-0099: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0099: p95 | 2027-01-01 | 2027-01-01 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 31 December 2026 | CD-0099: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0099: p85 | 2026-12-31 | 2026-12-31 | ok |
| CD-0107 | CD-0107: the request id | `requests` where request_id = CD-0107: request_id | CD-0107 | CD-0107 | ok |
| 17 February 2027 | CD-0107: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0107: p50 | 2027-02-17 | 2027-02-17 | ok |
| 3 March 2027 | CD-0107: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0107: p95 | 2027-03-03 | 2027-03-03 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 25 February 2027 | CD-0107: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0107: p85 | 2027-02-25 | 2027-02-25 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 12 February 2027 | CD-0107: its 85% date in the last forecast | `forecasts` where run_id = fc-20261125T000231Z, request_id = CD-0107: p85 | 2027-02-12 | 2027-02-12 | ok |
| 25 February 2027 | CD-0107: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0107: p85 | 2027-02-25 | 2027-02-25 | ok |
| CD-0120 | CD-0120: the request id | `requests` where request_id = CD-0120: request_id | CD-0120 | CD-0120 | ok |
| 19 February 2027 | CD-0120: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0120: p50 | 2027-02-19 | 2027-02-19 | ok |
| 5 March 2027 | CD-0120: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0120: p95 | 2027-03-05 | 2027-03-05 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 3 March 2027 | CD-0107: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0107: p95 | 2027-03-03 | 2027-03-03 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 17 February 2027 | CD-0107: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0107: p50 | 2027-02-17 | 2027-02-17 | ok |
| 3 March 2027 | CD-0107: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0107: p95 | 2027-03-03 | 2027-03-03 | ok |
| CD-0145 | CD-0145: the request id | `requests` where request_id = CD-0145: request_id | CD-0145 | CD-0145 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 15 | CD-0145: small requests like it are done within this many days, 85% of the time | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0145: service_level_days | 15 | 15 | ok |
| CD-0156 | CD-0156: the request id | `requests` where request_id = CD-0156: request_id | CD-0156 | CD-0156 | ok |
| 10 March 2027 | CD-0156: done by this date in 50% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0156: p50 | 2027-03-10 | 2027-03-10 | ok |
| 26 March 2027 | CD-0156: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0156: p95 | 2027-03-26 | 2027-03-26 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 19 March 2027 | CD-0156: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0156: p85 | 2027-03-19 | 2027-03-19 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 5 March 2027 | CD-0120: done by this date in 95% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0120: p95 | 2027-03-05 | 2027-03-05 | ok |
| 19 March 2027 | CD-0156: done by this date in 85% of the forecast's runs | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0156: p85 | 2027-03-19 | 2027-03-19 | ok |

Every open item answered (R25):

| Item | Answer | Answered |
|---|---|---|
| CD-0099 Retire the old welcome-email workflow | date range | yes |
| CD-0107 Clean up duplicate Quote records | date range, moved | yes |
| CD-0120 Retire the old welcome-email workflow | date range, moved | yes |
| CD-0145 Check who still uses their CRM seat | service level | yes |
| CD-0156 The CRM is slow and annoying | date range, moved | yes |

## `U-up-20261125T003014Z-manager`

For **Desk manager** (manager, status). Drafted by update_drafter from forecast run `fc-20261125T001928Z`. Status: **draft**.

> **Forecast update: 9 requests moved, hours cut to 36**
>
> Setting changed since the last forecast: hours of work a week went from 40 to 36, a change made by the desk owner. 9 items moved their 85% date by more than 7 days: CD-0107 from 12 February 2027 to 25 February 2027; CD-0119 from 20 January 2027 to 28 January 2027; CD-0120 from 17 February 2027 to 3 March 2027; CD-0121 from 28 January 2027 to 5 February 2027; CD-0132 from 17 March 2027 to 2 April 2027; CD-0133 from 5 February 2027 to 17 February 2027; CD-0141 from 11 February 2027 to 24 February 2027; CD-0142 from 10 March 2027 to 25 March 2027; CD-0156 from 5 March 2027 to 19 March 2027. Hours in against hours worked a week, and whether the lane grows: urgent lane 1.3 hours in, 1.4 hours worked, does not grow; fixed date lane 3.9 hours in, 4.2 hours worked, does not grow; small and quick lane 8.1 hours in, 7.9 hours worked, grows; standard lane 30.8 hours in, 22.5 hours worked, grows. This week's plan, starting 23 November 2026, has 36 hours: fixed date lane 22 hours, small and quick lane 8.1 hours, standard lane 1.9 hours, urgent lane 4 hours. Decisions waiting for a person: 7 items are on the decide list. CD-0035, CD-0054, CD-0086 and CD-0020 are past their lane's age limit. 3 fixed-date requests have passed their date. No lane is waiting to be confirmed.

| Figure | Fact | Source row | Drafted | Now | |
|---|---|---|---|---|---|
| 9 | requests whose 85% date moved by more than a week since the last forecast | `update_triggers` where run_id = fc-20261125T001928Z: count of rows | 9 | 9 | ok |
| 36 | hours of work a week, after the change made by desk owner since the last forecast | `settings_history` where id = 139: value | 36 | 36 | ok |
| 40 | hours of work a week, before the change | `settings_history` where id = 1: value | 40 | 40 | ok |
| 36 | hours of work a week, after the change made by desk owner since the last forecast | `settings_history` where id = 139: value | 36 | 36 | ok |
| 9 | requests whose 85% date moved by more than a week since the last forecast | `update_triggers` where run_id = fc-20261125T001928Z: count of rows | 9 | 9 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 7 | days an 85% date must move before an update is drafted | `settings` where key = update_trigger_days: value | 7 | 7 | ok |
| CD-0107 | CD-0107 (Clean up duplicate Quote records): moved | `requests` where request_id = CD-0107: request_id | CD-0107 | CD-0107 | ok |
| 12 February 2027 | CD-0107: its 85% date in the last forecast | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0107: old_p85 | 2027-02-12 | 2027-02-12 | ok |
| 25 February 2027 | CD-0107: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0107: new_p85 | 2027-02-25 | 2027-02-25 | ok |
| CD-0119 | CD-0119 (Pipeline report does not match finance's total): moved | `requests` where request_id = CD-0119: request_id | CD-0119 | CD-0119 | ok |
| 20 January 2027 | CD-0119: its 85% date in the last forecast | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0119: old_p85 | 2027-01-20 | 2027-01-20 | ok |
| 28 January 2027 | CD-0119: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0119: new_p85 | 2027-01-28 | 2027-01-28 | ok |
| CD-0120 | CD-0120 (Retire the old welcome-email workflow): moved | `requests` where request_id = CD-0120: request_id | CD-0120 | CD-0120 | ok |
| 17 February 2027 | CD-0120: its 85% date in the last forecast | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0120: old_p85 | 2027-02-17 | 2027-02-17 | ok |
| 3 March 2027 | CD-0120: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0120: new_p85 | 2027-03-03 | 2027-03-03 | ok |
| CD-0121 | CD-0121 (Try a meeting-scheduler app from the marketplace): moved | `requests` where request_id = CD-0121: request_id | CD-0121 | CD-0121 | ok |
| 28 January 2027 | CD-0119: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0119: new_p85 | 2027-01-28 | 2027-01-28 | ok |
| 5 February 2027 | CD-0121: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0121: new_p85 | 2027-02-05 | 2027-02-05 | ok |
| CD-0132 | CD-0132 (Load event attendees from a spreadsheet): moved | `requests` where request_id = CD-0132: request_id | CD-0132 | CD-0132 | ok |
| 17 March 2027 | CD-0132: its 85% date in the last forecast | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0132: old_p85 | 2027-03-17 | 2027-03-17 | ok |
| 2 April 2027 | CD-0132: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0132: new_p85 | 2027-04-02 | 2027-04-02 | ok |
| CD-0133 | CD-0133 (Load event attendees from a spreadsheet): moved | `requests` where request_id = CD-0133: request_id | CD-0133 | CD-0133 | ok |
| 5 February 2027 | CD-0121: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0121: new_p85 | 2027-02-05 | 2027-02-05 | ok |
| 17 February 2027 | CD-0120: its 85% date in the last forecast | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0120: old_p85 | 2027-02-17 | 2027-02-17 | ok |
| CD-0141 | CD-0141 (Raise the discount that needs a director's approval): moved | `requests` where request_id = CD-0141: request_id | CD-0141 | CD-0141 | ok |
| 11 February 2027 | CD-0141: its 85% date in the last forecast | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0141: old_p85 | 2027-02-11 | 2027-02-11 | ok |
| 24 February 2027 | CD-0141: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0141: new_p85 | 2027-02-24 | 2027-02-24 | ok |
| CD-0142 | CD-0142 (Lead source is lost when a Lead is converted): moved | `requests` where request_id = CD-0142: request_id | CD-0142 | CD-0142 | ok |
| 10 March 2027 | CD-0142: its 85% date in the last forecast | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0142: old_p85 | 2027-03-10 | 2027-03-10 | ok |
| 25 March 2027 | CD-0142: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0142: new_p85 | 2027-03-25 | 2027-03-25 | ok |
| CD-0156 | CD-0156 (The CRM is slow and annoying): moved | `requests` where request_id = CD-0156: request_id | CD-0156 | CD-0156 | ok |
| 5 March 2027 | CD-0156: its 85% date in the last forecast | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0156: old_p85 | 2027-03-05 | 2027-03-05 | ok |
| 19 March 2027 | CD-0156: its 85% date now | `update_triggers` where run_id = fc-20261125T001928Z, request_id = CD-0156: new_p85 | 2027-03-19 | 2027-03-19 | ok |
| 1.3 | urgent lane: hours a week that arrive, in the forecast | `forecasts` where lane = urgent, run_id = fc-20261125T001928Z, request_id = null: hours_in_per_week | 1.3 | 1.3 | ok |
| 1.4 | urgent lane: hours a week that are worked, in the forecast | `forecasts` where lane = urgent, run_id = fc-20261125T001928Z, request_id = null: hours_out_per_week | 1.4 | 1.4 | ok |
| 3.9 | fixed date lane: hours a week that arrive, in the forecast | `forecasts` where lane = fixed_date, run_id = fc-20261125T001928Z, request_id = null: hours_in_per_week | 3.9 | 3.9 | ok |
| 4.2 | fixed date lane: hours a week that are worked, in the forecast | `forecasts` where lane = fixed_date, run_id = fc-20261125T001928Z, request_id = null: hours_out_per_week | 4.2 | 4.2 | ok |
| 8.1 | small and quick lane: hours a week that arrive, in the forecast | `forecasts` where lane = small, run_id = fc-20261125T001928Z, request_id = null: hours_in_per_week | 8.1 | 8.1 | ok |
| 7.9 | small and quick lane: hours a week that are worked, in the forecast | `forecasts` where lane = small, run_id = fc-20261125T001928Z, request_id = null: hours_out_per_week | 7.9 | 7.9 | ok |
| 30.8 | standard lane: hours a week that arrive, in the forecast | `forecasts` where lane = standard, run_id = fc-20261125T001928Z, request_id = null: hours_in_per_week | 30.8 | 30.8 | ok |
| 22.5 | standard lane: hours a week that are worked, in the forecast | `forecasts` where lane = standard, run_id = fc-20261125T001928Z, request_id = null: hours_out_per_week | 22.5 | 22.5 | ok |
| 23 November 2026 | the Monday this week's plan starts | `week_plan` where plan_id = plan-20261123-001854: min(week_start) | 2026-11-23 | 2026-11-23 | ok |
| 36 | hours of work a week | `settings` where key = hours_per_week: value | 36 | 36 | ok |
| 22 | this week's plan: hours for the fixed date lane | `week_plan` where lane = fixed_date, plan_id = plan-20261123-001854: sum(hours) | 22 | 22 | ok |
| 8.1 | small and quick lane: hours a week that arrive, in the forecast | `forecasts` where lane = small, run_id = fc-20261125T001928Z, request_id = null: hours_in_per_week | 8.1 | 8.1 | ok |
| 1.9 | this week's plan: hours for the standard lane | `week_plan` where lane = standard, plan_id = plan-20261123-001854: sum(hours) | 1.9 | 1.9 | ok |
| 4 | fixed date lane: hours a week that arrive, in the forecast | `forecasts` where lane = fixed_date, run_id = fc-20261125T001928Z, request_id = null: hours_in_per_week | 3.9 | 3.9 | ok |
| 7 | requests on the decide list today | `decide_list_at(2026-11-25)` where every row: count of rows | 7 | 7 | ok |
| CD-0035 | CD-0035 (Alert when Account records go stale): on the decide list, past the age limit | `requests` where request_id = CD-0035: request_id | CD-0035 | CD-0035 | ok |
| CD-0054 | CD-0054 (Cannot save one Lead record after the last update): on the decide list, past the age limit | `requests` where request_id = CD-0054: request_id | CD-0054 | CD-0054 | ok |
| CD-0086 | CD-0086 (Cannot save one Quote record after the last update): on the decide list, past the age limit | `requests` where request_id = CD-0086: request_id | CD-0086 | CD-0086 | ok |
| CD-0020 | CD-0020 (Refresh the test sandbox): on the decide list, past the age limit | `requests` where request_id = CD-0020: request_id | CD-0020 | CD-0020 | ok |
| 3 | of them, fixed-date requests whose date has passed | `decide_list_at(2026-11-25)` where why = its fixed date has passed: count of rows | 3 | 3 | ok |

## `U-up-20261125T003014Z-executive`

For **Executive sponsor** (executive, status). Drafted by update_drafter from forecast run `fc-20261125T001928Z`. Status: **draft**.

> **Forecast update: open work, backlog growth and fixed dates**
>
> There are 43 items open now. The standard lane takes in 30.8 hours a week but works through only 22.5 hours, so its backlog grows. The small and quick lane takes in 8.1 hours a week and works 7.9 hours, so it also grows; we expect 85% of small requests to be done within 15 days. Three fixed dates have passed with the work still open, and we expect the next fixed date, 4 December 2026, with a 100% chance of being met. Nine requests have expected dates that moved by more than a week since the last forecast.

| Figure | Fact | Source row | Drafted | Now | |
|---|---|---|---|---|---|
| 43 | requests open now (triaged, planned or started) | `requests` where status = Triaged or Planned or In progress: count of rows | 43 | 43 | ok |
| 30.8 | standard lane: hours a week that arrive, in the forecast | `forecasts` where lane = standard, run_id = fc-20261125T001928Z, request_id = null: hours_in_per_week | 30.8 | 30.8 | ok |
| 22.5 | standard lane: hours a week that are worked, in the forecast | `forecasts` where lane = standard, run_id = fc-20261125T001928Z, request_id = null: hours_out_per_week | 22.5 | 22.5 | ok |
| 8.1 | small and quick lane: hours a week that arrive, in the forecast | `forecasts` where lane = small, run_id = fc-20261125T001928Z, request_id = null: hours_in_per_week | 8.1 | 8.1 | ok |
| 7.9 | small and quick lane: hours a week that are worked, in the forecast | `forecasts` where lane = small, run_id = fc-20261125T001928Z, request_id = null: hours_out_per_week | 7.9 | 7.9 | ok |
| 85% | the forecast's 85% level | `settings` where key = forecast_levels: value[1] | 0.85 | 0.85 | ok |
| 15 | small requests are done within this many days, 85% of the time, in the forecast | `forecasts` where lane = small, run_id = fc-20261125T001928Z, request_id = null: service_level_days | 15 | 15 | ok |
| Three | fixed dates that passed with the work still open | `decide_list_at(2026-11-25)` where why = its fixed date has passed: count of rows | 3 | 3 | ok |
| 4 December 2026 | the next fixed date still open | `requests` where request_id = CD-0149: due_date | 2026-12-04 | 2026-12-04 | ok |
| 100% | the chance of meeting the next fixed date | `forecasts` where run_id = fc-20261125T001928Z, request_id = CD-0149: chance | 1 | 1 | ok |
| Nine | requests whose expected date moved by more than a week since the last forecast | `update_triggers` where run_id = fc-20261125T001928Z: count of rows | 9 | 9 | ok |

Every request is made up. The figures show direction, not size.
