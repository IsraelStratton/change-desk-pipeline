# Stage notes: stages 0, 1 and 2

A short "how it works" for each stage, so the build can be explained in an interview. Built 25/11/2026. Every ticket is made up.

## Stage 0: the store, the settings and a loaded history

**What it is.** A schema named `changedesk` in the local Supabase Postgres, with the tables of KB-139 section 6.2: requests, status history, scores, settings, work log, week plan, forecasts, updates, goals, the run log and the hand-off record, plus a decisions table for every person's choice. One table holds every setting, with who changed it, when and why; a second table keeps every value a setting has had.

**How to say it.** "Every request is one row, and every change to its status is another row, from the moment it arrives. The database itself refuses a request whose status is not the last line of its history, so the history cannot drift."

**The app's own login.** `changedesk_app` can read the schema and nothing else. It cannot insert, update or delete any table: it writes only through seven checked functions, each of which writes the row, its status history and a stamp together. `scripts/setup_db.py` makes its password straight into `.env` and proves twelve limits each time it runs: it cannot read the pipeline's schema, cannot change a setting by hand, cannot create a table.

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

**Waiting earns points (R11).** Each whole week waited adds 0.25 points (the setting). The standard lane is ranked by score plus age, with "do it next" from the decide list first. Score alone never sets the order. The test that proves it: eight weeks in which the top item is done each week and a new item arrives that scores more than the oldest low-scored item. With 0.25 points a week, that item climbs from rank 18 to rank 12; with 0, it stays at 18 for good, because each new arrival takes its place.

**The decide list (R16).** Open items past their lane's age limit (30 days small, 90 standard) go on a list. An n8n form decides each: do it next, merge it into another open item with the same playbook, or close it with a reason. A close hands the item to the message drafter, which writes a short note to the requester; code checks the draft (it names the request, makes no promise, names no internal codes); it waits in the updates table as a draft. Nothing is sent to anyone, and the app's login has no way to approve or send.

**How to say it.** "Score ranks work only inside the standard lane, and age keeps adding to it, so nothing sinks for good. Anything past its age limit is put in front of a person: do it, merge it, or close it and tell the requester why."

## Carried to later stages

- **Stage 3, the tracker (Israel's ruling, 25/11/2026).** The Notion tracker is filled by a script with its own Notion key, limited to one board. The board is already built. Its property names come with the stage 3 prompt. The script reads the `changedesk.tracker` view; the no-goal flag (R7) is a column there.
- **Stage 3, the planner and R11.** The ranking lives in one place now, `changedesk.ranked_standard`. The planner, the forecast and the rule test (R13) must take their order from it or from one module with a test that the two agree, never a second copy of the rule.
- **Stage 4, the rule test across seeds (COURSES 2ND, 25/11/2026).** Run the rule test on the histories made from seeds 163 to 172, not on seed 172 alone, and show the spread in the README, so the result does not rest on one seed. Seed 172 stays the loaded history, with its note in `scripts/make_history.py`.
- **Stage 6, a fresh eval set.** The playbook was tuned on the 40 eval cases (see the table above); add requests it has never seen before the triage eval is quoted as a result.

## Test-run reviews

The reviews in test runs (lane confirmation, score change, decide list) are made by COURSES 2ND or the Code chat on Israel's delegation. They prove the flow works end to end; they are not an independent review.
