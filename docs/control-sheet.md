# Control sheet

One page for the whole build (KB-137 A1.5 to A1.7; R29), laid out on the six practices of Australia's [Guidance for AI Adoption](https://www.industry.gov.au/publications/guidance-for-ai-adoption/guidance-ai-adoption-foundations) (Department of Industry, October 2025), as the GTM pipeline's sheet is. Every line points to the file, test or log row that shows it; `tests/test_control_sheet.py` fails if one does not. **This sheet records facts about the build and states no legal conclusion. At an employer, whether a duty applies is decided by their privacy lead.**

## The AI register (A1.7)

| Process | Playbook | Agent or tool | Approval point | Owner | Eval |
|---|---|---|---|---|---|
| Triage of bugs and enhancements into four lanes | [triage-playbook](../skills/triage-playbook/SKILL.md) 1.0.2 | [Triage agent](role-cards/triage-agent.md): one Claude Haiku 5.5 call, no tools | Lane confirmation form: urgent, fixed-date, unsure and flagged items, and every split | Systems desk lead (made-up role) | [results.md](../skills/triage-playbook/eval/results.md) (40 tuned cases) and [results-fresh.md](../skills/triage-playbook/eval/results-fresh.md) (30 fresh), against [bar.json](../skills/triage-playbook/eval/bar.json) |
| Close messages for the decide list | Its brief in [drafter.js](../engine/drafter.js) | [Message drafter](role-cards/message-drafter.md): one call, no tools | Approval form, every draft | Systems desk lead (made-up role) | No labelled set: the code check of every draft (`tests/test_scoring_engine.py::test_the_draft_check_catches_what_a_requester_must_not_get`) |
| Updates for three audiences | Its brief in [updates.js](../engine/updates.js) 1.0.2 | [Update drafter](role-cards/update-drafter.md): one call per reader, no tools | Approval form, every draft, each figure shown with its row | Systems desk lead (made-up role) | No labelled set: the code check and the R23 check script ([updates.md](reports/updates.md)) |

The planner and the forecast are plain scripts, not AI, and the intake, confirm, score and approval workflows hold no AI step: none is on the register. Every workflow and what it writes through: [workflows.md](workflows.md).

## The six practices

1. **Decide who is accountable.** Each agent's role card names its owner, purpose, limits and review date ([role cards](role-cards/)). One spend ceiling covers every call: the `gtm-pipeline` workspace's US$10 monthly limit ([cost sheet](cost-sheet.md)).
2. **Understand impacts and plan accordingly.** Every ticket is made up and requesters are roles, never names (`tests/test_no_private_data.py::test_no_real_email_addresses_in_tracked_files`). Nobody is scored, and score alone never sets the order: waiting earns points (`tests/test_requirements_db.py::test_r11_an_old_items_rank_rises_week_by_week`).
3. **Measure and manage risks.** The app's login reads one schema and writes only through checked functions; `scripts/setup_db.py` proves 14 limits each run. Request text is data: hostile requests blocked 24 of 24 on the tuned set and 18 of 18 on the fresh one ([results-fresh.md](../skills/triage-playbook/eval/results-fresh.md)). A fact can read only listed tables (`tests/test_updates_db.py::test_r23_a_fact_may_read_only_the_listed_tables_and_columns`).
4. **Share essential information.** This register, the [README](../README.md) and the [cost sheet](cost-sheet.md). Every AI write carries a stamp back to its log row (`changedesk.triage_record`; `tests/test_updates_db.py::test_r22_three_audiences_are_drafted_from_one_run`), and every figure in an update is traced to its row (`scripts/check_updates.py`).
5. **Test and monitor.** Tests run on every push ([tests.yml](../.github/workflows/tests.yml)). A playbook below its bar cannot be pushed (`tests/test_playbook_bar.py::test_a_moved_bar_or_a_result_below_it_is_refused`); the fresh eval ran once on the playbook unchanged (`tests/test_fresh_eval.py::test_the_fresh_result_is_of_the_committed_set_and_the_live_playbook_unchanged`); the docs cannot drift from the workflow files (`tests/test_build_docs.py::test_the_readme_and_the_workflows_page_match_a_fresh_build`).
6. **Maintain human control.** A person confirms lanes, decides old items and approves every update, and the store refuses each without them (the table below). Nothing is scheduled (`tests/test_n8n_workflows.py::test_r31_nothing_is_scheduled_every_run_starts_from_a_form`) and nothing sends (`tests/test_n8n_workflows.py::test_r24_no_workflow_has_a_node_that_sends`).

## Approval points and stop switches

| Workflow | Where a person decides | Proof | Stop switch |
|---|---|---|---|
| Triage | Lane confirmation form: confirm or change each lane, accept or reject each split | `tests/test_requirements_db.py::test_r5_no_such_item_is_planned_without_a_confirmation` | Unpublish the forms in n8n; revoke the key in `gtm-pipeline` ([triage card](role-cards/triage-agent.md)) |
| Decide list | Decide form: do it next, merge, or close with a reason | `tests/test_requirements_db.py::test_r16_only_an_item_on_the_list_can_be_decided` | Unpublish the form; a close only drafts a message |
| Updates | Approval form: approve or reject each draft; problems or stale facts allow only a rejection | `tests/test_updates_db.py::test_r24_a_person_approves_and_the_update_goes_to_the_outbox_and_nowhere_else`; `changedesk.outbox` | Unpublish the approval form; nothing reads the outbox to send ([update drafter card](role-cards/update-drafter.md)) |
| Settings | `changedesk.set_setting`: who, when and why, every old value kept | `tests/test_planner_db.py::test_r14_changing_a_setting_in_the_table_changes_the_next_plan`; `changedesk.settings_history` | The demo reset puts back the starting values (`tests/test_history.py::test_the_demo_reset_puts_the_store_back_to_the_history_and_the_starting_settings`) |

## The 10/12/2026 disclosure questions

From 10/12/2026 an Australian privacy policy must say when a computer program uses personal information to "make, or do a thing that is substantially and directly related to making, a decision" that "could reasonably be expected to significantly affect the rights or interests of an individual" ([OAIC](https://www.oaic.gov.au/news/media-centre/new-resources-on-transparency-for-use-of-ai-and-automated-decision-making)). All three tests must be met. Each row gives this build's facts, not a legal answer.

| Question it raises | This build's facts | Evidence |
|---|---|---|
| Does a program use personal information? | Here, none: requesters are roles and tickets are made up. A request holding contact details is flagged and held for a person; at an employer a ticket may name a person | `tests/test_triage_engine.py::test_personal_data_is_flagged` |
| Does it make the decision, or do a thing "substantially and directly related to making" it? | The AI proposes a lane and drafts updates; code sets the lane by a published rule, and a person confirms lanes and approves every update. Whether proposing counts is the legal question | `tests/test_requirements_db.py::test_r5_no_such_item_is_planned_without_a_confirmation` |
| Could the decision "reasonably be expected to significantly affect the rights or interests of an individual"? | Which week a request is worked, and whether an old one is closed. No person is scored | [Triage](role-cards/triage-agent.md) and [update drafter](role-cards/update-drafter.md) role cards |
| What would the policy say, and who decides? | Not decided here. At an employer, their privacy lead, with this register as the input | [README](../README.md) |
