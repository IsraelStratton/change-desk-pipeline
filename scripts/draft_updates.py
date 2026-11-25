#!/usr/bin/env python3
"""Draft the updates for three audiences behind the update trigger (the spec's stage 5, R20, R22 to R25). Started by hand,
or by scripts/forecast.py right after it saves a forecast run. Nothing is scheduled and nothing is sent.

The trigger (R20): an item whose 85% date moved by more than update_trigger_days (setting, 7) between a forecast run
and the run before it, or gained or lost its date. The triggers are logged first (changedesk.log_updates works them out
again from the forecasts rows). If nothing triggered, nothing is drafted. Otherwise one pack of facts is built for each
reader (R22):
  - each requester (by role) with an item that moved: every open item of theirs, each with its answer (R25): a date
    range (50, 85 and 95%), a service level, the chance of a fixed date and its latest safe start, a passed date with
    the person's decision as the next step, or a named next step when there is no date;
  - the desk manager: what changed since the last forecast, what moved, each lane's hours in and out, the service
    level, the fixed dates, this week's plan and the decisions waiting;
  - the executive sponsor: the few figures that say how the pipe stands.
Every fact is a row's value with its source, read through changedesk.fact_value: pipe data only, never request text.
One Claude call per pack (Haiku 5.5, engine/updates.js, the same code n8n could run), then the code check of the draft
(every figure traced to a fact, R23; every open item answered, R25; no promise, no internal code, no contact detail).
The drafts go to changedesk.updates through changedesk.log_updates, which refuses a fact that is not its row's value.
A person approves each one on the n8n approval form; an approved update goes to the outbox, and nowhere else (R24).

  python scripts/draft_updates.py                          # the latest forecast run, against the one before it
  python scripts/draft_updates.py --run fc-20261125T001500Z
  python scripts/draft_updates.py --dry-run                # build and print the packs; call nothing; keep nothing

The Claude key is read from .env (ANTHROPIC_API_KEY) and never printed.
Exit codes: 0 done (or nothing triggered), 1 a call failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk_db  # noqa: E402
import forecast as F  # noqa: E402
import planner as P  # noqa: E402
from desk_engine import MODEL, REPO, Engine, EngineError  # noqa: E402

OPEN = ["Triaged", "Planned", "In progress"]
STATUS_WORDS = {"Planned": "in this week's plan", "In progress": "started", "Triaged": "waiting its turn"}
LANE_WORDS = {"urgent": "urgent", "fixed_date": "fixed date", "small": "small and quick", "standard": "standard"}
REQUESTER_WORDS = {"base": 70, "per_item": 55}
# 320 from run 3 (25/11/2026): run 2's manager draft needed 301 words for what its brief asks (9 moved items with two dates
# each, four lanes, the plan and the decisions); the first limit, 230, was set before any live run.
MANAGER_WORDS = 320
# How a changed setting is named in the manager's pack: words only, so no figure comes in that is not a fact.
SETTING_WORDS = {"hours_per_week": "hours of work a week", "urgent_buffer_share": "the urgent buffer's share of the week",
                 "small_share": "the small and quick lane's share of the week", "standard_share": "the standard lane's share of the week",
                 "age_points_per_week": "points for each week waited", "age_limit_days_small": "the small lane's age limit in days",
                 "age_limit_days_standard": "the standard lane's age limit in days", "update_trigger_days": "the days an 85% date must move"}
EXECUTIVE_WORDS = 110


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


# ---------------------------------------------------------------- sources: where each fact is read from

def fc(run_id: str, rid: str, col: str) -> dict:
    return {"table": "forecasts", "where": {"run_id": run_id, "request_id": rid}, "column": col}


def fc_lane(run_id: str, lane: str, col: str) -> dict:
    return {"table": "forecasts", "where": {"run_id": run_id, "lane": lane, "request_id": None}, "column": col}


def req(rid: str, col: str) -> dict:
    return {"table": "requests", "where": {"request_id": rid}, "column": col}


def setting(key: str, index: int | None = None) -> dict:
    s = {"table": "settings", "where": {"key": key}, "column": "value"}
    if index is not None:
        s["index"] = index
    return s


def trig(run_id: str, rid: str, col: str) -> dict:
    return {"table": "update_triggers", "where": {"run_id": run_id, "request_id": rid}, "column": col}


class Pack:
    """One reader's facts. Each fact: id, kind (id, date, percent, number, text, flag), unit, says, source, value."""

    def __init__(self, audience: str, to_role: str, update_id: str, run: dict, prev: dict, today: date, word_limit: int):
        self.audience, self.to_role, self.update_id = audience, to_role, update_id
        self.run, self.prev, self.today, self.word_limit = run, prev, today, word_limit
        self.facts: list[dict] = []
        self._index: dict[str, str] = {}
        self.items: list[dict] = []
        self.titles: list[str] = []
        self.moved: list[str] = []
        self.plan_id: str | None = None

    def add(self, kind: str, says: str, source: dict, unit: str | None = None) -> str:
        key = json.dumps([kind, unit, source], sort_keys=True)
        if key in self._index:
            return self._index[key]
        fid = f"F{len(self.facts) + 1}"
        self.facts.append({"id": fid, "kind": kind, "unit": unit, "says": says, "source": source, "value": None})
        self._index[key] = fid
        return fid

    def doc(self) -> dict:
        return {"update_id": self.update_id, "audience": self.audience, "to_role": self.to_role, "today": self.today.isoformat(),
                "forecast_run_id": self.run["run_id"], "previous_run_id": self.prev["run_id"], "word_limit": self.word_limit,
                "facts": self.facts, "items": self.items, "titles": self.titles, "moved": self.moved}


def fill(conn, packs: list[Pack]) -> None:
    """Every fact's value, read from its source row by changedesk.fact_value (the store's one reader of facts)."""
    for p in packs:
        got = {r["id"]: r["v"] for r in desk_db.rows(conn, "select x->>'id' as id, changedesk.fact_value(x->'source') as v "
                                                          "from jsonb_array_elements(%s::jsonb) x", (json.dumps(p.facts),))}
        for f in p.facts:
            f["value"] = got[f["id"]]


# ---------------------------------------------------------------- the runs and the trigger

def forecast_run(conn, run_id: str | None) -> dict | None:
    if run_id:
        rows = desk_db.rows(conn, "select * from changedesk.forecast_runs where run_id = %s and purpose = 'forecast'", (run_id,))
    else:
        rows = desk_db.rows(conn, "select * from changedesk.forecast_runs where purpose = 'forecast' order by made_at desc, run_id desc limit 1")
    return rows[0] if rows else None


def previous_run(conn, run: dict) -> dict | None:
    rows = desk_db.rows(conn, "select * from changedesk.forecast_runs where purpose = 'forecast' and made_at < %s "
                              "order by made_at desc, run_id desc limit 1", (run["made_at"],))
    return rows[0] if rows else None


def fc_rows(conn, run_id: str) -> list[dict]:
    rows = desk_db.rows(conn, "select * from changedesk.forecasts where run_id = %s and request_id is not null order by request_id", (run_id,))
    for r in rows:
        for k in ("p50", "p85", "p95", "latest_safe_start"):
            r[k] = date.fromisoformat(r[k]) if r[k] else None
    return rows


def find_triggers(conn, run: dict, prev: dict, days: int) -> list[dict]:
    """R20, from the two runs' stored rows, with the same rule the forecast uses (scripts/forecast.py, triggers)."""
    old = {r["request_id"]: r["p85"] for r in fc_rows(conn, prev["run_id"])}
    return [{"run_id": run["run_id"], "previous_run_id": prev["run_id"], "request_id": r["request_id"]}
            for r, _ in F.triggers(old, fc_rows(conn, run["run_id"]), days)]


# ---------------------------------------------------------------- the three kinds of pack

def levels(p: Pack) -> dict[str, str]:
    return {lv: p.add("percent", f"the forecast's {lv} level", setting("forecast_levels", i)) for i, lv in enumerate(("50%", "85%", "95%"))}


def this_week(p: Pack, frow: dict) -> bool:
    """The forecast runs from this week's Monday, so work it finishes in this week's plan can carry a date before today (found in the
    first live run, up-20261125T001949Z). Such an item is told the week it is planned in, not a date that has gone."""
    end = date.fromisoformat(p.run["start_week"]) + timedelta(days=7)
    return frow["p85"] is not None and frow["p85"] < end and frow.get("planned", False)


def week_fact(p: Pack) -> str:
    return p.add("date", "the Monday of the week this week's plan covers",
                 {"table": "week_plan", "where": {"plan_id": p.plan_id}, "agg": "min", "column": "week_start"})


def item_facts(p: Pack, r: dict, frow: dict, triggered: set[str], decide: set[str], waiting: set[str], lv: dict) -> dict:
    """One requester item: its id, title, status, and its answer (R25) with the facts that give it."""
    rid, run, prev = r["request_id"], p.run["run_id"], p.prev["run_id"]
    f = {"id": p.add("id", f"{rid}: the request id", req(rid, "request_id")),
         "title": p.add("text", f"{rid}: its title", req(rid, "title"))}
    due = date.fromisoformat(r["due_date"]) if r.get("due_date") else None
    if rid in waiting:
        answer = "waits"
    elif frow["kind"] == "date_range" and this_week(p, frow):
        answer = "this_week"
        f["week"] = week_fact(p)
    elif frow["kind"] == "date_range":
        if frow["p85"] is None:
            answer = "no_date"
            f["age_limit_days"] = p.add("number", "the days a standard request may wait before a person decides on it",
                                        setting("age_limit_days_standard"), "days")
        else:
            answer = "date_range"
            for k, lvl in (("p50", "50%"), ("p85", "85%"), ("p95", "95%")):
                f[k] = p.add("date", f"{rid}: done by this date in {lvl} of the forecast's runs", fc(run, rid, k))
    elif frow["kind"] == "service_level" and frow["service_level_days"] is None:
        # The forecast gives the small lane no service level (too many of its items wait past the horizon): a named next step.
        answer = "no_date"
        f["age_limit_days"] = p.add("number", "the days a small request may wait before a person decides on it",
                                    setting("age_limit_days_small"), "days")
    elif frow["kind"] == "service_level":
        answer = "service_level"
        f["service_level_days"] = p.add("number", f"{rid}: small requests like it are done within this many days, 85% of the time",
                                        fc(run, rid, "service_level_days"), "days")
        f["level"] = lv["85%"]
    else:
        f["due_date"] = p.add("date", f"{rid}: the date it must be done by", req(rid, "due_date"))
        if due is not None and due < p.today:
            answer = "passed_date"
            if this_week(p, frow):
                f["week"] = week_fact(p)
            elif frow["p85"] is not None:
                f["p85"] = p.add("date", f"{rid}: done by this date in 85% of the forecast's runs, if still needed", fc(run, rid, "p85"))
        else:
            answer = "fixed_chance"
            f["chance"] = p.add("percent", f"{rid}: the chance of meeting its date", fc(run, rid, "chance"))
            f["latest_safe_start"] = p.add("date", f"{rid}: the latest day its work can start and still meet the date", fc(run, rid, "latest_safe_start"))
    if rid in triggered:
        f["old_p85"] = p.add("date", f"{rid}: its 85% date in the last forecast", fc(prev, rid, "p85"))
        if "p85" not in f and frow["p85"] is not None:
            f["p85"] = p.add("date", f"{rid}: its 85% date now", fc(run, rid, "p85"))
    if rid in decide:
        f["on_decide_list"] = p.add("flag", f"{rid}: on the list a person decides today",
                                    {"table": "decide_list_at", "as_of": p.today.isoformat(), "where": {"request_id": rid}, "agg": "count"})
    return {"request_id": rid, "title": r["title"], "answer": answer, "status_words": STATUS_WORDS.get(r["status"], r["status"].lower()),
            "moved": rid in triggered, "on_decide_list": rid in decide, "facts": f}


def requester_packs(conn, run, prev, today, triggers, up_run) -> list[Pack]:
    triggered = {t["request_id"] for t in triggers}
    frows = {r["request_id"]: r for r in fc_rows(conn, run["run_id"])}
    open_rows = desk_db.rows(conn, "select request_id, title, lane, status, requester_role, due_date from changedesk.requests "
                                   "where status = any(%s) and lane is not null order by arrived_at, request_id", (OPEN,))
    decide = {r["request_id"] for r in desk_db.rows(conn, "select request_id from changedesk.decide_list_at(%s)", (today,))}
    waiting = {r["request_id"] for r in desk_db.rows(conn, "select request_id from changedesk.awaiting_confirmation")}
    roles = sorted({r["requester_role"] for r in open_rows if r["request_id"] in triggered})
    plan = desk_db.rows(conn, "select plan_id from changedesk.week_plan order by made_at desc, plan_id desc limit 1")
    plan_id = plan[0]["plan_id"] if plan else None
    planned = {r["request_id"] for r in desk_db.rows(conn, "select request_id from changedesk.week_plan where plan_id = %s", (plan_id,))}
    for fr in frows.values():
        fr["planned"] = fr["request_id"] in planned
    packs = []
    for role in roles:
        mine = [r for r in open_rows if r["requester_role"] == role and r["request_id"] in frows]
        p = Pack("requester", role, f"U-{up_run}-req-{slug(role)}", run, prev, today,
                 REQUESTER_WORDS["base"] + REQUESTER_WORDS["per_item"] * len(mine))
        p.plan_id = plan_id
        lv = levels(p)
        p.add("number", f"requests {role} has open now", {"table": "requests", "where": {"requester_role": role, "status": OPEN}, "agg": "count"}, "items")
        for r in mine:
            p.items.append(item_facts(p, r, frows[r["request_id"]], triggered, decide, waiting, lv))
        p.moved = [r["request_id"] for r in mine if r["request_id"] in triggered]
        packs.append(p)
    return packs


def lane_facts(p: Pack, lane: str) -> None:
    run = p.run["run_id"]
    w = LANE_WORDS[lane]
    p.add("number", f"{w} lane: hours a week that arrive, in the forecast", fc_lane(run, lane, "hours_in_per_week"), "hours")
    p.add("number", f"{w} lane: hours a week that are worked, in the forecast", fc_lane(run, lane, "hours_out_per_week"), "hours")
    p.add("flag", f"{w} lane: takes in more than it puts out in the forecast", fc_lane(run, lane, "growing"))


def open_count(lane: str | None = None) -> dict:
    where = {"status": OPEN}
    if lane:
        where["lane"] = lane
    return {"table": "requests", "where": where, "agg": "count"}


def manager_pack(conn, run, prev, today, triggers, up_run) -> Pack:
    p = Pack("manager", "Desk manager", f"U-{up_run}-manager", run, prev, today, MANAGER_WORDS)
    levels(p)
    rid_run = run["run_id"]
    for h in desk_db.rows(conn, "select h.id, h.key, h.changed_by from changedesk.settings_history h "
                                "where h.changed_at > %s and h.changed_at <= %s order by h.id", (prev["made_at"], run["made_at"])):
        kind = "percent" if h["key"].endswith("_share") else "number"
        what = SETTING_WORDS.get(h["key"], h["key"].replace("_", " "))
        before = desk_db.rows(conn, "select id from changedesk.settings_history where key = %s and id < %s order by id desc limit 1", (h["key"], h["id"]))
        if before:
            p.add(kind, f"{what}, before the change", {"table": "settings_history", "where": {"id": before[0]["id"]}, "column": "value"})
        p.add(kind, f"{what}, after the change made by {h['changed_by']} since the last forecast",
              {"table": "settings_history", "where": {"id": h["id"]}, "column": "value"})
    p.add("number", "requests whose 85% date moved by more than a week since the last forecast",
          {"table": "update_triggers", "where": {"run_id": rid_run}, "agg": "count"}, "items")
    p.add("number", "days an 85% date must move before an update is drafted", setting("update_trigger_days"), "days")
    titles = desk_db.rows(conn, "select request_id, title from changedesk.requests where request_id = any(%s)", ([t["request_id"] for t in triggers],))
    tmap = {r["request_id"]: r["title"] for r in titles}
    for t in triggers:
        rid = t["request_id"]
        p.add("id", f"{rid} ({tmap.get(rid, '')}): moved", req(rid, "request_id"))
        p.add("date", f"{rid}: its 85% date in the last forecast", trig(rid_run, rid, "old_p85"))
        p.add("date", f"{rid}: its 85% date now", trig(rid_run, rid, "new_p85"))
        p.add("number", f"{rid}: days its 85% date moved (later is more)", trig(rid_run, rid, "moved_days"), "days")
        p.titles.append(tmap.get(rid, ""))
        p.moved.append(rid)
    for lane in P.LANES:
        lane_facts(p, lane)
        p.add("number", f"{LANE_WORDS[lane]} lane: open requests now", open_count(lane), "items")
    p.add("number", "small and quick lane: its items are done within this many days, 85% of the time, in the forecast",
          fc_lane(rid_run, "small", "service_level_days"), "days")
    for key, what in (("small_share", "the small and quick lane's share of the week"), ("standard_share", "the standard lane's share of the week"),
                      ("urgent_buffer_share", "the urgent buffer's share of the week")):
        p.add("percent", what, setting(key))
    p.add("number", "hours of work a week", setting("hours_per_week"), "hours")
    fixed = desk_db.rows(conn, "select request_id, title, due_date from changedesk.requests where lane = 'fixed_date' and status = any(%s) "
                               "order by due_date, request_id", (OPEN,))
    for r in fixed:
        rid = r["request_id"]
        p.titles.append(r["title"])
        p.add("id", f"{rid} ({r['title']}): a fixed-date request still open", req(rid, "request_id"))
        p.add("date", f"{rid}: the date it must be done by", req(rid, "due_date"))
        if date.fromisoformat(r["due_date"]) >= today:
            p.add("percent", f"{rid}: the chance of meeting its date", fc(rid_run, rid, "chance"))
            p.add("date", f"{rid}: the latest day its work can start and still meet the date", fc(rid_run, rid, "latest_safe_start"))
    dl = {"table": "decide_list_at", "as_of": today.isoformat()}
    p.add("number", "requests on the decide list today", dict(dl, agg="count"), "items")
    p.add("number", "of them, fixed-date requests whose date has passed", dict(dl, where={"why": "its fixed date has passed"}, agg="count"), "items")
    p.add("number", "of them, requests past their lane's age limit", dict(dl, where={"why": "past the age limit"}, agg="count"), "items")
    for r in desk_db.rows(conn, "select request_id, title, why from changedesk.decide_list_at(%s)", (today,)):
        p.titles.append(r["title"])
        p.add("id", f"{r['request_id']} ({r['title']}): on the decide list, {r['why']}", req(r["request_id"], "request_id"))
    p.add("number", "requests waiting for a person to confirm their lane or split", {"table": "awaiting_confirmation", "agg": "count"}, "items")
    plan = desk_db.rows(conn, "select plan_id from changedesk.week_plan order by made_at desc, plan_id desc limit 1")
    if plan:
        pid = plan[0]["plan_id"]
        p.add("date", "the Monday this week's plan starts", {"table": "week_plan", "where": {"plan_id": pid}, "agg": "min", "column": "week_start"})
        p.add("number", "hours in this week's plan", {"table": "week_plan", "where": {"plan_id": pid}, "agg": "sum", "column": "hours"}, "hours")
        for lane in desk_db.rows(conn, "select distinct lane from changedesk.week_plan where plan_id = %s order by lane", (pid,)):
            p.add("number", f"this week's plan: hours for the {LANE_WORDS[lane['lane']]} lane",
                  {"table": "week_plan", "where": {"plan_id": pid, "lane": lane["lane"]}, "agg": "sum", "column": "hours"}, "hours")
    return p


def executive_pack(conn, run, prev, today, up_run) -> Pack:
    p = Pack("executive", "Executive sponsor", f"U-{up_run}-executive", run, prev, today, EXECUTIVE_WORDS)
    levels(p)
    rid_run = run["run_id"]
    p.add("number", "requests open now (triaged, planned or started)", open_count(), "items")
    for lane in ("standard", "small"):
        lane_facts(p, lane)
    p.add("number", "small requests are done within this many days, 85% of the time, in the forecast",
          fc_lane(rid_run, "small", "service_level_days"), "days")
    p.add("number", "fixed dates that passed with the work still open",
          {"table": "decide_list_at", "as_of": today.isoformat(), "where": {"why": "its fixed date has passed"}, "agg": "count"}, "items")
    nxt = desk_db.rows(conn, "select request_id from changedesk.requests where lane = 'fixed_date' and status = any(%s) and due_date >= %s "
                             "order by due_date, request_id limit 1", (OPEN, today))
    if nxt:
        rid = nxt[0]["request_id"]
        p.add("date", "the next fixed date still open", req(rid, "due_date"))
        p.add("percent", "the chance of meeting the next fixed date", fc(rid_run, rid, "chance"))
    p.add("number", "requests whose expected date moved by more than a week since the last forecast",
          {"table": "update_triggers", "where": {"run_id": rid_run}, "agg": "count"}, "items")
    return p


# ---------------------------------------------------------------- the run

def draft(eng: Engine, client, packs: list[Pack], up_run: str, model: str) -> tuple[list, list, list]:
    from triage import call_claude

    calls, drafts, handoffs = [], [], []
    for p in packs:
        doc = p.doc()
        request = eng.call("buildUpdateRequest", doc, model)
        http, ms = call_claude(client, request)
        out = eng.call("checkUpdateDraft", doc, http, {"run_id": up_run, "source": "python", "model": model, "now": now_iso(), "latency_ms": ms})
        calls.append(out["call"])
        if out["draft"]:
            drafts.append(out["draft"])
            handoffs.append(out["handoff"])
    return calls, drafts, handoffs


def build_packs(conn, run: dict, prev: dict, today: date, triggers: list[dict], up_run: str) -> list[Pack]:
    packs = requester_packs(conn, run, prev, today, triggers, up_run)
    packs.append(manager_pack(conn, run, prev, today, triggers, up_run))
    packs.append(executive_pack(conn, run, prev, today, up_run))
    fill(conn, packs)
    return packs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", help="the forecast run (default: the latest)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry-run", action="store_true", help="build and print the packs; call nothing; keep nothing")
    ap.add_argument("--today", help="the date the updates are drafted on (default: today)")
    args = ap.parse_args(argv)
    load_dotenv(REPO / ".env")
    today = date.fromisoformat(args.today) if args.today else date.today()
    up_run = "up-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        eng = Engine("updates")
        with desk_db.connect(autocommit=False) as conn:
            run = forecast_run(conn, args.run)
            if run is None:
                print("CANNOT RUN no forecast run to draft from (run python scripts/forecast.py)")
                return 2
            prev = previous_run(conn, run)
            if prev is None:
                print(f"Forecast {run['run_id']} is the first: there is nothing to compare it with, so nothing is drafted.")
                return 0
            days = int(conn.execute("select changedesk.setting_num('update_trigger_days') as d").fetchone()["d"])
            triggers = find_triggers(conn, run, prev, days)
            if not triggers:
                print(f"Forecast {run['run_id']} against {prev['run_id']}: no 85% date moved by more than {days} days. Nothing is drafted (R20).")
                return 0
            desk_db.call_function(conn, "select changedesk.log_updates('[]'::jsonb, %s::jsonb, '[]'::jsonb, '[]'::jsonb)", triggers)
            packs = build_packs(conn, run, prev, today, triggers, up_run)
            if args.dry_run:
                conn.rollback()
                for p in packs:
                    print(json.dumps(eng.call("packForModel", p.doc()), indent=1))
                print(f"Dry run: {len(triggers)} triggers, {len(packs)} packs ({sum(p.audience == 'requester' for p in packs)} requesters, "
                      "the manager, the executive). Nothing was called or kept.")
                return 0
            conn.commit()
        import anthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(f"CANNOT DRAFT ANTHROPIC_API_KEY is not in .env. The {len(triggers)} triggers are logged; "
                  f"run python scripts/draft_updates.py --run {run['run_id']} once it is there.")
            return 2
        client = anthropic.Anthropic(max_retries=3)
        calls, drafts, handoffs = draft(eng, client, packs, up_run, args.model)
        with desk_db.connect() as conn:
            n = desk_db.call_function(conn, "select changedesk.log_updates(%s::jsonb, '[]'::jsonb, %s::jsonb, %s::jsonb) as n",
                                      calls, drafts, handoffs)["n"]
            summary = desk_db.rows(conn, "select * from changedesk.run_summary where run_id = %s", (up_run,))
    except (EngineError, LookupError, OSError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    print(f"Run {up_run}: forecast {run['run_id']} against {prev['run_id']}, {len(triggers)} items' 85% dates moved by more than {days} days.")
    print(f"{n} drafts for {len(packs)} readers ({sum(p.audience == 'requester' for p in packs)} requesters, the manager, the executive); "
          "each waits for a person on the approval form. Nothing was sent.")
    for d in drafts:
        print(f"  {d['update_id']}: {d['subject']}  [{'checks passed' if not d['draft_problems'] else 'PROBLEMS: ' + d['draft_problems']}]")
    if summary:
        s = summary[0]
        print(f"Cost: US${s['total_cost_usd']:.6f} for {s['calls']} calls, US${s['cost_per_call_usd']:.6f} an update. Failed calls: {s['failed']}.")
    import check_updates

    check_updates.main(["--run", up_run, "--write"])
    return 0 if all(c["output_valid"] for c in calls) else 1


if __name__ == "__main__":
    sys.exit(main())
