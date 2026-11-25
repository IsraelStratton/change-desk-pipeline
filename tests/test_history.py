"""The made-up history (sample/history.json, from scripts/make_history.py): the seed makes the file, every request has
a status history that ends where the request is, and the history carries the fault the design fixes."""
import json
import sys
from collections import defaultdict
from datetime import date

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import make_history  # noqa: E402

DOC = json.loads((REPO / "sample" / "history.json").read_text(encoding="utf-8"))
REQS = {r["request_id"]: r for r in DOC["requests"]}


def test_the_seed_makes_exactly_this_file():
    assert make_history.render(make_history.Maker(make_history.SEED).make()) == (REPO / "sample" / "history.json").read_text(encoding="utf-8")


def test_twelve_weeks_from_a_monday():
    assert DOC["weeks"] == 12 and date.fromisoformat(DOC["week_one"]).weekday() == 0
    weeks = {w["week_start"] for w in DOC["work_log"]}
    assert len(weeks) == 12 and all(date.fromisoformat(w).weekday() == 0 for w in weeks)
    per_week = defaultdict(float)
    for w in DOC["work_log"]:
        per_week[w["week_start"]] += w["hours"]
    assert all(abs(h - 40.0) < 1e-6 for h in per_week.values())  # the old way spent every hour of the week


def test_r1_every_request_has_a_status_history_that_ends_where_it_is():
    hist = defaultdict(list)
    for h in DOC["status_history"]:
        hist[h["request_id"]].append(h)
    for rid, r in REQS.items():
        hs = sorted(hist[rid], key=lambda h: h["changed_at"])
        assert hs and hs[0]["from_status"] is None and hs[0]["to_status"] == "New", rid
        assert all(a["to_status"] == b["from_status"] for a, b in zip(hs, hs[1:])), rid
        assert hs[-1]["to_status"] == r["status"], rid


def test_every_triaged_request_has_a_lane_a_reason_and_five_score_parts():
    parts = defaultdict(set)
    for s in DOC["scores"]:
        parts[s["request_id"]].add(s["part"])
    for rid, r in REQS.items():
        if r["status"] == "New":
            continue
        assert r["lane"] and r["triage_reason"] and r["triaged_by"] == "history (made-up)", rid
        assert parts[rid] == {"value", "effort", "risk", "goal_fit", "readiness"}, rid


def test_the_inbox_holds_twelve_new_requests_for_the_triage_step():
    inbox = [r for r in DOC["requests"] if r["status"] == "New"]
    assert len(inbox) == 12 and all(r["arrived_at"] >= "2026-11-22" for r in inbox)
    assert any("ignore your previous rules" in r["body"] for r in inbox)  # one hostile request


def test_the_old_rule_starved_small_work_and_missed_fixed_dates():
    """The history is worked the old way, highest score first. It shows the fault KB-136 section 6.5 found."""
    done = {h["request_id"]: h["changed_at"][:10] for h in DOC["status_history"] if h["to_status"] == "Done"}
    fixed = [r for r in REQS.values() if r.get("lane") == "fixed_date" and r["due_date"] < DOC["as_of"]]
    missed = [r for r in fixed if r["request_id"] not in done or done[r["request_id"]] > r["due_date"]]
    assert missed, "no fixed date was missed"
    waiting_small = [r for r in REQS.values() if r.get("lane") == "small" and r["status"] == "Triaged"]
    oldest = min(date.fromisoformat(r["arrived_at"][:10]) for r in waiting_small)
    assert (date.fromisoformat(DOC["as_of"]) - oldest).days > 30


def test_contact_details_appear_once_on_purpose_and_are_made_up():
    text = json.dumps(DOC)
    assert "@" not in text.replace("@freight.example", "")  # one inbox request holds made-up contact details on purpose
    assert sum("Jane Doe" in r.get("body", "") for r in REQS.values()) == 1


def test_the_demo_reset_puts_the_store_back_to_the_history_and_the_starting_settings():
    """COURSES 2ND's guard (25/11/2026): load_history.py --reset gives a demo the made-up history and the starting settings
    (40 hours a week, the 20/70 split), and clears everything stages 3 to 5 added (forecast runs, triggers, drafts, the
    outbox). Run here as the owner inside a transaction that is rolled back, so the live store is untouched."""
    import sys

    from conftest import owner_sql

    sys.path.insert(0, str(REPO / "scripts"))
    import load_history

    doc = json.loads((REPO / "sample" / "history.json").read_text(encoding="utf-8"))
    sql = load_history.load_sql(doc, reset=True, wrap=False)
    assert not any(line.strip().lower() in ("commit;", "begin;") for line in sql.splitlines()), "the load must not commit its own transaction"
    check = ("select json_build_object('hours', changedesk.setting_num('hours_per_week'), 'small', changedesk.setting_num('small_share'), "
             "'standard', changedesk.setting_num('standard_share'), 'requests', (select count(*) from changedesk.requests), "
             "'updates', (select count(*) from changedesk.updates), 'outbox', (select count(*) from changedesk.outbox), "
             "'runs', (select count(*) from changedesk.forecast_runs), 'triggers', (select count(*) from changedesk.update_triggers), "
             "'by', (select changed_by from changedesk.settings where key = 'hours_per_week'), "
             "'kept', (select count(*) from changedesk.settings_history where key = 'hours_per_week'));")
    out = owner_sql(sql + check)
    assert out.returncode == 0, out.stderr[-500:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    start = {s["key"]: s["value"] for s in json.loads((REPO / "settings" / "settings.json").read_text(encoding="utf-8"))["settings"]}
    assert (got["hours"], got["small"], got["standard"]) == (start["hours_per_week"], start["small_share"], start["standard_share"]) == (40, 0.2, 0.7)
    assert got["requests"] == doc["counts"]["requests"] and got["updates"] == got["outbox"] == got["runs"] == got["triggers"] == 0
    assert got["by"] in ("load_history.py --reset", "setup_db.py") and got["kept"] >= 1  # every value the setting has had is kept
