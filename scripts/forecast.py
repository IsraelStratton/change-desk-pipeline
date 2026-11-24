#!/usr/bin/env python3
"""The forecast by lane, and the update trigger (KB-139 stage 4, R18 to R20). A plain script, started by hand.

One forecast for each lane, from that lane's own history (R18). Every open item gets one of three:
  - standard (and urgent) work: the dates it is done by in 50, 85 and 95% of runs (setting forecast_levels);
  - small items: no date each, but one service level: 85% of the small items that arrive in the run are done within
    so many days;
  - fixed-date items: the chance of meeting the date, and the latest safe start.
How: forecast_runs runs (setting) of the next forecast_horizon_weeks weeks. Each run starts from the open work in the
store. From next week on, each lane gets new arrivals each week, copied from one of its own past weeks drawn at random
(R19: new arrivals are in the run). Every week of every run is planned by scripts/planner.py's plan_week(), the same
code that makes the real week's plan (R13), and worked. A fixed seed (setting forecast_seed) makes the same store and
settings give the same forecast. When a lane takes in more hours than it puts out in the run, the output says so, and
an item not done within the horizon in enough runs gets no date at that level: no finish date for the tail.

The update trigger (R20): the forecast is run again by hand when the pipe changes. An update is drafted for an item
only when its 85% date moves by more than update_trigger_days (setting, 7) from the last forecast, or it gains or
loses its 85% date. The draft is a plain template filled from the forecast rows (no AI; stage 5 adds the drafts for
three audiences). It waits in changedesk.updates as a draft: nothing is sent to anyone.

  python scripts/forecast.py                  # forecast from this week; save it; draft what the trigger asks for
  python scripts/forecast.py --dry-run        # forecast and report; save nothing
  python scripts/forecast.py --load 1.15      # a what-if run with heavier demand; saved as what-if, drafts nothing

Exit codes: 0 done, 2 could not run.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk_db  # noqa: E402
import planner as P  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO / "docs" / "reports"
KIND = {"urgent": "date_range", "standard": "date_range", "fixed_date": "chance_of_date", "small": "service_level"}
TRIGGER_BY = "update trigger (template, no AI)"


def d(x: date | None) -> str:
    return f"{x:%d/%m/%Y}" if x else "no date"


def middle(levels: list[float]) -> float:
    """The level the update trigger and the service level use: the middle one, 85%."""
    xs = sorted(levels)
    return xs[len(xs) // 2]


def forecast_rows(sim: P.SimResult, items: list[P.Item], waiting: list[dict], ps: P.PlanSettings, levels: list[float],
                  past_small: list[int | None] | None = None) -> tuple[list[dict], list[dict]]:
    """One row per open item and one per lane, as changedesk.log_forecast takes them. past_small: the days each small item
    of the history took from arrival to done, None for one still waiting."""
    levels = sorted(levels)
    lv = middle(levels)
    growing = {lane: sim.hours_in_per_week[lane] > sim.hours_out_per_week[lane] + 0.05 for lane in P.LANES}
    flow = {lane: f"{sim.hours_in_per_week[lane]:g} hours a week arrive in the run and {sim.hours_out_per_week[lane]:g} are worked" for lane in P.LANES}
    sl_days = P.nearest_rank(sim.new_small_cycle_days, lv) if sim.new_small_cycle_days else None
    tail_note = {lane: (f" The {P.LANE_WORDS[lane].lower()} lane takes in more than it puts out in this run ({flow[lane]}): "
                        "no finish date is given for the tail.") if growing[lane] else "" for lane in P.LANES}
    rows = []
    for it in items:
        dates = sim.finish[it.request_id]
        p50, p85, p95 = P.level_dates(dates, levels)
        base = {"request_id": it.request_id, "lane": it.lane, "kind": KIND[it.lane], "p50": p50, "p85": p85, "p95": p95,
                "service_level_days": None, "chance": None, "latest_safe_start": None}
        missing = [f"{p:.0%}" for p, x in zip(levels, (p50, p85, p95)) if x is None]
        gap = (f" Not done within {sim.horizon} weeks in too many runs: no {', '.join(missing)} date." if missing else "")
        if it.lane in ("urgent", "standard"):
            note = f"Done by {d(p50)} in half the runs, by {d(p85)} in 85%, by {d(p95)} in 95%." if not missing else \
                   (f"Done by {d(p50)} in half the runs." if p50 else "") + gap
            rows.append(dict(base, note=(note + (tail_note[it.lane] if missing else "")).strip()))
        elif it.lane == "fixed_date":
            chance = P.chance_by(dates, it.due)
            lss = P.latest_safe_start(it, ps)
            if it.due < sim.start_week:
                note = f"The date {d(it.due)} passed before this forecast: it cannot be met. Done by {d(p85)} in 85% of runs."
                chance = 0.0
            else:
                note = f"{chance:.0%} chance of meeting {d(it.due)}; latest safe start {d(lss)}."
            rows.append(dict(base, chance=chance, latest_safe_start=lss, note=note + gap))
        else:
            rows.append(dict(base, p50=None, p85=None, p95=None, service_level_days=sl_days,
                             note=(f"Service level: {lv:.0%} of small items are done within {sl_days} days." if sl_days is not None
                                   else "No service level: too many small items are not done within the horizon." + tail_note["small"])))
    for w in waiting:
        rows.append({"request_id": w["request_id"], "lane": w["lane"], "kind": KIND[w["lane"]], "p50": None, "p85": None, "p95": None,
                     "service_level_days": None, "chance": None, "latest_safe_start": None,
                     "note": f"Waits for a person to confirm its {'lane' if w.get('lane_waits') else 'split'}: no forecast until then."})
    lanes = []
    for lane in P.LANES:
        mine = [it for it in items if it.lane == lane]
        done = sum(x is not None for it in mine for x in sim.finish[it.request_id])
        share = round(done / (len(mine) * sim.runs), 3) if mine else None
        row = {"request_id": None, "lane": lane, "kind": KIND[lane], "p50": None, "p85": None, "p95": None, "service_level_days": None,
               "chance": None, "latest_safe_start": None, "hours_in_per_week": sim.hours_in_per_week[lane],
               "hours_out_per_week": sim.hours_out_per_week[lane], "growing": growing[lane], "finished_share": share}
        tail = sum(1 for r in rows if r["lane"] == lane and r["request_id"] in {it.request_id for it in mine} and r["p85"] is None) \
            if lane in ("urgent", "standard", "fixed_date") else 0
        if growing[lane] and lane != "small":
            grow = (f"; it takes in more than it puts out, so its queue grows: {tail} of its {len(mine)} open items get no 85% date (the tail)"
                    if tail else f"; it takes in more than it puts out, so its queue grows. All {len(mine)} of its open items still get dates, "
                    "because points for waiting lift them above new work; the new work behind them is the tail, and it waits longer and longer")
        elif growing[lane]:
            grow = "; it takes in more than it puts out, so its queue grows and its wait gets longer"
        else:
            grow = ""
        head = f"{flow[lane]}{grow}."
        if lane == "small":
            row["service_level_days"] = sl_days
            past = ""
            if past_small:
                waited = sum(x is None for x in past_small)
                p_days = P.nearest_rank(past_small, lv)
                past = (f" Under the old rule, {lv:.0%} of small items were done within {p_days} days" if p_days is not None
                        else f" Under the old rule, fewer than {lv:.0%} of small items were done") + \
                       (f", but {waited} of {len(past_small)} were never done and are still waiting." if waited else ".")
            head += (f" Service level: {lv:.0%} of the small items that arrive in the run are done within {sl_days} days." if sl_days is not None
                     else " No service level can be given.") + past
        elif lane == "fixed_date" and mine:
            open_dates = [r for r in rows if r["lane"] == "fixed_date" and r["chance"] is not None]
            row["chance"] = round(sum(r["chance"] for r in open_dates) / len(open_dates), 3) if open_dates else None
            head += f" {len(mine)} open; average chance of the date {row['chance']:.0%}." if row["chance"] is not None else ""
        if mine:
            head += f" Its {len(mine)} open items are done within {sim.horizon} weeks in {share:.0%} of item-runs."
        row["note"] = head.strip()
        lanes.append(row)
    return rows, lanes


def triggers(prev: dict[str, date | None], rows: list[dict], days: int) -> list[tuple[dict, date | None]]:
    """R20: the items whose 85% date moved by more than days since the previous forecast, or gained or lost it.
    prev: request_id to its 85% date in the previous forecast run (missing: no previous forecast for it)."""
    out = []
    for r in rows:
        if r["request_id"] is None or r["request_id"] not in prev or r["kind"] == "service_level":
            continue
        old, new = prev[r["request_id"]], r["p85"]
        if old is None and new is None:
            continue
        if old is None or new is None or abs((new - old).days) > days:
            out.append((r, old))
    return out


def update_draft(row: dict, old: date | None, info: dict, run_id: str, now: str, days: int) -> dict:
    """A plain status update for the requester, filled from the forecast rows only. A draft: nobody sends it."""
    rid, new = row["request_id"], row["p85"]
    head = f"Hello, {info['requester_role']}.\n\nThis is an update on your request {rid}, \"{info['title']}\"."
    if new and old:
        line = (f" We now expect it to be done by {new:%d %B %Y}; before, we expected {old:%d %B %Y}. We give the date we are 85% sure of, "
                "and it moves when other work arrives or the team's hours change.")
    elif new:
        line = f" We can now give a date: we expect it to be done by {new:%d %B %Y}, the date we are 85% sure of."
    else:
        line = (f" Before, we expected it by {old:%d %B %Y}. We cannot give a date at the moment: more work is arriving than the team "
                "can finish, so the queue is growing.")
    body = head + line + "\n\nNothing is needed from you. If the need has changed, please raise a new request through the desk's intake form."
    uid = f"U-{run_id}-{rid}"
    return {"update_id": uid, "request_id": rid, "subject": f"An update on your request {rid}", "body": body, "drafted_by": TRIGGER_BY,
            "drafted_at": now, "draft_problems": "",
            "stamp": f"changedesk {uid} | no AI | update trigger@{P.PLANNER_VERSION} (85% date moved more than {days} days) | drafted by update trigger | {now}"}


def run_forecast(conn, start_week: date, load: float = 1.0, runs: int | None = None):
    """Read the store, run the forecast, and build its rows. Returns (state, sim, rows, lanes, run settings)."""
    import desk_state

    st = desk_state.load(conn)
    ps = st.plan_settings()
    s = st.settings
    n_hist = desk_state.history_weeks(st, start_week)
    hist = P.lane_history(desk_state.arrivals(conn), st.first_week, n_hist) if st.first_week else {}
    runs = runs or int(s["forecast_runs"])
    sim = P.simulate(st.items, hist, ps, start_week, "lanes", runs, int(s["forecast_horizon_weeks"]), int(s["forecast_seed"]), load)
    # The small lane's past service level: every small item that arrived in the history weeks, done or not. One still
    # waiting counts as not done (None), so a lane that starved its small work cannot look quick.
    past = [r["days"] for r in desk_db.rows(conn, "select case when e.done_at is not null then e.done_at::date - e.arrived_at::date end as days "
                                                  "from changedesk.request_ends e join changedesk.requests r on r.request_id = e.request_id "
                                                  "where e.lane = 'small' and r.status not in ('Closed', 'Merged') "
                                                  "and e.arrived_at >= %s and e.arrived_at < %s",
                                            (st.first_week, start_week))] if st.first_week else []
    rows, lanes = forecast_rows(sim, st.items, st.waiting, ps, [float(x) for x in s["forecast_levels"]], past or None)
    return st, ps, sim, rows, lanes, n_hist


def report(st, ps, sim: P.SimResult, rows: list[dict], lanes: list[dict], run_id: str, load: float, n_hist: int, purpose: str,
           drafts: list[dict], first_run: bool, saved: bool) -> str:
    info = {**{i.request_id: i for i in st.items}}
    lines = [f"# The forecast by lane{' (what-if: demand x ' + f'{load:g})' if purpose == 'what-if' else ''}", "",
             f"Made by `scripts/forecast.py`, run `{run_id}`{'' if saved else ' (dry run, not saved)'}: {sim.runs} runs of the {sim.horizon} weeks "
             f"from {sim.start_week:%d/%m/%Y}, seed {st.settings['forecast_seed']}, new arrivals from each lane's own {n_hist} weeks of history"
             f"{f', at {load:g} times the usual demand' if load != 1 else ''}. Every week of every run is planned by the planner's `plan_week()`, "
             "the same code as the week's plan. Every ticket is made up.", "",
             "## Each lane", "", "| Lane | Hours in a week (run) | Hours worked a week (run) | Takes in more than it puts out | |",
             "|---|---|---|---|---|"]
    for ln in lanes:
        lines.append(f"| {P.LANE_WORDS[ln['lane']]} | {ln['hours_in_per_week']:g} | {ln['hours_out_per_week']:g} | {'**yes**' if ln['growing'] else 'no'} | {ln['note']} |")
    for lane in P.LANES:
        mine = [r for r in rows if r["lane"] == lane]
        if not mine:
            continue
        lines += ["", f"## {P.LANE_WORDS[lane]}", ""]
        if lane in ("urgent", "standard"):
            lines += ["| Item | 50% | 85% | 95% | |", "|---|---|---|---|---|"]
            for r in sorted(mine, key=lambda r: (r["p85"] is None, r["p85"] or date.max, r["request_id"])):
                t = info[r["request_id"]].title if r["request_id"] in info else ""
                lines.append(f"| {r['request_id']} {t} | {d(r['p50'])} | {d(r['p85'])} | {d(r['p95'])} | {r['note'] if r['p95'] is None else ''} |")
        elif lane == "fixed_date":
            lines += ["| Item | Due | Chance of the date | Latest safe start | 85% done by |", "|---|---|---|---|---|"]
            for r in mine:
                it = info.get(r["request_id"])
                chance = "" if r["chance"] is None else f"{r['chance']:.0%}"
                lines.append(f"| {r['request_id']} {it.title if it else ''} | {d(it.due) if it else ''} | {chance} | "
                             f"{d(r['latest_safe_start'])} | {d(r['p85'])} |")
        else:
            lines += [f"{len(mine)} open small items; no date for each (KB-136 section 6.4). {mine[0]['note']}"]
    lines += ["", "## The update trigger (R20)", ""]
    if purpose == "what-if":
        lines.append("A what-if run triggers no update.")
    elif first_run:
        lines.append("No earlier forecast to compare with, so nothing is drafted. The next run, after the pipe changes, compares its 85% dates with these.")
    elif drafts:
        lines += [f"{len(drafts)} items' 85% date moved by more than {st.settings['update_trigger_days']} days, so {len(drafts)} updates were drafted "
                  "for a person to approve (nothing is sent):", ""] + [f"- {u['request_id']}: {u['body'].splitlines()[2]}" for u in drafts]
    else:
        lines.append(f"No item's 85% date moved by more than {st.settings['update_trigger_days']} days since the last forecast, so nothing is drafted.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--week", help="the Monday the forecast starts from (default: this week)")
    ap.add_argument("--load", type=float, default=1.0, help="demand as a multiple of each lane's own history (a what-if run)")
    ap.add_argument("--runs", type=int, help="override forecast_runs for this run only (a what-if run)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    start = date.fromisoformat(args.week) if args.week else P.monday(date.today())
    purpose = "what-if" if (args.load != 1.0 or args.runs) else "forecast"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    run_id = ("fc-" if purpose == "forecast" else "wi-") + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        with desk_db.connect() as conn:
            st, ps, sim, rows, lanes, n_hist = run_forecast(conn, start, args.load, args.runs)
            prev_run = conn.execute("select run_id from changedesk.forecast_runs where purpose = 'forecast' order by made_at desc, run_id desc limit 1").fetchone()
            drafts = []
            if purpose == "forecast" and prev_run:
                prev = {r["request_id"]: (date.fromisoformat(r["p85"]) if r["p85"] else None)
                        for r in desk_db.rows(conn, "select request_id, p85 from changedesk.forecasts where run_id = %s and request_id is not null",
                                              (prev_run["run_id"],))}
                info = {r["request_id"]: r for r in st.rows.values()}
                drafts = [update_draft(r, old, info[r["request_id"]], run_id, now, int(st.settings["update_trigger_days"]))
                          for r, old in triggers(prev, rows, int(st.settings["update_trigger_days"]))]
            run = {"run_id": run_id, "purpose": purpose, "start_week": start.isoformat(), "rule": "lanes", "runs": sim.runs,
                   "horizon_weeks": sim.horizon, "seed": int(st.settings["forecast_seed"]), "load": args.load, "safe_start_days": ps.safe_start_days,
                   "settings": st.settings, "summary": {"history_weeks": n_hist, "open_items": len(st.items), "waiting": len(st.waiting),
                                                        "drafts": len(drafts), "previous_run": prev_run["run_id"] if prev_run else None},
                   "made_by": "forecast (plain script)", "made_at": now,
                   "stamp": f"changedesk {run_id} | no AI | forecast@{P.PLANNER_VERSION} lanes rule, {sim.runs} runs, seed {st.settings['forecast_seed']} | made by forecast (plain script) | {now}"}
            if not args.dry_run:
                desk_db.call_function(conn, "select changedesk.log_forecast(%s::jsonb, %s::jsonb, %s::jsonb)", run, rows + lanes, drafts)
    except (LookupError, OSError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    name = "forecast.md" if purpose == "forecast" else "forecast-what-if.md"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / name).write_text(report(st, ps, sim, rows, lanes, run_id, args.load, n_hist, purpose, drafts, prev_run is None, not args.dry_run),
                                encoding="utf-8")
    print(f"Forecast {run_id} ({purpose}{', dry run' if args.dry_run else ''}): {sim.runs} runs x {sim.horizon} weeks from {start:%d/%m/%Y}, "
          f"load {args.load:g}, {len(rows)} items.")
    for ln in lanes:
        print(f"  {P.LANE_WORDS[ln['lane']]:<16} {ln['note']}")
    print(f"  Update trigger: {'what-if, none' if purpose == 'what-if' else ('first forecast, nothing to compare' if prev_run is None else f'{len(drafts)} drafted')}.")
    print(f"Wrote docs/reports/{name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
