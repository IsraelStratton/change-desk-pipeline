"""The settings (the spec's settings) and the labelled eval set: starting values as the spec gives them, and labels the
playbook can grade."""
import json

import pytest
from conftest import REPO, SETTINGS

SECTION_7 = {
    "hours_per_week": 40, "urgent_buffer_share": 0.10, "small_share": 0.20, "standard_share": 0.70, "small_lane_max_hours": 2,
    "age_points_per_week": 0.25, "age_limit_days_small": 30, "age_limit_days_standard": 90, "latest_safe_start_percentile": 0.85,
    "lane_growth_weeks": 3, "update_trigger_days": 7, "forecast_levels": [0.50, 0.85, 0.95],
    "score_weights": {"value": 0.30, "effort": 0.20, "risk": 0.20, "goal_fit": 0.20, "readiness": 0.10},
}


def test_every_setting_in_kb_139_section_7_has_its_starting_value():
    for k, v in SECTION_7.items():
        assert SETTINGS[k] == v, k


def test_the_shares_add_up_to_the_week():
    assert round(SETTINGS["urgent_buffer_share"] + SETTINGS["small_share"] + SETTINGS["standard_share"], 9) == 1.0


def test_build_additions_are_marked_as_such():
    rows = json.loads((REPO / "settings" / "settings.json").read_text(encoding="utf-8"))["settings"]
    extra = {r["key"]: r["source"] for r in rows if r["key"] not in SECTION_7}
    assert set(extra) == {"large_item_hours", "effort_points_by_size", "forecast_runs", "forecast_horizon_weeks", "forecast_seed"}
    assert all(s.startswith("build addition") for s in extra.values())


def test_the_store_holds_the_settings_with_who_and_when(db):
    import desk_db

    rows = {r["key"]: r for r in desk_db.rows(db, "select * from changedesk.settings")}
    assert set(rows) == set(SETTINGS)
    assert all(r["changed_by"] and r["changed_at"] and r["why"] for r in rows.values())
    hist = db.execute("select count(*) as n from changedesk.settings_history").fetchone()["n"]
    assert hist >= len(SETTINGS)


CASES = json.loads((REPO / "skills" / "triage-playbook" / "eval" / "cases.json").read_text(encoding="utf-8"))


def test_the_eval_set_has_forty_cases_eight_hostile():
    cases = CASES["cases"]
    assert len(cases) == 40 and len({c["case_id"] for c in cases}) == 40
    assert sum(c["label"]["hostile"] for c in cases) == 8


def test_every_label_uses_the_playbooks_codes(pb):
    for c in CASES["cases"]:
        lab = c["label"]
        assert set(lab["lane"].split("|")) <= set(pb["lanes"]), c["case_id"]
        assert lab["size_band"] is None or set(lab["size_band"].split("|")) <= {"small", "medium", "large"}, c["case_id"]
        assert lab["playbooks"] and set(lab["playbooks"]) <= set(pb["playbooks"]), c["case_id"]
        if lab["hostile"]:
            assert lab["needs_person"] is True, c["case_id"]
        if lab["lane"] in ("urgent", "fixed_date"):
            assert lab["needs_person"] is True, c["case_id"]


@pytest.mark.parametrize("case", [c for c in CASES["cases"] if c["label"]["hostile"]], ids=lambda c: c["case_id"])
def test_r3_the_code_screen_alone_catches_every_hostile_case(triage_eng, pb, case):
    """The model is told to flag the same things; either is enough to hold the request for a person (the eval counts both)."""
    s = triage_eng.call("screenRequest", pb, case)
    assert "possible_injection" in s["flags"], s["hits"]


def test_no_normal_eval_case_trips_the_code_screen(triage_eng, pb):
    tripped = [c["case_id"] for c in CASES["cases"] if not c["label"]["hostile"]
               and "possible_injection" in triage_eng.call("screenRequest", pb, c)["flags"]]
    assert tripped == []
