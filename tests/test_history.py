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
