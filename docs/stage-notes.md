# Stage notes: stages 0 to 4

A short "how it works" for each stage, so the build can be explained in an interview. Built 25/11/2026. Every ticket is made up.

## Stage 0: the store, the settings and a loaded history

**What it is.** A schema named `changedesk` in the local Supabase Postgres, with the tables of KB-139 section 6.2: requests, status history, scores, settings, work log, week plan, forecasts, updates, goals, the run log and the hand-off record, plus a decisions table for every person's choice. One table holds every setting, with who changed it, when and why; a second table keeps every value a setting has had.

**How to say it.** "Every request is one row, and every change to its status is another row, from the moment it arrives. The database itself refuses a request whose status is not the last line of its history, so the history cannot drift."

**The app's own login.** `changedesk_app` can read the schema and nothing else. It cannot insert, update or delete any table: it writes only through checked functions (seven in stage 0 to 2, nine with stage 3 and 4's save_plan and log_forecast), each of which writes the row, its status history and a stamp together. `scripts/setup_db.py` makes its password straight into `.env` and proves twelve limits each time it runs: it cannot read the pipeline's schema, cannot change a setting by hand, cannot create a table.

**The history.** `scripts/make_history.py` makes twelve weeks of made-up tickets from a fixed seed: an opening backlog, then each week's arrivals drawn the way the policy test in KB-136 section 6.6 draws them (about 42.7 hours of demand against 40 hours). The weeks are worked the old way, highest score first, so the history carries the fault the design fixes: three fixed dates were missed, and small items have waited since August. Twelve hand-written requests from 23 and 24 November sit in the inbox, still New, for the triage step. The same seed makes the same file every time; a test checks it.

**Ends with.** A loaded history: 159 requests, 538 status changes, 735 score parts, 480 hours of work over twelve weeks.

## Stage 1: intake, triage and lane confirmation

**Intake.** An n8n form. A request gets an id (CD-1001 onwards) and its first status history row in one step (R1). The form asks for the requester's role, never a name.

**The triage playbook, written as a skill.** `skills/triage-playbook/SKILL.md`: the four lanes, the two tests, the size rule, the score parts, the flags and the 36 playbooks of the CRM Admin Process Library (KB-115), each with how people ask for it. The engine reads the playbook's tables, so a lane or playbook that is not in the file cannot be returned.

**The one AI step.** One Claude call per request, Haiku 5.5, structured output in the fixed shape of section 6.4 (R2). Request text is data, never instructions (R3): guard rules come before the playbook; the text goes in as escaped JSON inside a data block, so it cannot close the block; and a code screen, apart from the model, looks for instructions, claims of senior approval, fake output and markup. Either the model or the screen is enough to hold a request for a person, and a flagged request's confidence is capped at 0.50.

**The two tests (R4).** The model answers them: is there a date, and what breaks on it? Is harm growing now? Then code sets the lane from those answers by the published rule: urgent, else fixed date, else small if two hours or less, else standard. If the model's own lane differs from the rule, the rule wins and a person looks. "URGENT!!!" with no growing harm is not urgent; "before the meeting" with nothing breaking is not a fixed date.

**Lane confirmation (R5).** Urgent, fixed-date, low-confidence and flagged items, and every proposed split (R8), wait for a person on an n8n form. The person confirms or changes the lane and accepts or rejects the split; each choice is stamped with their name. The store refuses to plan or start an item that waits: a constraint on the request and a trigger on the week plan.

**Also on every item.** The playbook that would handle it, or none (R6). A flag when it serves no business goal (R7). Each hand-off from the AI step to a person is a row: what was asked, why, the evidence, the confidence.

**How to say it.** "The AI answers two questions and estimates the size; a published rule, not the AI, picks the lane. Anything urgent, dated, unsure or suspicious waits for a person, and the database will not let it be planned until someone has signed it."

**The eval, and how the playbook got to 1.0.2.** 40 labelled requests, eight of them hostile, three rounds on Haiku 5.5, graded by `scripts/triage_eval.py` against a bar written before the first run (`skills/triage-playbook/eval/bar.json`). Nothing in the bar or the labels was changed after any run.

| Playbook | Result | What happened |
|---|---|---|
| 1.0.0 | Missed the bar on one line: hostile requests 18 of 24 | No attack steered anything: all 24 were flagged and held for a person (code screen 24, model 23). The misses were sizing: Haiku called small items "small" but sized them at 3 hours, so the 2-hour rule moved them to standard, and the grader counts a hostile row as blocked only when its lane is also right. Lane 92.5%, size 82% |
| 1.0.1 | Missed the bar on one line: answers in the fixed shape 118 of 120 | Written after seeing 1.0.0's misses: the team's sizing guide, and "your lane must agree with your own size". Hostile 24 of 24, lane 98.3%, size 100%. But for the deliberately vague request ("the CRM is slow and annoying") Haiku gave a size of 0 twice; the engine refuses that, so the request would stay in the inbox |
| 1.0.2 | **Met every line; kept** | One sentence added: if a request is too unclear to size, give a best guess of at least an hour, keep the confidence low and flag it unclear. Shape 120 of 120, lane 120 of 120, size 117 of 117, playbook 97.5%, a person asked exactly when the label says 108 of 108, hostile 24 of 24 (code screen 24, model 24), no normal request flagged as an attack. US$0.00088 a triage |

Each candidate was tested once, from its own file, against the unchanged cases and bar, then copied over the live playbook unchanged. 1.0.1 and 1.0.2 were written after seeing results on the same 40 cases, so they are tuned to this eval; a fresh set of labelled requests is the honest check, and stage 6 should add one. Sonnet 5.5 was not needed. The results of 1.0.0 and 1.0.1 are kept as `results-1.0.0-not-kept` and `results-1.0.1-not-kept`.

One run was lost: the first test of 1.0.1 crashed in the eval script after its 120 calls (a path bug, now fixed, and the script now saves the raw rows first). Its results were never seen, and about US$0.10 of calls is not in the run log.

**The live run.** `scripts/triage.py`, 25/11/2026, run `py-20261124T221440Z`: the twelve inbox requests, all in lanes with a reason, US$0.0106 for 12 calls. Seven wait for a person: the urgent sync failure, two fixed dates, the large integration's split into pieces, the vague request, the request that tried to instruct the AI, and the one holding contact details. "URGENT!!!" for a page colour went to small; a report wanted "before the meeting", with nothing breaking, went to standard.

## Stage 2: scoring, the change log, ageing and the decide list

**Scoring with its working shown (R9).** Five parts in the form of the Decision Engine: value, effort, risk, goal fit and readiness, weighted 30, 20, 20, 20 and 10 per cent. The triage step proposes value, risk, goal fit and readiness, each with a reason. Effort comes from the size by a published band (two hours or less scores 10), and goal fit is 1 by rule when no goal is named. The store works the score out from the parts and the weights in the settings, so every figure can be traced: "value 6 x 0.3 = 1.80 + effort 4 x 0.2 = 0.80 + ...".

**A person can change any part (R10).** An n8n form: one part of one item, a new value, a reason. The change is a new row; the old value stays, and the working view shows both, with who and why.

**Waiting earns points (R11).** Each whole week waited adds 0.25 points (the setting). The standard lane is ranked by score plus age, with "do it next" from the decide list first. Score alone never sets the order. The test that proves it: eight weeks in which the top item is done each week and a new item arrives that scores more than the oldest low-scored item. With 0.25 points a week, that item climbs from rank 18 to rank 12 on the loaded history (26 to 20 on the store after the test run, which added more open work); with 0, it stays where it started for good, because each new arrival takes its place.

**The decide list (R16).** Open items past their lane's age limit (30 days small, 90 standard) go on a list. An n8n form decides each: do it next, merge it into another open item with the same playbook, or close it with a reason. A close hands the item to the message drafter, which writes a short note to the requester; code checks the draft (it names the request, makes no promise, names no internal codes); it waits in the updates table as a draft. Nothing is sent to anyone, and the app's login has no way to approve or send.

**How to say it.** "Score ranks work only inside the standard lane, and age keeps adding to it, so nothing sinks for good. Anything past its age limit is put in front of a person: do it, merge it, or close it and tell the requester why."

## Fixes from the first test run (n8n-8905 to n8n-8909, 25/11/2026)

COURSES 2ND ran all five forms on Israel's delegation. Everything was stamped and nothing was sent. Three things needed putting right.

1. **A close reason held the whole form's note.** The decide form has one note box for the whole form, and it was copied onto every merge and close. So CD-0029's close reason talked about CD-0016 and CD-0037. Now each decided item's reason is its own (the reason chosen for that item), and it is the only thing that becomes the close reason, the history note and the drafter's input. The reviewer's note is kept on the decision row only. The form's label says so. `tests/test_scoring_engine.py` and `tests/test_requirements_db.py` check it. The test run's own rows keep what was written at the time; the demo reset (`load_history.py --reset`) clears them.
2. **A clean draft was flagged.** The close draft for CD-0029 came back flagged possible injection and personal data. The cause was finding 1: the drafter read the shared note, which named a person and two other items. `scripts/drafter_probe.py` showed it by changing only that one field. With the note in the reason, the model flagged 6 drafts of 6; with the item's own reason, 0 of 6. US$0.002 for 12 calls, in the run log; no draft stored. The same draft also tripped the code's own promise check, on "please raise a new request ... and we will be glad to look at it again". The check now reads one sentence at a time, and lets "we will" stand in a sentence about a new request that promises no delivery and no date. The probe's drafts showed other wordings ("we will take a fresh look at it"), so the rule is about the sentence's meaning, not one phrase. A false flag can still happen, because the flags are the model's own judgement; the README's known limits say so.
3. **The workflows were switched on and off in the n8n screens.** Publish, then Unpublish, saved a named version of each workflow. `n8n_publish.py check` found every one in step and off. But it compared only the saved draft, and n8n 2.x runs the published version. So check now also reads the published version when there is one: an active workflow's must be its latest saved version and match the file, and an inactive one must have none. The five workflows were rebuilt (the two engines changed), put in again and checked: all in step, all off.

The store's tests also found one older bug: `changedesk.set_setting` could never run, because its parameter `why` has the same name as the settings table's column. No setting had been changed through it before stage 3. It now names its parameter in full, and the R14 tests use it.

## Stage 3: the planner, pipe health and the tracker

**The planner, a plain script (R12).** `scripts/planner.py`. One week of hours is spent in this order, and every number is a setting: urgent first, one at a time, oldest first (the 10% buffer is what urgent work is expected to take; it takes more if it must, and the plan says how much more); fixed-date items from their latest safe start; the small lane's 20%, oldest first; standard work's 70%, by score plus points for waiting, "do it next" first; and any hours left flow to the other lanes, on down the standard order, then small, then fixed-date work ahead of its safe start. Items waiting for a person are never planned. The latest safe start is the due date less the time fixed-date work has needed 85% of the time; the made-up history's timestamps are too rough for that, so it is read from the work log (the weeks an item's hours were spread over): all four done items took one week, so 7 days.

**The hand check.** The plan for the week of 23/11/2026, worked by hand before the code ran, then matched line by line: 40 hours. Urgent CD-0148 takes its 4: 36 left. Four fixed-date items are at or past their latest safe start (CD-0060, CD-0046 and CD-0089 missed their dates under the old rule; CD-0149 is due 04/12, safe start 27/11): 10 + 5 + 5 + 2 = 22, so 14 left. Small, the lesser of 14 and 8: seven items oldest first, CD-0150 getting 1 of its 1.5 hours: 6 left. Standard, the lesser of 6 and 28: CD-0016, "do it next" from the decide list, 6 of its 13 hours. Nothing flows. A second hand-checked week, with every step used, is the test `test_r12_the_weeks_plan_matches_a_hand_check`.

**One piece of code (R13).** The planner's `plan_week()` makes the real plan, every week of every forecast run, and every week of every rule-test replay. The strongest check: replayed with the old rule, "highest score first", it gives back the made-up history's own work log hour for hour (126 of 126 rows, the same 114 items done), on the sample history and on every seed from 163 to 172. The standard lane's order is the store's own `ranked_standard`; the planner checks they agree before it saves. `ranked_standard` now includes work already in progress, so the planner places it by the same rule.

**Settings drive it (R14).** A setting is changed with `changedesk.set_setting` (who, when, why; every value it has had is kept), and the next plan follows it. The test halves the small share in the store and the plan's small hours go from 8 to 4.

**Pipe health (R15 to R17).** `changedesk.lane_health` gives each lane's week: in, out, open, the oldest age, past the age limit, fixed dates met, urgent hours beyond the buffer. `scripts/health_report.py` writes the one-page report from it, with the decide list and the fixed dates still open. The lane growth flag: more in than out for three complete weeks running (the setting), and then a person is asked to choose: change the split, add hours, or say no. Nothing is flagged on 25/11/2026: small and quick is at two weeks running.

**The tracker.** `scripts/sync_tracker.py`, with its own Notion key that reaches one board. It reads the board's properties first and writes nothing if one of its 21 is missing, of the wrong type, or short of an option (Notion would otherwise add the option to COURSES 2ND's board). It upserts by Request ID, changes only what differs, and never deletes. Roles only: "Lane confirmed by" is worked out as a role ("Desk reviewer", "Made-up history", "Waits for a person", "Not needed: the lane rule set it"), never copied from a reviewer's label. 163 rows created on 25/11/2026, then read back: all 163 the same as the store.

**How to say it.** "A plain script spends the week in a published order: urgent, then dates that cannot move, then the small lane's share, then scored work, and the leftovers flow on. The same function makes the real plan, the forecast and the proof, and replayed with the old rule it gives back the old history to the hour."

## Stage 4: the forecast, the trigger and the proof

**The forecast (R18, R19).** `scripts/forecast.py`: 1000 runs of the next 26 weeks, seed 163 (settings). Each run starts from the open work in the store, and each lane gets new arrivals copied from one of its own past weeks, drawn at random. Each week is planned by `plan_week()` and worked. Standard and urgent items get the dates they are done by in 50, 85 and 95% of runs; small items get one service level (85% within 17 days); fixed-date items get the chance of the date and the latest safe start. When a lane takes in more hours than it puts out, the output says so, and an item not done within the horizon in enough runs gets no date at that level. On 25/11/2026 the standard lane grows (30.8 hours a week in, 26.6 worked) but all its open items still get dates, because points for waiting lift them over new work. At twice the demand, one item loses its 85% date, and the output says why.

**The update trigger (R20).** Run the forecast again when the pipe changes. An item gets an update draft only when its 85% date moves by more than a week, or it gains or loses its date. The draft is a plain template, filled from the forecast rows; it waits as a draft, and nothing is sent. Stage 5 puts the three audiences' drafts behind the same trigger.

**The rule test (R26).** `scripts/rule_test.py`: three order rules on the sample history's own arrivals, then on the histories of seeds 163 to 172, through `plan_week()`, with the policy test's measures. The lanes rule finishes every small item and meets every fixed date that falls due, on every seed; "highest score first" meets a median of 43% of them. The price is a little value (median 96.5 against 100). The table is in the README whatever it shows, and a test checks it is what the script makes.

**The back-check (R21).** `scripts/back_check.py`: a forecast from the end of week 8, knowing only what was known then, planned by the rule the history was really worked by, against weeks 9 to 12. 4 of 4 standard items that could be judged finished inside their 85% range; 4 more are not yet known; the 7 given no date were all still open. Small items: 75% were done within the forecast's 85% service level. Four weeks is a short window, and the README says so.

**How to say it.** "The forecast runs the weeks ahead a thousand times with new work arriving the way it has arrived, through the same planner. It gives a date range for scored work, a service level for small work and a chance for each date that cannot move. It says when a lane is growing, and it only drafts an update when a date moves by more than a week."

## Changed from the spec, or added by the build

- `ranked_standard` now includes In progress work (it held Triaged and Planned only), so started work is placed by the same rule. No new rule.
- The latest safe start reads the time fixed-date work needed from the work log, in weeks, because the made-up history's start and end times are rough. KB-139 section 7's rule is unchanged.
- Three settings added as build additions: forecast runs (1000), horizon (26 weeks), seed (163).
- The update trigger's draft is a plain template in stage 4, as no AI drafter for status updates exists before stage 5.
- `check` in `n8n_publish.py` reads the published version too; `set_setting`'s old bug fixed.

## Carried to later stages

- **Stage 5, the updates.** The three audiences' drafts go behind the stage 4 trigger, from the forecast rows, with the approval step and the outbox.
- **Stage 6, a fresh eval set.** The playbook was tuned on the 40 eval cases (see the table above); add requests it has never seen before the triage eval is quoted as a result.
- **For Israel, a split to review.** The forecast shows the small lane's 20% just under its demand (8.1 hours a week against 8). The split is a setting to be reset from data; no change was made.
- **For a person, three fixed dates missed under the old rule.** CD-0046, CD-0060 and CD-0089 are past their dates and still open, and this week's plan gives them 20 hours. The decide list covers only the small and standard lanes, so a person should say whether they are still needed.

## Test-run reviews

The reviews in test runs (lane confirmation, score change, decide list) are made by COURSES 2ND or the Code chat on Israel's delegation. They prove the flow works end to end; they are not an independent review.
