#!/usr/bin/env python3
"""The back-check (the spec's stage 4, R21): forecast from week 8 of the sample history, and compare with what happened in
weeks 9 to 12. The share of items that finished inside their 85% range is reported, whatever it is.

The forecast is the same code as scripts/forecast.py: the planner's simulate() and plan_week(), and forecast.py's
forecast_rows(). It knows only what was known at the end of week 8: the work open then, with the hours still to do, and
each lane's own arrivals in weeks 1 to 8. The history was worked "highest score first", so the forecast plans by that
rule (a forecast must model the rule the team works by). Then the history's own weeks 9 to 12 say what happened.

"Inside the 85% range": done on or before its 85% date. An item still open at the end of week 12 whose 85% date is
later than that is not yet known, and is counted apart. Items a person closed or merged count neither way.

  python scripts/back_check.py           # print it, write docs/reports/back-check.md and the README's lines
  python scripts/back_check.py --check   # exit 1 if either is not what the script makes now

A plain script, no database: the sample history file only. Exit codes: 0 done (or up to date), 1 out of date, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import forecast as F  # noqa: E402
import planner as P  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HISTORY = REPO / "sample" / "history.json"
SETTINGS = REPO / "settings" / "settings.json"
REPORT = REPO / "docs" / "reports" / "back-check.md"
README = REPO / "README.md"
START, END = "<!-- back-check:start (made by scripts/back_check.py) -->", "<!-- back-check:end -->"
FROM_WEEK = 8
RULE = "highest score first"


def state_at(doc: dict, s: dict, start: date) -> tuple[list[P.Item], dict[str, date], set[str], list[P.Item]]:
    """What was known at the start of week FROM_WEEK + 1: the open items with their hours left, when each was really
    done, which a person closed or merged later, and every item (for the lanes' own history)."""
    items, _ = P.history_items(doc, s["score_weights"])
    cut = datetime.combine(start, time(0), P.TEAM_TZ)
    ended_before, done_at, person_later = set(), {}, set()
    for h in sorted(doc["status_history"], key=lambda h: h["changed_at"]):
        at = P.parse_ts(h["changed_at"])
        if h["to_status"] in ("Done", "Closed", "Merged") and at < cut:
            ended_before.add(h["request_id"])
        if h["to_status"] == "Done":
            done_at.setdefault(h["request_id"], at.astimezone(P.TEAM_TZ).date())
        if h["to_status"] in ("Closed", "Merged") and at >= cut:
            person_later.add(h["request_id"])
    worked: dict[str, float] = {}
    for w in doc["work_log"]:
        if date.fromisoformat(w["week_start"]) < start:
            worked[w["request_id"]] = worked.get(w["request_id"], 0.0) + float(w["hours"])
    open_items = []
    for i in items:
        if i.arrived_at < cut and i.request_id not in ended_before:
            open_items.append(P.replace(i, left=i.size - worked.get(i.request_id, 0.0)))
    return open_items, done_at, person_later, items


def judge(p: date | None, done: date | None, window_end: date) -> str:
    """One item against one forecast date. An item given no date at that level (the tail) is judged apart."""
    finished = done is not None and done <= window_end
    if p is None:
        return "no date, done anyway" if finished else "no date, still open"
    if finished:
        return "inside" if done <= p else "outside"
    return "outside" if p <= window_end else "not yet known"


def pct(a: int, n: int) -> str:
    return f"{100 * a / n:.0f}%" if n else "none"


def build() -> tuple[str, str]:
    s = {x["key"]: x["value"] for x in json.loads(SETTINGS.read_text(encoding="utf-8"))["settings"]}
    doc = json.loads(HISTORY.read_text(encoding="utf-8"))
    week_one = date.fromisoformat(doc["week_one"])
    start = week_one + timedelta(weeks=FROM_WEEK)
    window_end = week_one + timedelta(weeks=doc["weeks"]) - timedelta(days=1)
    open_items, done_at, person_later, every = state_at(doc, s, start)
    ps = P.PlanSettings.from_settings(s, P.history_safe_start_days(doc, float(s["latest_safe_start_percentile"])))
    hist = P.lane_history(every, week_one, FROM_WEEK)
    levels = sorted(float(x) for x in s["forecast_levels"])
    sim = P.simulate(open_items, hist, ps, start, RULE, int(s["forecast_runs"]), int(s["forecast_horizon_weeks"]), int(s["forecast_seed"]),
                     arrivals_from=0)
    rows, lanes = F.forecast_rows(sim, open_items, [], ps, levels)
    by_id = {r["request_id"]: r for r in rows}
    counts: dict[str, int] = {}
    calib = {lv: [0, 0] for lv in levels}
    detail, fixed = [], []
    for it in open_items:
        if it.request_id in person_later:
            continue
        p50, p85, p95 = P.level_dates(sim.finish[it.request_id], levels)
        done = done_at.get(it.request_id)
        if it.lane == "fixed_date":
            met = done is not None and done <= it.due
            fixed.append((it, by_id[it.request_id]["chance"], met, done))
            detail.append((it, p50, p85, p95, done, f"chance {by_id[it.request_id]['chance']:.0%}; {'met' if met else 'missed'}"))
            continue
        if it.lane == "small":
            detail.append((it, None, None, None, done, "service level (below)"))
            continue
        verdict = judge(p85, done, window_end)
        counts[verdict] = counts.get(verdict, 0) + 1
        for lv, pd in zip(levels, (p50, p85, p95)):
            v = judge(pd, done, window_end)
            if v in ("inside", "outside"):
                calib[lv][0] += v == "inside"
                calib[lv][1] += 1
        detail.append((it, p50, p85, p95, done, verdict))
    # The small lane's service level is for the small items that arrive in the run, so it is checked against the small
    # items that arrived in weeks 9 to 12; one still open is outside once it has waited longer than the level.
    sl = next(ln["service_level_days"] for ln in lanes if ln["lane"] == "small")
    small_in = small_n = small_unknown = 0
    if sl is not None:
        for i in (x for x in every if x.lane == "small" and start <= x.arrived_local <= window_end and x.request_id not in person_later):
            done = done_at.get(i.request_id)
            if done is not None and done <= window_end:
                small_n += 1
                small_in += (done - i.arrived_local).days <= sl
            elif (window_end - i.arrived_local).days > sl:
                small_n += 1
            else:
                small_unknown += 1
    ins, outs = counts.get("inside", 0), counts.get("outside", 0)
    pending, tail_open, tail_done = counts.get("not yet known", 0), counts.get("no date, still open", 0), counts.get("no date, done anyway", 0)
    head = (f"Forecast from the end of week {FROM_WEEK} ({start - timedelta(days=1):%d/%m/%Y}), by the rule the history was worked by "
            f"({RULE}), {sim.runs} runs, seed {s['forecast_seed']}, compared with weeks {FROM_WEEK + 1} to {doc['weeks']}:")
    block_lines = [head, "",
                   f"- **Standard and urgent work: {ins} of {ins + outs} items ({pct(ins, ins + outs)}) finished inside their 85% range** "
                   "(done on or before their 85% date)."
                   + (f" {pending} more are still open with an 85% date after week {doc['weeks']}: not yet known." if pending else ""),
                   f"- {tail_open + tail_done} standard items got no 85% date (the tail of a lane growing under the old rule): "
                   f"{tail_open} of them were still open at the end of week {doc['weeks']}" + (f", and {tail_done} were done anyway." if tail_done else "."),
                   "- The other levels, as a check of the spread: " + "; ".join(
                       f"{pct(a, n)} done by their {lv:.0%} date ({a} of {n})" for lv, (a, n) in calib.items()) + "."]
    if fixed:
        block_lines.append(f"- Fixed dates open at week {FROM_WEEK}: " + "; ".join(
            f"{it.request_id} due {it.due:%d/%m}, given a {ch:.0%} chance, {'met' if met else 'missed'}" for it, ch, met, _ in fixed) + ".")
    if sl is not None:
        block_lines.append(f"- Small items that arrived in weeks {FROM_WEEK + 1} to {doc['weeks']}, against the forecast's service level "
                           f"({levels[1]:.0%} within {sl} days): {small_in} of {small_n} ({pct(small_in, small_n)}) were done within {sl} days"
                           + (f"; {small_unknown} too recent to tell." if small_unknown else "."))
    block = "\n".join(block_lines)
    lines = ["# The back-check: the forecast from week 8 against what happened", "",
             "Made by `scripts/back_check.py` from `sample/history.json`, with the forecast's own code (`planner.simulate`, `plan_week`, "
             "`forecast.forecast_rows`). Every ticket is made up: the figures show direction, not size.", "", block, "",
             "## Each item open at the end of week 8", "",
             "| Item | Lane | 50% | 85% | 95% | Done | Verdict (85%) |", "|---|---|---|---|---|---|---|"]
    for it, p50, p85, p95, done, verdict in sorted(detail, key=lambda x: (P.LANES.index(x[0].lane), x[2] or date.max, x[0].request_id)):
        dates = "| | |" if it.lane == "small" else f"| {F.d(p50)} | {F.d(p85)} | {F.d(p95)} |"
        lines.append(f"| {it.request_id} {it.title} | {P.LANE_WORDS[it.lane]} {dates} {F.d(done) if done else 'still open'} | {verdict} |")
    lines += ["", f"Items a person closed or merged after week {FROM_WEEK}, left out: {', '.join(sorted(person_later)) or 'none'}.", "",
              "## Each lane in the forecast", ""] + [f"- **{P.LANE_WORDS[ln['lane']]}**: {ln['note']}" for ln in lanes] + [""]
    return "\n".join(lines), block


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    try:
        report, block = build()
        text = README.read_text(encoding="utf-8")
        if START not in text or END not in text:
            raise LookupError("README.md has no back-check markers")
        a, rest = text.split(START, 1)
        _, b = rest.split(END, 1)
        readme = f"{a}{START}\n{block}\n{END}{b}"
    except (LookupError, OSError, ValueError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    if args.check:
        stale = [p.name for p, t in ((REPORT, report), (README, readme)) if not p.exists() or p.read_text(encoding="utf-8") != t]
        print("The back-check's report and README lines are what the script makes." if not stale else f"OUT OF DATE {', '.join(stale)}: run python scripts/back_check.py")
        return 1 if stale else 0
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    README.write_text(readme, encoding="utf-8")
    print(block)
    print(f"\nWrote {REPORT.relative_to(REPO)} and the lines in README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
