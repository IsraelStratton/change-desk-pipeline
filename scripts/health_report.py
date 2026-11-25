#!/usr/bin/env python3
"""Write the one-page pipe health report (KB-139 stage 3, R15 to R17): docs/reports/health.md.

For each lane, each week (the view changedesk.lane_health): in, out, open, the oldest age, items past the age limit,
fixed dates met, and urgent hours beyond the buffer (R15). The decide list (R16). And the lane growth flag (R17): a
lane that takes in more than it puts out for lane_growth_weeks complete weeks running (setting, 3) is flagged, and a
person is asked to choose: change the split, add hours, or say no. Read as the app's own login; it writes nothing to
the store. Nothing is scheduled: run it when the pipe changes.

  python scripts/health_report.py                    # as of today
  python scripts/health_report.py --as-of 2026-11-23

Exit codes: 0 written, 2 could not run.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk_db  # noqa: E402
import planner as P  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "docs" / "reports" / "health.md"
SHOW_WEEKS = 6
CHOICES = ("change the split (small_share, standard_share, urgent_buffer_share)", "add hours (hours_per_week)",
           "say no to some of what arrives (close it with a reason, through the decide list or at triage)")


def growth_flags(rows: list[dict], weeks_needed: int, as_of: date) -> dict[str, dict]:
    """R17. rows: changedesk.lane_health. For each lane, how many complete weeks running, up to the last complete week
    before as_of, took in more items than they put out; flagged when that run is at least weeks_needed."""
    out = {}
    for lane in P.LANES:
        weeks = sorted((r for r in rows if r["lane"] == lane and date.fromisoformat(str(r["week_start"])[:10]) + timedelta(days=7) <= as_of),
                       key=lambda r: str(r["week_start"]))
        run = 0
        for r in reversed(weeks):
            if int(r["arrived"]) > int(r["finished"]):
                run += 1
            else:
                break
        out[lane] = {"run": run, "flagged": run >= weeks_needed, "weeks": weeks[-max(weeks_needed, 1):]}
    return out


def ask_text(lane: str, flag: dict, weeks_needed: int) -> str:
    seen = ", ".join(f"{date.fromisoformat(str(w['week_start'])[:10]):%d/%m} in {w['arrived']}, out {w['finished']}" for w in flag["weeks"])
    return (f"**{P.LANE_WORDS[lane]} is growing:** more in than out for {flag['run']} weeks running ({seen}); the flag is set at "
            f"{weeks_needed}. When demand is above capacity, no order rule clears the lane; the rules only decide where the wait falls. "
            f"**A person is asked to choose:** " + "; or ".join(CHOICES) + ". A setting is changed with changedesk.set_setting, "
            "with who and why, and the next plan follows it.")


def report(rows: list[dict], decide: list[dict], fixed: list[dict], plan: list[dict], fc_lanes: list[dict], settings: dict, as_of: date) -> str:
    weeks_needed = int(settings["lane_growth_weeks"])
    complete = sorted({str(r["week_start"])[:10] for r in rows if date.fromisoformat(str(r["week_start"])[:10]) + timedelta(days=7) <= as_of})
    last = complete[-1] if complete else None
    shown = complete[-SHOW_WEEKS:]
    by = {(r["lane"], str(r["week_start"])[:10]): r for r in rows}
    flags = growth_flags(rows, weeks_needed, as_of)
    lines = [f"# Pipe health, as of {as_of:%d/%m/%Y}", "",
             "Made by `scripts/health_report.py` from the view `changedesk.lane_health` (R15), the decide list (R16) and the lane growth "
             f"flag (R17). Counts are items; a week runs Monday to Sunday. Every ticket is made up.", "",
             f"Made at the settings in the store on {as_of:%d/%m/%Y}: **{float(settings['hours_per_week']):g} hours a week**, small and quick "
             f"{float(settings['small_share']) * 100:g}%, standard {float(settings['standard_share']) * 100:g}%. Each past week's urgent hours beyond "
             "the buffer use the buffer of that week (changedesk.setting_num_at): 4 hours at 40 hours a week, 3.6 at 36.", ""]
    if last:
        lw = date.fromisoformat(last)
        lines += [f"## Each lane in the last complete week ({lw:%d/%m} to {lw + timedelta(days=6):%d/%m/%Y})", "",
                  "| Lane | In | Out | Open at the end | Oldest open (days) | Past the age limit | Fixed dates met | Urgent hours beyond the buffer |",
                  "|---|---|---|---|---|---|---|---|"]
        for lane in P.LANES:
            r = by[(lane, last)]
            fixed_cell = f"{r['fixed_dates_met']} of {r['fixed_dates_due']}" if lane == "fixed_date" else ""
            urgent_cell = f"{float(r['urgent_hours_beyond_buffer']):g}" if lane == "urgent" else ""
            past_cell = str(r["past_age_limit"]) if lane in ("small", "standard") else ""
            lines.append(f"| {P.LANE_WORDS[lane]} | {r['arrived']} | {r['finished']} | {r['open_at_end']} | {r['oldest_open_days'] if r['oldest_open_days'] is not None else ''} "
                         f"| {past_cell} | {fixed_cell} | {urgent_cell} |")
        lines += ["", f"## In against out, the last {len(shown)} complete weeks (in / out)", "",
                  "| Lane | " + " | ".join(f"{date.fromisoformat(w):%d/%m}" for w in shown) + " | Weeks running with more in than out |",
                  "|---|" + "---|" * len(shown) + "---|"]
        for lane in P.LANES:
            cells = []
            for w in shown:
                r = by[(lane, w)]
                cells.append(f"**{r['arrived']} / {r['finished']}**" if int(r["arrived"]) > int(r["finished"]) else f"{r['arrived']} / {r['finished']}")
            lines.append(f"| {P.LANE_WORDS[lane]} | " + " | ".join(cells) + f" | {flags[lane]['run']} |")
        lines += ["", "Bold: more in than out that week.", ""]
    lines += [f"## Lane growth flag (R17): more in than out, {weeks_needed} weeks running", ""]
    flagged = [lane for lane in P.LANES if flags[lane]["flagged"]]
    if flagged:
        for lane in flagged:
            lines += [ask_text(lane, flags[lane], weeks_needed), ""]
    else:
        lines += [f"No lane is flagged: none took in more than it put out for {weeks_needed} complete weeks running. "
                  + "; ".join(f"{P.LANE_WORDS[lane]} {flags[lane]['run']}" for lane in P.LANES) + " weeks running now.", ""]
    totals = {lane: sum(int(r["arrived"]) for r in rows if r["lane"] == lane and str(r["week_start"])[:10] in complete) for lane in P.LANES}
    outs = {lane: sum(int(r["finished"]) for r in rows if r["lane"] == lane and str(r["week_start"])[:10] in complete) for lane in P.LANES}
    lines += [f"Over all {len(complete)} complete weeks: " + "; ".join(f"{P.LANE_WORDS[lane]} {totals[lane]} in, {outs[lane]} out" for lane in P.LANES) + ".", ""]
    passed = [d for d in decide if d.get("why") == "its fixed date has passed"]
    lines += [f"## The decide list (R16): {len(decide)} items, {len(decide) - len(passed)} past their lane's age limit and "
              f"{len(passed)} past their fixed date", ""]
    if decide:
        lines += ["| Item | Lane | Why it is here | Age (days) | Limit | Days over |", "|---|---|---|---|---|---|"]
        for d in decide:
            limit = d["age_limit_days"] if d["age_limit_days"] is not None else f"due {d['due_date']:%d/%m/%Y}" if hasattr(d["due_date"], "strftime") \
                else f"due {date.fromisoformat(str(d['due_date'])):%d/%m/%Y}"
            lines.append(f"| {d['request_id']} {d['title']} | {P.LANE_WORDS[d['lane']]} | {d['why']} | {d['age_days']} | {limit} | {d['days_over']} |")
        lines += ["", "Each is decided on the n8n decide form: do it next, merge it, or close it with a reason. A fixed-date item whose date "
                  "has passed is listed at once, whatever its age (a build addition to R16, Israel's decision of 25/11/2026): "
                  "a person says whether it is still needed.", ""]
    lines += ["## Fixed dates still open", ""]
    if fixed:
        lines += ["| Item | Due | Latest safe start | |", "|---|---|---|---|"]
        for f in fixed:
            due = date.fromisoformat(f["due_date"])
            lss = due - timedelta(days=int(f["safe_start_days"]))
            state = "the date has passed" if due < as_of else ("at or past its latest safe start: planned first" if lss <= as_of + timedelta(days=6) else "not yet")
            lines.append(f"| {f['request_id']} {f['title']} | {due:%d/%m/%Y} | {lss:%d/%m/%Y} | {state} |")
        lines.append("")
    else:
        lines += ["None.", ""]
    if plan:
        week = plan[0]["week_start"]
        lines += [f"## This week's plan (week of {date.fromisoformat(week):%d/%m/%Y}, plan {plan[0]['plan_id']})", "",
                  "| Lane | Items | Hours |", "|---|---|---|"]
        for lane in P.LANES:
            mine = [p for p in plan if p["lane"] == lane]
            lines.append(f"| {P.LANE_WORDS[lane]} | {len(mine)} | {sum(float(p['hours']) for p in mine):g} |")
        lines += ["", "The working of every step: [week-plan.md](week-plan.md).", ""]
    if fc_lanes:
        lines += [f"## The latest forecast, by lane (run {fc_lanes[0]['run_id']})", ""]
        for f in fc_lanes:
            lines.append(f"- **{P.LANE_WORDS[f['lane']]}**: {f['note']}")
        lines += ["", "Every item's forecast: [forecast.md](forecast.md).", ""]
    if rows:
        lines += ["<details><summary>Every lane, every week</summary>", "",
                  "| Week | Lane | In | Out | Open | Oldest (days) | Past limit | Fixed due | Fixed met | Urgent beyond buffer |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: (str(r["week_start"]), P.LANES.index(r["lane"]))):
            lines.append(f"| {date.fromisoformat(str(r['week_start'])[:10]):%d/%m/%Y} | {P.LANE_WORDS[r['lane']]} | {r['arrived']} | {r['finished']} | {r['open_at_end']} "
                         f"| {r['oldest_open_days'] if r['oldest_open_days'] is not None else ''} | {r['past_age_limit']} | {r['fixed_dates_due']} | {r['fixed_dates_met']} "
                         f"| {float(r['urgent_hours_beyond_buffer']):g} |")
        lines += ["", "</details>", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of", help="the day the report is for (default: today)")
    args = ap.parse_args(argv)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    try:
        with desk_db.connect() as conn:
            settings = {s["key"]: s["value"] for s in desk_db.settings(conn)}
            rows = desk_db.rows(conn, "select * from changedesk.lane_health where week_start <= %s", (as_of,))
            decide = desk_db.rows(conn, "select * from changedesk.decide_list_at(%s)", (as_of,))
            import desk_state

            st = desk_state.load(conn)
            fixed = [dict(st.rows[i.request_id], due_date=i.due.isoformat(), safe_start_days=st.safe_start_days())
                     for i in P.fixed_order([i for i in st.items if i.lane == "fixed_date"])]
            plan = desk_db.rows(conn, "select plan_id, week_start, lane, request_id, hours from changedesk.week_plan where plan_id = "
                                      "(select plan_id from changedesk.week_plan order by made_at desc, plan_id desc limit 1)")
            fc_lanes = desk_db.rows(conn, "select f.run_id, f.lane, f.note from changedesk.forecasts f where f.request_id is null and f.run_id = "
                                          "(select run_id from changedesk.forecast_runs where purpose = 'forecast' order by made_at desc, run_id desc limit 1) "
                                          "order by array_position(array['urgent','fixed_date','small','standard'], f.lane)")
    except (LookupError, OSError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report(rows, decide, fixed, plan, fc_lanes, settings, as_of), encoding="utf-8")
    flags = growth_flags(rows, int(settings["lane_growth_weeks"]), as_of)
    print(f"Wrote {REPORT.relative_to(REPO)} as of {as_of:%d/%m/%Y}: {len(decide)} on the decide list; growth flags: "
          + ", ".join(f"{P.LANE_WORDS[lane]} {'FLAGGED' if f['flagged'] else 'no'} ({f['run']} weeks)" for lane, f in flags.items()) + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
