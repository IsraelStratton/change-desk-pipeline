# Build guide: stages 0 to 4

Who does what. The Code chat does every step it can from the command line. Israel does only what needs him: keys and passwords. COURSES 2ND does the clicks in Israel's Chrome. Neither chat sees a key or a password.

If any screen shows a price, a trial, a card or a licence: stop and tell Israel.

## Step 1. Two keys into this folder's .env (Israel, in Terminal; done 25/11/2026)

This one command copies two lines from the GTM pipeline's `.env` into this folder's `.env`: `ANTHROPIC_API_KEY` (the Claude key: Claude Console workspace `gtm-pipeline`, US$10 monthly limit) and `N8N_API_KEY` (the local n8n's API key, used only by `scripts/n8n_publish.py`). It prints only their lengths, never the values.

```bash
cd ~/change-desk-pipeline && for k in ANTHROPIC_API_KEY N8N_API_KEY; do { grep -v "^$k=" .env; grep "^$k=" ~/gtm-enrichment-quality-pipeline/.env; } > .env.tmp; mv .env.tmp .env; done; chmod 600 .env; awk -F= '/^(ANTHROPIC_API_KEY|N8N_API_KEY)=/{print $1, "length", length(substr($0, index($0,"=")+1))}' .env
```

Expected: `ANTHROPIC_API_KEY length 106` and `N8N_API_KEY length 289`.

## Step 2. The store (Code chat; done 25/11/2026)

```bash
.venv/bin/python scripts/setup_db.py
.venv/bin/python scripts/load_history.py
```

`setup_db.py` applies the four SQL files, makes the `changedesk_app` login with its password written straight into `.env` as `CHANGEDESK_DB_PASSWORD` (never printed), loads prices, goals and the settings, and proves the login's limits (12 checks). `load_history.py` loads the made-up history. `load_history.py --reset` puts the store back to the history for a demo.

## Part B. One new n8n credential (COURSES 2ND clicks; Israel pastes the password; done 25/11/2026)

n8n at http://localhost:5678, signed in as the owner. Credentials, Create credential. The name must match exactly: the workflows find their credentials by name.

**Change Desk (Postgres)**, type **Postgres**

| Field | Value |
|---|---|
| Name of the credential | `Change Desk (Postgres)` |
| Host | `host.docker.internal` |
| Database | `postgres` |
| User | `changedesk_app` |
| Password | Israel pastes it. This copies it to the clipboard and shows nothing on screen: `grep '^CHANGEDESK_DB_PASSWORD=' ~/change-desk-pipeline/.env \| cut -d= -f2- \| tr -d '\n' \| pbcopy` |
| Port | `54322` |
| SSL | Disable |

Save. It shows "Connection tested successfully" when the password is right. This login can read the `changedesk` schema and write only through its checked functions; it cannot read the pipeline's `gtm_v2` schema or anything else.

The Claude credential is reused, not made again: **Claude key gtm-pipeline-v2** (Header Auth) already holds the same key, and its reach fits this build.

## Part C. Put the workflows in (Code chat; done 25/11/2026, all five off)

```bash
.venv/bin/python scripts/n8n_publish.py publish
.venv/bin/python scripts/n8n_publish.py check
```

Five workflows, all off: Change Desk: intake form, run triage, confirm lanes, change a score, decide list. None has a schedule. Before a test session: `n8n_publish.py on`. After it: `n8n_publish.py off`, then `n8n_publish.py check`.

Switch them on and off with the script, not the n8n screens: Publish and Unpublish there each save a named version. That is no harm, and `check` now reads the published version too (n8n 2.x runs the published version, not the saved draft): an active workflow's must be its latest saved version and match the file, an inactive one must have none.

## Part D. A test run (COURSES 2ND, on Israel's delegation)

The reviews in a test run are made by COURSES 2ND or the Code chat on Israel's delegation. They prove the flow works; they are not an independent review. Use Chrome (the built-in browser pane blocks n8n's form submit, found in the pipeline).

1. **Intake** at http://localhost:5678/form/changedesk-intake. Role `Support lead`; title `A queue for billing questions`; description `Billing questions land in the general queue and wait. We need a billing queue and an escalation after two working days.`; no date; no harm. The last page names the new request id (CD-10xx).
2. **Triage** at http://localhost:5678/form/changedesk-triage. Choose "Every request in the inbox", Run triage. The last page says how many went into each lane, how many wait for a person, and the cost.
3. **Confirm lanes** at http://localhost:5678/form/changedesk-confirm-lanes. Reviewer label `courses-2nd (delegated)`. For each row: confirm the lane unless the table shows the AI's lane differs from the rule or the request tried to instruct the AI, in which case confirm the rule's lane (the note says why). Accept a split whose pieces each make sense on their own; reject one that does not. Note: `Test run on Israel's delegation.`
4. **Change a score** at http://localhost:5678/form/changedesk-change-score. Reviewer `courses-2nd (delegated)`; any item; part `readiness`; a new value; reason `Test run on Israel's delegation: the owner confirmed it can start.`
5. **Decide list** at http://localhost:5678/form/changedesk-decide. Reviewer `courses-2nd (delegated)`. Choose "Do it next" for the oldest standard item, "Close: no longer needed" for one small item, and leave the rest.

What the Code chat checks afterwards: every new request has a status history; every triaged row has every field and a stamp; nothing urgent or fixed-date is confirmed without a stamp with the reviewer's name; the changed score shows both values; the closed item has a draft in `changedesk.updates` with status `draft`; nothing was sent; the cost per triage in `docs/cost-sheet.md`.

## Part E. The tracker's own Notion key (Israel; done 25/11/2026, 09:40)

The board "Change Desk — tracker (made-up tickets)" was built by COURSES 2ND, empty, with its 21 properties and three views. Israel made a Notion connection, "Change Desk tracker", with its reach checked in Notion: read, update and insert content; no comments; no user information; access to this one board only. Three values are in `.env`, put there by Israel and never printed by any script: `NOTION_CHANGEDESK_TOKEN` (the key), `NOTION_CHANGEDESK_DB` (the board) and `NOTION_CHANGEDESK_DATA_SOURCE` (its data source). The two ids are also in `.prepush-private.local`, so the pre-push check refuses them.

```bash
.venv/bin/python scripts/sync_tracker.py --check     # the board's properties, types and options; writes nothing
.venv/bin/python scripts/sync_tracker.py --dry-run   # what a sync would change; writes nothing
.venv/bin/python scripts/sync_tracker.py             # create and update rows by Request ID; never deletes
```

If a property is missing or wrong, the script says which and writes nothing. The board is COURSES 2ND's: fix it there, not here.

## Part F. Stages 3 and 4 by hand (Code chat; done 25/11/2026)

Nothing is scheduled. After the pipe changes (a triage run, a confirmation, a decision, a setting), run in this order:

```bash
.venv/bin/python scripts/plan_week.py        # the week's plan, saved; docs/reports/week-plan.md with the working
.venv/bin/python scripts/forecast.py         # the forecast, saved; drafts an update only when an 85% date moved more than a week
.venv/bin/python scripts/health_report.py    # docs/reports/health.md
.venv/bin/python scripts/sync_tracker.py     # the board
```

A what-if forecast (another demand) is saved as a what-if and drafts nothing: `scripts/forecast.py --load 2`. The proof runs on the sample history file alone, with no database: `scripts/rule_test.py` and `scripts/back_check.py` write their tables into the README and `docs/reports/`, and `--check` says whether they are up to date (a test runs it in CI).

A setting is changed only through the store, with who and why, and the next plan follows it:

```bash
docker exec -i supabase_db_hubspot-ai-database psql -U postgres -d postgres -c "select changedesk.set_setting('small_share', '0.25'::jsonb, 'Israel', 'the small lane needs more than its demand');"
```
