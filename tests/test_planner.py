"""The planner (scripts/planner.py), stages 3 and 4: the week's plan against a hand check (R12), the settings driving it
(R14), one piece of code for the plan, the forecast and the rule test (R13), the forecast's three kinds and its tail
(R18, R19), and the update trigger (R20). No database and no network: these run in CI."""
import json
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import back_check  # noqa: E402
import forecast as F  # noqa: E402
import planner as P  # noqa: E402
import rule_test  # noqa: E402

SETTINGS = {s["key"]: s["value"] for s in json.loads((REPO / "settings" / "settings.json").read_text(encoding="utf-8"))["settings"]}
PS = P.PlanSettings.from_settings(SETTINGS, 7)
WEEK = date(2026, 12, 7)  # a Monday


def item(rid, lane, hours, arrived, score=5.0, value=5, due=None, do_next=False):
    return P.Item(rid, lane, hours, hours, datetime.combine(date.fromisoformat(arrived), time(12), timezone.utc), score, value,
                  date.fromisoformat(due) if due else None, do_next)


def sample_week():
    """The hand-checked week (the arithmetic is in the test below and in docs/stage-notes.md)."""
    return [
        item("U1", "urgent", 6, "2026-12-06"),
        item("F1", "fixed_date", 8, "2026-11-20", due="2026-12-11"),   # latest safe start 04/12: this week or earlier
        item("F2", "fixed_date", 5, "2026-11-25", due="2026-12-21"),   # latest safe start 14/12: next week
        item("S1", "small", 2, "2026-11-02"), item("S2", "small", 1.5, "2026-11-20"), item("S3", "small", 2, "2026-12-01"),
        item("S4", "small", 2, "2026-12-02"), item("S5", "small", 1, "2026-12-03"),
        item("A", "standard", 10, "2026-09-07", score=5.0),            # 13 weeks waited: 5.0 + 3.25 = 8.25
        item("B", "standard", 6, "2026-12-01", score=7.5),             # 0 weeks: 7.5
        item("C", "standard", 4, "2026-10-26", score=6.0),             # 6 weeks: 6.0 + 1.5 = 7.5, older than B
        item("D", "standard", 12, "2026-11-30", score=4.0, do_next=True),  # do it next comes first
    ]


def test_r12_the_weeks_plan_matches_a_hand_check():
    """40 hours. 1. Urgent U1 takes 6 (2 beyond the 4-hour buffer): 34 left. 2. F1 is past its latest safe start
    (11/12 less 7 days = 04/12): 8, so 26 left; F2's is 14/12, next week. 3. Small, min(26, 8) = 8, oldest first:
    S1 2, S2 1.5, S3 2, S4 2, S5 0.5 of its 1: 18 left. 4. Standard, min(18, 28) = 18: D first (do it next) 12, then
    A (8.25 points) 6 of its 10: 0 left. 5. Nothing flows. C (7.5) and B (7.5) wait; F2 waits for next week."""
    plan = P.plan_week(sample_week(), WEEK, PS)
    assert [(r["request_id"], r["hours"], r["position"]) for r in plan.rows()] == [
        ("U1", 6, 1), ("F1", 8, 2), ("S1", 2, 3), ("S2", 1.5, 4), ("S3", 2, 5), ("S4", 2, 6), ("S5", 0.5, 7), ("D", 12, 8), ("A", 6, 9)]
    assert plan.used == 40 and plan.urgent_beyond_buffer == 2
    assert [round(s.used, 1) for s in plan.steps] == [6, 8, 8, 18, 0]
    assert "latest safe start 04/12/2026" in plan.rows()[1]["why"] and "8.25 rank points" in plan.rows()[8]["why"]


def test_r14_a_setting_changes_the_next_plan_with_no_code_change():
    """The same week with small_share 0.10: small gets 4 (S1 2, S2 1.5, S3 0.5), and standard min(22, 28) = 22: D 12, A 10."""
    ps = P.PlanSettings.from_settings(dict(SETTINGS, small_share=0.10), 7)
    rows = {r["request_id"]: r["hours"] for r in P.plan_week(sample_week(), WEEK, ps).rows()}
    assert rows == {"U1": 6, "F1": 8, "S1": 2, "S2": 1.5, "S3": 0.5, "D": 12, "A": 10}
    more = P.PlanSettings.from_settings(dict(SETTINGS, hours_per_week=60), 7)
    roomy = P.plan_week(sample_week(), WEEK, more)
    assert roomy.used == 59.5 and len(roomy.rows()) == 12   # 60 hours: every item in full, half an hour to spare


def test_r12_unused_hours_flow_to_the_other_lanes():
    """No standard work: the small lane's share is 8, and the 32 hours nobody else needs flow to small, then to the
    fixed-date item ahead of its latest safe start."""
    items = [item(f"S{n}", "small", 2, "2026-11-0%d" % (n % 9 + 1)) for n in range(1, 11)] + [item("F2", "fixed_date", 5, "2026-11-25", due="2026-12-21")]
    plan = P.plan_week(items, WEEK, PS)
    by = {r["request_id"]: r for r in plan.rows()}
    assert sum(r["hours"] for r in plan.rows() if r["lane"] == "small") == 20 and by["F2"]["hours"] == 5
    assert "unused hours flow" in by["F2"]["why"] and plan.steps[2].used == 8


def test_r12_urgent_takes_more_than_its_buffer_and_says_so():
    plan = P.plan_week([item("U1", "urgent", 30, "2026-12-06"), item("S1", "small", 2, "2026-11-02")], WEEK, PS)
    assert plan.urgent_beyond_buffer == 26 and "26 hours beyond the 4-hour buffer" in plan.steps[0].note
    assert {r["request_id"]: r["hours"] for r in plan.rows()} == {"U1": 30, "S1": 2}


def test_the_standard_order_is_do_next_then_score_plus_age_then_the_oldest():
    order = [i.request_id for i in P.standard_order([i for i in sample_week() if i.lane == "standard"], WEEK, 0.25)]
    assert order == ["D", "A", "C", "B"]
    assert [i.request_id for i in P.standard_order([i for i in sample_week() if i.lane == "standard"], WEEK, 0.0)] == ["D", "B", "C", "A"]


def test_nearest_rank_and_the_latest_safe_start():
    assert P.nearest_rank([7, 7, 14, 7], 0.85) == 14 and P.nearest_rank([7, 7, 7, 7, 7, 7, 14], 0.85) == 7
    assert P.nearest_rank([date(2026, 1, 1), None, None], 0.5) is None
    assert P.safe_start_days([], 0.85) == 7 and P.safe_start_days([7, 14, 21], 0.85) == 21
    assert P.work_spans([{"request_id": "x", "week_start": "2026-09-07"}, {"request_id": "x", "week_start": "2026-09-14"}], {"x"}) == [14]


# ---------------------------------------------------------------- R13: one piece of code

def history():
    doc = json.loads((REPO / "sample" / "history.json").read_text(encoding="utf-8"))
    items, ends = P.history_items(doc, SETTINGS["score_weights"])
    return doc, items, ends


def test_r13_the_old_rule_through_the_planner_gives_back_the_historys_own_work_log():
    """The history was made by working highest score first (scripts/make_history.py). plan_week() with that rule, week by
    week, gives back every hour of the work log and the same items done: the rule test runs the code the plan runs."""
    doc, items, ends = history()
    ps = P.PlanSettings.from_settings(SETTINGS, P.history_safe_start_days(doc, 0.85))
    rp = P.replay(items, ends, date.fromisoformat(doc["week_one"]), doc["weeks"], ps, "highest score first")
    assert {k: round(v, 1) for k, v in rp.worked.items()} == {(w["request_id"], date.fromisoformat(w["week_start"])): w["hours"] for w in doc["work_log"]}
    assert {i.request_id for i in rp.items.values() if i.done_on} == {h["request_id"] for h in doc["status_history"] if h["to_status"] == "Done"}


def test_r13_the_plan_the_forecast_the_rule_test_and_the_back_check_all_use_plan_week():
    defs = [p.name for p in (REPO / "scripts").glob("*.py") if re.search(r"^def plan_week\(", p.read_text(encoding="utf-8"), re.M)]
    assert defs == ["planner.py"]
    for name, call in (("plan_week.py", "P.plan_week("), ("forecast.py", "P.simulate("), ("back_check.py", "P.simulate("),
                       ("rule_test.py", "P.replay(")):
        assert call in (REPO / "scripts" / name).read_text(encoding="utf-8"), name
    src = (REPO / "scripts" / "planner.py").read_text(encoding="utf-8")
    assert "plan = plan_week(active, ws, ps, rule)" in src and "plan = plan_week(avail, ws, ps, rule)" in src
    # No other script reads a share or the age rate to plan with.
    for p in (REPO / "scripts").glob("*.py"):
        if p.name not in ("planner.py", "plan_week.py", "make_history.py"):
            assert "small_share *" not in p.read_text(encoding="utf-8") and "age_points_per_week *" not in p.read_text(encoding="utf-8"), p.name


def test_r26_the_rule_test_report_and_readme_table_are_up_to_date():
    assert rule_test.main(["--check"]) == 0


def test_r26_the_lanes_rule_meets_every_fixed_date_that_fell_due_on_every_seed():
    report, _, same = rule_test.build()
    assert same
    lanes = [line for line in report.splitlines() if re.match(r"\| 1[67]\d \| \d+ \| lanes \|", line)]
    assert len(lanes) == 10 and all(" 100% |" in line or "none fell due" in line for line in lanes)


def test_r21_the_back_check_is_up_to_date():
    assert back_check.main(["--check"]) == 0


# ---------------------------------------------------------------- the forecast (R18, R19) and the trigger (R20)

def hist_of(arrivals):
    return {lane: [[a for a in arrivals if a.lane == lane]] * 4 for lane in P.LANES}


def test_r18_every_open_item_gets_a_range_a_service_level_or_a_chance():
    items = sample_week()
    arrivals = [P.Arrival("standard", 8, 5.0, 5, 1, None), P.Arrival("small", 1, 5.0, 3, 2, None), P.Arrival("fixed_date", 4, 5.0, 5, 0, 21)]
    sim = P.simulate(items, hist_of(arrivals), PS, WEEK, "lanes", 60, 12, 163)
    rows, lanes = F.forecast_rows(sim, items, [{"request_id": "W1", "lane": "standard", "lane_waits": True}], PS, [0.5, 0.85, 0.95])
    kinds = {r["request_id"]: r["kind"] for r in rows}
    assert {kinds[i.request_id] for i in items if i.lane in ("urgent", "standard")} == {"date_range"}
    assert {kinds[i.request_id] for i in items if i.lane == "small"} == {"service_level"}
    assert {kinds[i.request_id] for i in items if i.lane == "fixed_date"} == {"chance_of_date"}
    by = {r["request_id"]: r for r in rows}
    assert by["A"]["p50"] <= by["A"]["p85"] <= by["A"]["p95"] and by["S1"]["service_level_days"] is not None
    assert by["F1"]["latest_safe_start"] == date(2026, 12, 4) and 0 <= by["F1"]["chance"] <= 1
    assert "Waits for a person" in by["W1"]["note"] and by["W1"]["p85"] is None
    assert {ln["lane"] for ln in lanes} == set(P.LANES)


def test_r18_a_fixed_seed_gives_the_same_forecast():
    items = sample_week()
    weeks = {lane: [] for lane in P.LANES}
    weeks["standard"] = [[], [P.Arrival("standard", 12, 9.0, 8, 0, None)] * 3, [P.Arrival("standard", 4, 3.0, 3, 2, None)]]
    weeks["urgent"] = [[], [], [P.Arrival("urgent", 10, 10.0, 10, 1, None)]]
    a, b, c = (P.simulate(items, weeks, PS, WEEK, "lanes", 40, 10, seed) for seed in (163, 163, 164))
    assert a.finish == b.finish and a.finish != c.finish


def test_r19_a_lane_that_takes_in_more_than_it_puts_out_gives_no_date_for_its_tail_and_says_so():
    """Heavy demand: 60 hours of new standard work a week, scored above the old items, and no points for waiting. The old
    low-scored items never finish: no 85% date, and the output says the lane grows."""
    ps = P.PlanSettings.from_settings(dict(SETTINGS, age_points_per_week=0), 7)
    items = [item(f"OLD{n}", "standard", 8, "2026-10-01", score=3.0) for n in range(4)]
    heavy = [P.Arrival("standard", 10, 8.0, 8, 0, None)] * 6
    sim = P.simulate(items, hist_of(heavy), ps, WEEK, "lanes", 30, 12, 163, arrivals_from=0)
    rows, lanes = F.forecast_rows(sim, items, [], ps, [0.5, 0.85, 0.95])
    std = next(ln for ln in lanes if ln["lane"] == "standard")
    assert std["growing"] and std["hours_in_per_week"] > std["hours_out_per_week"]
    assert all(r["p85"] is None for r in rows) and "no finish date is given for the tail" in rows[0]["note"]
    assert "get no 85% date (the tail)" in std["note"]


def frow(rid, p85, kind="date_range"):
    return {"request_id": rid, "kind": kind, "p85": p85}


def test_r20_a_small_change_drafts_nothing_and_a_large_one_drafts_an_update():
    d = date(2026, 12, 10)
    prev = {"X": d, "Y": d, "Z": d, "N": None, "G": d}
    rows = [frow("X", d + timedelta(days=7)),    # moved exactly a week: not more than a week
            frow("Y", d + timedelta(days=8)),    # more than a week: an update
            frow("Z", d - timedelta(days=10)),   # earlier by more than a week: an update
            frow("N", d),                        # gained a date: an update
            frow("G", None),                     # lost its date (the tail): an update
            frow("S", None, "service_level"),    # no dates for small items
            frow("NEW", d)]                      # nothing to compare with
    assert [r["request_id"] for r, _ in F.triggers(prev, rows, 7)] == ["Y", "Z", "N", "G"]
    assert F.triggers({}, rows, 7) == []


def test_r20_the_update_draft_is_plain_and_names_the_request(drafter_eng):
    info = {"requester_role": "Sales manager", "title": "Route new Leads by region"}
    moved = F.update_draft(frow("CD-0010", date(2026, 12, 18)), date(2026, 12, 4), info, "fc-1", "2026-11-25T01:00:00Z", 7)
    lost = F.update_draft(frow("CD-0010", None), date(2026, 12, 4), info, "fc-1", "2026-11-25T01:00:00Z", 7)
    assert "18 December 2026" in moved["body"] and "04 December 2026" in moved["body"] and moved["drafted_by"].endswith("(template, no AI)")
    assert "cannot give a date" in lost["body"] and moved["stamp"].startswith("changedesk U-fc-1-CD-0010 | no AI")
    for u in (moved, lost):
        assert drafter_eng.call("draftProblems", {"request_id": "CD-0010"}, {"subject": u["subject"], "body": u["body"]}) == []


# ---------------------------------------------------------------- R17: the lane growth flag

def lh(lane, week, arrived, finished):
    return {"lane": lane, "week_start": week, "arrived": arrived, "finished": finished}


def test_r17_the_lane_growth_flag_fires_on_three_weeks_running():
    import health_report as H

    rows = [lh("standard", "2026-11-02", 5, 3), lh("standard", "2026-11-09", 4, 2), lh("standard", "2026-11-16", 6, 1),
            lh("standard", "2026-11-23", 0, 9),                    # this week is not complete on 25/11: left out
            lh("small", "2026-11-02", 2, 5), lh("small", "2026-11-09", 6, 2), lh("small", "2026-11-16", 6, 2),   # two weeks: no
            lh("urgent", "2026-11-02", 3, 1), lh("urgent", "2026-11-09", 1, 1), lh("urgent", "2026-11-16", 3, 1),  # broken run
            lh("fixed_date", "2026-11-16", 0, 0)]
    flags = H.growth_flags(rows, 3, date(2026, 11, 25))
    assert flags["standard"]["flagged"] and flags["standard"]["run"] == 3
    assert not flags["small"]["flagged"] and flags["small"]["run"] == 2
    assert not flags["urgent"]["flagged"] and flags["urgent"]["run"] == 1
    assert not H.growth_flags(rows, 4, date(2026, 11, 25))["standard"]["flagged"]   # the setting decides
    text = H.ask_text("standard", flags["standard"], 3)
    assert "change the split" in text and "add hours" in text and "say no" in text
