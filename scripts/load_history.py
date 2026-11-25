#!/usr/bin/env python3
"""Load the made-up history (sample/history.json) into the changedesk schema. The spec's stage 0, R1.

Runs as the database owner inside the Supabase db container, like scripts/setup_db.py: loading a
history is setup work, not something the app's login may do. One transaction: the requests, their
whole status history, every score part and the hours worked by week. The store's own check (every
request's status is the last one in its history) runs when the transaction commits, so a history
that breaks it is not loaded at all.

  python scripts/load_history.py            # load into an empty store; refuses if requests exist
  python scripts/load_history.py --reset    # empty the Change Desk tables first, then load (the demo reset)

--reset deletes every request, its history, scores, work, plans, forecast runs and their rows, the update
triggers, drafts, decisions, the outbox, the run log and the hand-offs, and starts request numbers at CD-1001
again. It also puts every setting back to its starting value in settings/settings.json (40 hours a week, the
20/70 split and the rest), each as a change in the settings table by "load_history.py --reset", so the history
of every value is kept. Goals and prices stay. The outbox is add-only (its trigger refuses delete), so the reset
empties it with TRUNCATE, which only the database owner can run. The run log goes too: the cost sheet's figures
are kept in docs/cost-sheet.json.

Exit codes: 0 loaded and checked, 1 a check failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from setup_db import psql  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HISTORY = REPO / "sample" / "history.json"
TAG = "$changedesk_history$"
SETTINGS = REPO / "settings" / "settings.json"
# In foreign-key order. The outbox (stage 5) is emptied first, by TRUNCATE (see above).
DATA_TABLES = ["agent_handoffs", "update_triggers", "updates", "decisions", "forecasts", "forecast_runs", "week_plan", "work_log",
               "scores", "status_history", "run_log", "requests"]
RESET_BY = "load_history.py --reset"


REQUEST_COLUMNS = {
    "request_id": "text", "source": "text", "requester_role": "text", "title": "text", "body": "text",
    "requester_due_date": "date", "requester_says_breaks": "text", "requester_says_harm": "text",
    "arrived_at": "timestamptz", "type": "text", "lane": "text", "size_hours": "numeric", "due_date": "date",
    "due_breaks": "text", "urgent": "boolean", "urgent_harm": "text", "goal_id": "text", "playbook": "text",
    "confidence": "numeric", "triage_reason": "text", "flags": "text", "triaged_by": "text", "triage_stamp": "text",
    "triaged_at": "timestamptz", "needs_confirmation": "boolean", "confirmation_reasons": "text",
    "lane_confirmed_by": "text", "lane_confirmed_at": "timestamptz", "lane_stamp": "text", "status": "text",
    "close_reason": "text", "merged_into": "text",
}
HISTORY_COLUMNS = {"request_id": "text", "from_status": "text", "to_status": "text", "changed_at": "timestamptz",
                   "changed_by": "text", "note": "text", "stamp": "text"}
SCORE_COLUMNS = {"request_id": "text", "part": "text", "points": "integer", "reason": "text", "set_by": "text",
                 "set_at": "timestamptz", "stamp": "text"}
WORK_COLUMNS = {"request_id": "text", "week_start": "date", "hours": "numeric", "logged_by": "text"}


def insert_sql(table: str, columns: dict[str, str], rows: list[dict], defaults: dict[str, str] | None = None) -> str:
    data = json.dumps(rows, ensure_ascii=False)
    if TAG in data:
        raise ValueError("the history holds the SQL quote tag")
    cols = list(columns)
    select = []
    for c in cols:
        if defaults and c in defaults:
            select.append(f"coalesce(r.{c}, {defaults[c]})")
        else:
            select.append(f"r.{c}")
    record = ", ".join(f"{c} {t}" for c, t in columns.items())
    return (f"insert into changedesk.{table} ({', '.join(cols)})\nselect {', '.join(select)}\n"
            f"from jsonb_to_recordset({TAG}{data}{TAG}::jsonb) as r({record});\n")


def settings_reset_sql(conf: dict) -> str:
    """Every setting back to its starting value, as a change with who and why (only those that differ, so the history
    shows each real change once)."""
    out = []
    for st in conf["settings"]:
        value = json.dumps(st["value"])
        if TAG in value:
            raise ValueError("a setting holds the SQL quote tag")
        source = st["source"].split(":")[0].replace("'", "''")  # a quote in the text must not end the SQL string
        out.append(f"update changedesk.settings set value = {TAG}{value}{TAG}::jsonb, changed_by = '{RESET_BY}', changed_at = now(), "
                   f"why = 'demo reset: back to the starting value ({source})' "
                   f"where key = '{st['key']}' and value is distinct from {TAG}{value}{TAG}::jsonb;")
    return "\n".join(out)


def load_sql(doc: dict, reset: bool, conf: dict | None = None, wrap: bool = True) -> str:
    """wrap=False leaves out begin and commit, so a test can run the whole load inside its own rolled-back transaction."""
    parts = ["begin;"] if wrap else []
    if reset:
        parts.append("truncate changedesk.outbox;")
        parts.append("delete from changedesk." + ";\ndelete from changedesk.".join(DATA_TABLES) + ";")
        parts.append("alter sequence changedesk.request_number restart with 1001;")
        parts.append(settings_reset_sql(conf or json.loads(SETTINGS.read_text(encoding="utf-8"))))
    else:
        parts.append("do $$ begin if exists (select 1 from changedesk.requests) then "
                     "raise exception 'the store already holds requests: use --reset to replace them'; end if; end $$;")
    # One statement, so a merged row may point at a request in the same load (the key is checked at its end).
    parts.append(insert_sql("requests", REQUEST_COLUMNS, doc["requests"], {"flags": "''", "needs_confirmation": "false",
                                                                           "confirmation_reasons": "''"}))
    parts.append(insert_sql("status_history", HISTORY_COLUMNS, doc["status_history"], {"note": "''"}))
    parts.append(insert_sql("scores", SCORE_COLUMNS, doc["scores"]))
    parts.append(insert_sql("work_log", WORK_COLUMNS, doc["work_log"]))
    if wrap:
        parts.append("commit;")
    return "\n".join(parts) + "\n"


CHECKS = {
    "requests loaded": "select count(*) from changedesk.requests",
    "requests with no status history": "select count(*) from changedesk.requests r where not exists "
                                       "(select 1 from changedesk.status_history h where h.request_id = r.request_id)",
    "triaged requests missing a lane or a reason": "select count(*) from changedesk.requests where status <> 'New' "
                                                   "and (lane is null or triage_reason is null)",
    "triaged requests without five score parts": "select count(*) from changedesk.requests r where status <> 'New' and "
                                                 "(select count(distinct part) from changedesk.scores s where s.request_id = r.request_id) <> 5",
    "requests in the inbox (New)": "select count(*) from changedesk.inbox",
    "hours in the work log": "select coalesce(sum(hours), 0) from changedesk.work_log",
    "items on the decide list today": "select count(*) from changedesk.decide_list",
    "hours of work a week (setting)": "select changedesk.setting_num('hours_per_week')",
    "small and quick share (setting)": "select changedesk.setting_num('small_share')",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reset", action="store_true", help="empty the Change Desk tables first (the demo reset)")
    args = ap.parse_args(argv)
    container = os.environ.get("SUPABASE_DB_CONTAINER", "supabase_db_hubspot-ai-database")
    try:
        doc = json.loads(HISTORY.read_text(encoding="utf-8"))
        psql(container, load_sql(doc, args.reset))
        got = {label: psql(container, sql + ";").strip() for label, sql in CHECKS.items()}
    except (RuntimeError, OSError, ValueError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    expected = doc["counts"]
    ok = (int(got["requests loaded"]) == expected["requests"] and got["requests with no status history"] == "0"
          and got["triaged requests missing a lane or a reason"] == "0" and got["triaged requests without five score parts"] == "0"
          and float(got["hours in the work log"]) == expected["hours_worked"])
    if args.reset:
        start = {st["key"]: st["value"] for st in json.loads(SETTINGS.read_text(encoding="utf-8"))["settings"]}
        ok = ok and float(got["hours of work a week (setting)"]) == start["hours_per_week"] \
            and float(got["small and quick share (setting)"]) == start["small_share"]
    print(f"Loaded sample/history.json (seed {doc['seed']}, {doc['weeks']} weeks from {doc['week_one']}).")
    for label, value in got.items():
        print(f"  {label}: {value}")
    print("PASS every request has a status history; every triaged one has a lane, a reason and five score parts"
          + ("; the settings are the starting values" if args.reset else "") if ok else "FAIL the store does not match the file")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
