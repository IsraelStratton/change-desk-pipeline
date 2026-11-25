"""Stages 3 and 4 against the local store, as the app's own login, inside a transaction that is rolled back: the planner
agrees with the store's ranking (R11, R13), the plan is saved only through its checked function (R5, R12), a setting
change changes the next plan (R14), the health figures (R15), the forecast gives every open item one of three (R18),
the update trigger (R20), and the tracker view (stage 3). Skipped where there is no local store (CI)."""
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from conftest import j

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import desk_db  # noqa: E402
import desk_state  # noqa: E402
import forecast as F  # noqa: E402
import planner as P  # noqa: E402

NOW = "2026-11-25T01:00:00Z"
WEEK = date(2026, 11, 23)


def stamp(pid):
    return f"changedesk {pid} | no AI | planner@test | made by test | {NOW}"


def save(db, plan, pid="plan-test", week=WEEK):
    return db.execute("select changedesk.save_plan(%s::jsonb) as n", (j({"plan_id": pid, "week_start": week.isoformat(), "made_by": "test",
                                                                         "made_at": NOW, "stamp": stamp(pid), "rows": plan}),)).fetchone()["n"]


@pytest.mark.parametrize("as_of", ["2026-11-23", "2026-12-07", "2027-02-01"])
def test_r13_the_planners_standard_order_is_the_stores_ranking(db, as_of):
    day = date.fromisoformat(as_of)
    st = desk_state.load(db)
    store = [r["request_id"] for r in desk_db.rows(db, "select request_id from changedesk.ranked_standard(%s) order by rank", (day,))]
    mine = [i.request_id for i in P.standard_order([i for i in st.items if i.lane == "standard" and i.arrived <= day], day, 0.25)]
    assert store and mine == [r for r in store if r in set(mine)] and set(mine) <= set(store)


def test_r12_the_plan_is_saved_and_its_items_are_planned(db):
    st = desk_state.load(db)
    plan = P.plan_week(st.items, WEEK, st.plan_settings())
    rows = plan.rows()
    ids = [r["request_id"] for r in rows]
    before = {r["request_id"]: r["status"] for r in desk_db.rows(db, "select request_id, status from changedesk.requests where request_id = any(%s)", (ids,))}
    # Make one item Triaged first (the week's real plan may have planned them all already), so the move to Planned shows.
    db.execute("select changedesk.save_plan(%s::jsonb)", (j({"plan_id": "plan-test-0", "week_start": WEEK.isoformat(), "made_by": "test", "made_at": NOW,
                                                             "stamp": stamp("plan-test-0"), "rows": [dict(rows[-1], position=1)]}),))
    assert save(db, rows) == len(rows) and sum(r["hours"] for r in rows) <= 40
    status = {r["request_id"]: r["status"] for r in desk_db.rows(db, "select request_id, status from changedesk.requests where request_id = any(%s)", (ids,))}
    assert set(status.values()) <= {"Planned", "In progress"}
    moved = next(r for r in ids[:-1] if before[r] != "In progress")
    h = desk_db.rows(db, "select to_status, changed_by, note from changedesk.status_history where request_id = %s order by changed_at desc, id desc limit 1",
                     (moved,))[0]
    assert h["to_status"] == "Planned" and h["changed_by"] == "test" and "plan-test" in h["note"]
    # A new plan that leaves an item out puts it back to Triaged, with its history.
    assert save(db, [dict(r, position=n) for n, r in enumerate(rows[1:], 1)], "plan-test-2") == len(rows) - 1
    assert desk_db.rows(db, "select status from changedesk.requests where request_id = %s", (rows[0]["request_id"],))[0]["status"] == (
        "In progress" if before[rows[0]["request_id"]] == "In progress" else "Triaged")
    db.execute("set constraints all immediate")


@pytest.mark.parametrize("bad,match", [
    (lambda r: [dict(r[0], hours=r[0]["hours"] + 50)], "hours left"),
    (lambda r: [dict(r[0], lane="small" if r[0]["lane"] != "small" else "standard")], "is in lane"),
    (lambda r: [dict(r[0], position=2)], "positions"),
])
def test_r12_save_plan_refuses_a_row_that_breaks_the_rules(db, bad, match):
    st = desk_state.load(db)
    rows = P.plan_week(st.items, WEEK, st.plan_settings()).rows()
    with pytest.raises(Exception, match=match):
        save(db, bad(rows))


def test_r12_save_plan_refuses_a_week_that_is_not_a_monday_or_more_hours_than_the_week(db):
    st = desk_state.load(db)
    rows = P.plan_week(st.items, WEEK, st.plan_settings()).rows()
    with pytest.raises(Exception, match="Monday"):
        save(db, rows, week=WEEK + timedelta(days=1))
    db.rollback()
    db.execute("select changedesk.set_setting('hours_per_week', '20'::jsonb, 'test', 'R12 test, rolled back')")
    with pytest.raises(Exception, match="more than the week"):
        save(db, rows)


def test_r5_an_item_that_waits_for_a_person_is_never_planned(db):
    """The planner leaves it out (desk_state), and if a row names it anyway the store refuses it."""
    rid = db.execute("select changedesk.add_request(%s::jsonb) as id", (j({"requester_role": "Sales manager", "title": "Renewal report before the board meeting",
                                                                             "body": "Made up."}),)).fetchone()["id"]
    from conftest import GOALS, PLAYBOOK, SETTINGS, answer, fake_claude
    from desk_engine import Engine

    eng = Engine("triage")
    pb = eng.call("parseTriagePlaybook", PLAYBOOK.read_text(encoding="utf-8"))
    req = desk_db.rows(db, "select * from changedesk.inbox where request_id = %s", (rid,))[0]
    settings = eng.call("settingsFromRows", [{"key": k, "value": v} for k, v in SETTINGS.items()])
    out = eng.call("checkTriage", pb, req, fake_claude(answer(lane="fixed_date", due_date="2026-12-04", what_breaks="The board pack goes out without it.",
                                                              size_hours=6, playbook="crm-report-build")),
                   {"run_id": "t", "source": "python", "model": "m", "settings": settings, "goals": GOALS, "now": NOW, "latency_ms": 1})
    db.execute("select changedesk.log_triage(%s::jsonb, %s::jsonb, '[]'::jsonb)", (j([out["call"]]), j([out["proposal"]])))
    st = desk_state.load(db)
    assert rid in {w["request_id"] for w in st.waiting} and rid not in {i.request_id for i in st.items}
    with pytest.raises(Exception, match="waits for a lane confirmation"):
        save(db, [{"request_id": rid, "lane": "fixed_date", "hours": 6, "position": 1, "why": "test"}])


def test_r14_changing_a_setting_in_the_table_changes_the_next_plan(db):
    def small_hours():
        st = desk_state.load(db)
        return sum(s.hours for s in P.plan_week(st.items, WEEK, st.plan_settings()).segments if s.step == "small")
    # The share as the store holds it: 0.20 at the start, 0.225 since Israel's decision of 25/11/2026 (9 hours of 40).
    share = float(db.execute("select changedesk.setting_num('small_share') as s").fetchone()["s"])
    week = float(db.execute("select changedesk.setting_num('hours_per_week') as h").fetchone()["h"])
    before = small_hours()
    db.execute("select changedesk.set_setting('small_share', %s::jsonb, 'desk-lead (test)', 'R14 test, rolled back')", (j(share / 2),))
    after = small_hours()
    assert abs(before - week * share) < 0.06 and abs(after - week * share / 2) < 0.06, (before, after, week, share)
    who = desk_db.rows(db, "select changed_by, why from changedesk.settings_history where key = 'small_share' order by id desc limit 1")[0]
    assert who == {"changed_by": "desk-lead (test)", "why": "R14 test, rolled back"}


def test_r15_the_health_figures_match_a_count_from_the_rows(db):
    """One lane-week of changedesk.lane_health, counted again from requests and status history."""
    week = date(2026, 11, 9)
    got = desk_db.rows(db, "select * from changedesk.lane_health where lane = 'small' and week_start = %s", (week,))[0]
    ends = desk_db.rows(db, "select request_id, arrived_at::date as a, ended_at::date as e from changedesk.request_ends where lane = 'small'")
    end = week + timedelta(days=7)
    a = lambda r: date.fromisoformat(r["a"])  # noqa: E731
    e = lambda r: date.fromisoformat(r["e"]) if r["e"] else None  # noqa: E731
    assert got["arrived"] == sum(week <= a(r) < end for r in ends)
    assert got["finished"] == sum(e(r) is not None and week <= e(r) < end for r in ends)
    assert got["open_at_end"] == sum(a(r) < end and (e(r) is None or e(r) >= end) for r in ends)


def run(db, runs=120):
    st, ps, sim, rows, lanes, n = F.run_forecast(db, WEEK, runs=runs)
    return st, ps, sim, rows, lanes


def log(db, rid, rows, lanes, drafts=(), purpose="forecast", made_at=NOW):
    run_ = {"run_id": rid, "purpose": purpose, "start_week": WEEK.isoformat(), "rule": "lanes", "runs": 120, "horizon_weeks": 26, "seed": 163,
            "load": 1.0, "safe_start_days": 7, "settings": {}, "made_by": "test", "made_at": made_at, "stamp": f"changedesk {rid} | test"}
    return db.execute("select changedesk.log_forecast(%s::jsonb, %s::jsonb, %s::jsonb) as n", (j(run_), j(rows + lanes), j(list(drafts)))).fetchone()["n"]


def test_r18_every_open_item_gets_a_range_a_service_level_or_a_chance(db):
    st, ps, sim, rows, lanes = run(db)
    log(db, "fc-test-1", rows, lanes)
    missing = db.execute("select count(*) as n from changedesk.requests r where r.status in ('Triaged','Planned','In progress') and r.lane is not null "
                         "and not exists (select 1 from changedesk.forecasts f where f.run_id = 'fc-test-1' and f.request_id = r.request_id)").fetchone()["n"]
    assert missing == 0
    kinds = {(r["lane"], r["kind"]) for r in desk_db.rows(db, "select lane, kind from changedesk.forecasts where run_id = 'fc-test-1' and request_id is not null")}
    assert kinds <= {("standard", "date_range"), ("urgent", "date_range"), ("small", "service_level"), ("fixed_date", "chance_of_date")}
    with pytest.raises(Exception, match="gives no forecast for"):
        log(db, "fc-test-2", rows[1:], lanes)


def triggers_of(run_id, prev_id, found):
    return [{"run_id": run_id, "previous_run_id": prev_id, "request_id": r["request_id"]} for r, _ in found]


def test_r20_a_small_change_triggers_nothing_and_a_large_one_triggers_updates(db):
    """R20, as stage 5 runs it: the trigger's rows are written by changedesk.log_updates, which works each one out again
    from the two runs' forecasts rows. The updates themselves are drafted behind them (tests/test_updates_db.py)."""
    st, ps, sim, rows, lanes = run(db)
    log(db, "fc-test-a", rows, lanes, made_at="2026-11-25T01:00:00Z")
    prev = {r["request_id"]: r["p85"] for r in rows if r["request_id"]}
    # A small change: one standard item's readiness goes up by one point.
    rid = next(r["request_id"] for r in rows if r["lane"] == "standard")
    db.execute("select changedesk.change_score(%s::jsonb)", (j([{"decision_id": "P-t", "run_id": "t", "request_id": rid, "part": "readiness",
                                                                "points": 10, "reason": "test", "decided_by": "desk-lead (test)", "decided_at": NOW,
                                                                "stamp": "changedesk P-t | test"}]),))
    _, _, _, rows2, _ = run(db)
    small = F.triggers(prev, rows2, 7)
    # A large change: the week halves.
    db.execute("select changedesk.set_setting('hours_per_week', '20'::jsonb, 'desk-lead (test)', 'R20 test, rolled back')")
    _, _, _, rows3, lanes3 = run(db)
    large = F.triggers(prev, rows3, 7)
    assert len(small) <= 1 and len(large) >= 10, (len(small), len(large))
    log(db, "fc-test-b", rows3, lanes3, made_at="2026-11-25T02:00:00Z")
    db.execute("select changedesk.log_updates('[]'::jsonb, %s::jsonb, '[]'::jsonb, '[]'::jsonb)", (j(triggers_of("fc-test-b", "fc-test-a", large)),))
    got = desk_db.rows(db, "select request_id, old_p85, new_p85, moved_days, why from changedesk.update_triggers where run_id = 'fc-test-b'")
    assert len(got) == len(large)
    assert all((g["why"] != "moved") or abs(g["moved_days"]) > 7 for g in got)
    # A trigger that did not happen is refused: an item whose 85% date stayed put.
    still = next(r for r in rows3 if r["request_id"] in prev and r["p85"] and prev[r["request_id"]] and r["p85"] == prev[r["request_id"]])
    with pytest.raises(Exception, match="triggers nothing"):
        db.execute("select changedesk.log_updates('[]'::jsonb, %s::jsonb, '[]'::jsonb, '[]'::jsonb)",
                   (j([{"run_id": "fc-test-b", "previous_run_id": "fc-test-a", "request_id": still["request_id"]}]),))


def test_r20_a_what_if_run_triggers_nothing(db):
    st, ps, sim, rows, lanes = run(db, 30)
    log(db, "fc-test-w0", rows, lanes, made_at="2026-11-25T01:00:00Z")
    log(db, "wi-test", rows, lanes, purpose="what-if", made_at="2026-11-25T02:00:00Z")
    rid = next(r["request_id"] for r in rows if r["request_id"] and r["p85"])
    with pytest.raises(Exception, match="compares a forecast run with an earlier forecast run"):
        db.execute("select changedesk.log_updates('[]'::jsonb, %s::jsonb, '[]'::jsonb, '[]'::jsonb)",
                   (j([{"run_id": "wi-test", "previous_run_id": "fc-test-w0", "request_id": rid}]),))


def test_r20_a_what_if_run_takes_no_draft_either(db):
    st, ps, sim, rows, lanes = run(db, 30)
    draft = {"update_id": "U-wi-t", "request_id": rows[0]["request_id"], "subject": "s", "body": "b", "drafted_by": "test",
             "drafted_at": NOW, "draft_problems": "", "stamp": "changedesk U-wi-t | test"}
    with pytest.raises(Exception, match="what-if run drafts no updates"):
        log(db, "wi-test", rows, lanes, [draft], purpose="what-if")


def test_the_tracker_view_has_one_row_for_every_request(db):
    n = db.execute("select count(*) as n from changedesk.requests").fetchone()["n"]
    rows = desk_db.rows(db, "select * from changedesk.tracker")
    assert len(rows) == n == len({r["request_id"] for r in rows})
    decide = {r["request_id"] for r in desk_db.rows(db, "select request_id from changedesk.decide_list")}
    assert {r["request_id"] for r in rows if r["past_age_limit"]} == decide
    assert all(r["rank_points"] is None for r in rows if r["lane"] != "standard")
    ranked = {r["request_id"]: r["rank_points"] for r in desk_db.rows(db, "select request_id, rank_points from changedesk.standard_ranked")}
    assert all(abs(float(r["rank_points"]) - float(ranked[r["request_id"]])) < 1e-9 for r in rows if r["request_id"] in ranked)
