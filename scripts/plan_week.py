#!/usr/bin/env python3
"""Make the week's plan by hand: a plain script, not a model (the spec's stage 3, R12 to R14).

Reads the open work and the settings from the store as the app's own login, makes the plan with scripts/planner.py
(the same plan_week() the forecast and the rule test call), checks that the standard lane's order is the store's own
(changedesk.ranked_standard), saves it through changedesk.save_plan, and writes docs/reports/week-plan.md with the
working of every step, so the plan can be checked by hand. Items waiting for a person (R5) are never planned.

  python scripts/plan_week.py                      # the week holding today; save it; write the report
  python scripts/plan_week.py --week 2026-11-30    # another week (a Monday)
  python scripts/plan_week.py --dry-run            # make it and write the report; save nothing

Nothing is scheduled: run it when the pipe changes. Exit codes: 0 done, 1 a check failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk_db  # noqa: E402
import desk_state  # noqa: E402
import planner as P  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "docs" / "reports" / "week-plan.md"
MADE_BY = "planner (plain script)"


def plan_stamp(plan_id: str, at: str) -> str:
    return f"changedesk {plan_id} | no AI | planner@{P.PLANNER_VERSION} lanes rule (settings) | made by {MADE_BY} | {at}"


def order_agrees(conn, items: list[P.Item], week: date, rate: float) -> tuple[bool, list[str], list[str]]:
    """The planner's standard order against the store's changedesk.ranked_standard for the same day."""
    ids = {i.request_id for i in items if i.lane == "standard"}
    store = [r["request_id"] for r in desk_db.rows(conn, "select request_id from changedesk.ranked_standard(%s) order by rank", (week,))
             if r["request_id"] in ids]
    mine = [i.request_id for i in P.standard_order([i for i in items if i.lane == "standard" and i.arrived <= week], week, rate)]
    return mine == store, mine, store


def report(plan: P.WeekPlan, st: desk_state.DeskState, ps: P.PlanSettings, plan_id: str, saved: bool) -> str:
    s = st.settings
    titles = {i.request_id: i.title for i in st.items}
    rows = plan.rows()
    planned = {r["request_id"] for r in rows}
    lines = [
        f"# The week's plan: week of {plan.week_start:%d/%m/%Y}",
        "",
        f"Made by `scripts/plan_week.py` (a plain script, not a model; planner {P.PLANNER_VERSION}), plan `{plan_id}`"
        f"{'' if saved else ' (dry run, not saved)'}. Every ticket is made up.",
        "",
        "## The settings it used (changedesk.settings)",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Hours of work a week | {ps.hours_per_week:g} |",
        f"| Urgent buffer | {ps.urgent_buffer_share * 100:g}% ({ps.hours_per_week * ps.urgent_buffer_share:g} hours) |",
        f"| Small and quick share | {ps.small_share * 100:g}% ({ps.hours_per_week * ps.small_share:g} hours) |",
        f"| Standard share | {ps.standard_share * 100:g}% ({ps.hours_per_week * ps.standard_share:g} hours) |",
        f"| Points for each week waited | {ps.age_points_per_week:g} |",
        f"| Latest safe start | the due date less {ps.safe_start_days} days: the time fixed-date work has needed "
        f"{float(s['latest_safe_start_percentile']):.0%} of the time ({len(st.spans)} done items in the work log, spans {st.spans or 'none'} days) |",
        "",
        "## The working, step by step (a hand check follows it line by line)",
        "",
        "| Step | Hours it may take | Hours it took | Note |",
        "|---|---|---|---|",
    ]
    for step in plan.steps:
        lines.append(f"| {step.name} | {step.budget:g} | {step.used:g} | {step.note} |")
    lines += [f"| **The week** | **{plan.hours:g}** | **{plan.used:g}** | {plan.hours - plan.used:g} hours left |", "",
              "## The plan", "", "| # | Item | Lane | Hours | Why it is here |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['position']} | {r['request_id']} {titles.get(r['request_id'], '')} | {P.LANE_WORDS[r['lane']]} | {r['hours']:g} | {r['why']} |")
    lines += ["", "## Open work not in this week's plan", "", "| Lane | Items | Hours left |", "|---|---|---|"]
    for lane in P.LANES:
        rest = [i for i in st.items if i.lane == lane and i.request_id not in planned]
        part = [r for r in rows if r["lane"] == lane and abs(next(i.left for i in st.items if i.request_id == r["request_id"]) - r["hours"]) > 1e-6]
        note = f" (and {len(part)} planned in part)" if part else ""
        lines.append(f"| {P.LANE_WORDS[lane]} | {len(rest)}{note} | {sum(i.left for i in rest):g} |")
    if st.waiting:
        lines += ["", "## Waiting for a person, so not planned (R5)", ""]
        for w in st.waiting:
            lines.append(f"- {w['request_id']} {w['title']}: {'the lane' if w['lane_waits'] else 'the split'} waits for a person")
    passed = [i for i in st.items if i.lane == "fixed_date" and i.due and i.due < plan.week_start]
    if passed:
        lines += ["", "## Fixed dates already missed", "",
                  f"{len(passed)} fixed-date items are past their date and still open "
                  f"({', '.join(f'{i.request_id} due {i.due:%d/%m/%Y}' for i in passed)}). "
                  "They were missed under the old rule, before the lanes. Past their latest safe start, the rule plans them "
                  "at once. They are on the decide list (a build addition to R16, 25/11/2026): a person says whether each is still needed."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--week", help="the Monday of the week to plan (default: this week)")
    ap.add_argument("--dry-run", action="store_true", help="make the plan and the report; save nothing")
    args = ap.parse_args(argv)
    week = date.fromisoformat(args.week) if args.week else P.monday(date.today())
    if week.weekday() != 0:
        print(f"CANNOT RUN {week} is not a Monday")
        return 2
    try:
        with desk_db.connect() as conn:
            st = desk_state.load(conn)
            ps = st.plan_settings()
            agrees, mine, store = order_agrees(conn, st.items, week, ps.age_points_per_week)
            if not agrees:
                print("FAIL the planner's standard order is not changedesk.ranked_standard's: nothing saved")
                print(f"  planner: {mine[:10]}\n  store:   {store[:10]}")
                return 1
            plan = P.plan_week(st.items, week, ps, "lanes")
            at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            plan_id = f"plan-{week:%Y%m%d}-{datetime.now(timezone.utc):%H%M%S}"
            saved = 0
            if not args.dry_run:
                saved = desk_db.call_function(conn, "select changedesk.save_plan(%s::jsonb) as n", {
                    "plan_id": plan_id, "week_start": week.isoformat(), "made_by": MADE_BY, "made_at": at,
                    "stamp": plan_stamp(plan_id, at), "rows": plan.rows()})["n"]
    except (LookupError, OSError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report(plan, st, ps, plan_id, bool(saved)), encoding="utf-8")
    print(f"Plan {plan_id} for the week of {week:%d/%m/%Y}: {len(plan.rows())} items, {plan.used:g} of {plan.hours:g} hours"
          f"{'' if saved else ' (dry run, not saved)'}. The standard order agrees with changedesk.ranked_standard.")
    for step in plan.steps:
        print(f"  {step.name}: took {step.used:g} of {step.budget:g}. {step.note}")
    for r in plan.rows():
        print(f"  {r['position']:>2}. {r['request_id']} {P.LANE_WORDS[r['lane']]:<15} {r['hours']:>4g} h  {r['why']}")
    print(f"Wrote {REPORT.relative_to(REPO)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
