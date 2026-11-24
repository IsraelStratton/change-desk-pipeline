"""The scoring engine (engine/scoring.js) and the message drafter (engine/drafter.js): the score with its working,
the effort rule, the score change form, the decide list form and the close message check. No network."""
import json

import pytest
from conftest import SETTINGS, fake_claude

WEIGHTS = SETTINGS["score_weights"]


def test_r9_the_score_is_the_weighted_parts_with_the_working_shown(scoring_eng):
    out = scoring_eng.call("scoreWithWorking", {"value": 8, "effort": 7, "risk": 9, "goal_fit": 8, "readiness": 6}, WEIGHTS)
    # The Decision Engine's own example (KB-136, INIT-163's score): 2.40 + 1.40 + 1.80 + 1.60 + 0.60 = 7.80.
    assert out["score"] == 7.8
    assert out["working"] == "value 8 x 0.3 = 2.40 + effort 7 x 0.2 = 1.40 + risk 9 x 0.2 = 1.80 + goal_fit 8 x 0.2 = 1.60 + readiness 6 x 0.1 = 0.60"
    with pytest.raises(Exception, match="whole number"):
        scoring_eng.call("scoreWithWorking", {"value": 0, "effort": 7, "risk": 9, "goal_fit": 8, "readiness": 6}, WEIGHTS)


def test_the_weights_add_up_to_one():
    assert round(sum(WEIGHTS.values()), 9) == 1.0


@pytest.mark.parametrize("hours,points", [(0.5, 10), (2, 10), (2.5, 8), (4, 8), (6, 6), (8, 6), (12, 4), (16, 4), (40, 2)])
def test_effort_points_follow_the_size_bands(scoring_eng, triage_eng, hours, points):
    assert scoring_eng.call("sizeEffortPoints", hours, SETTINGS) == points
    assert triage_eng.call("effortPoints", hours, SETTINGS["effort_points_by_size"]) == points


def test_r11_each_week_waited_adds_the_rate(scoring_eng):
    assert [scoring_eng.call("rankPoints", 4.5, w, 0.25) for w in (0, 1, 4, 10)] == [4.5, 4.75, 5.5, 7.0]


RANKED = [{"rank": 1, "request_id": "CD-0016", "title": "Clean up duplicate Order records", "score": 4.9, "weeks_waited": 17,
           "rank_points": 9.15, "do_next": False},
          {"rank": 2, "request_id": "CD-0020", "title": "Refresh the test sandbox", "score": 4.3, "weeks_waited": 14,
           "rank_points": 7.8, "do_next": False}]
WORKING = [{"request_id": r, "part": p, "points": 5, "reason": "A reason.", "set_by": "history (made-up)", "is_change": False, "previous_points": None}
           for r in ("CD-0016", "CD-0020") for p in ("value", "effort", "risk", "goal_fit", "readiness")]


def test_r10_the_score_form_shows_the_working_and_asks_for_one_change(scoring_eng):
    fields = scoring_eng.call("buildScoreForm", RANKED, WORKING, {"run_id": "n8n-5"})
    assert [f.get("fieldName") for f in fields] == [None, "decided_by", "item", "part", "points", "reason"]
    assert "rank points" in fields[0]["html"].lower() and "CD-0016" in fields[0]["html"]
    assert [o["option"] for o in fields[2]["fieldOptions"]["values"]] == ["CD-0016 Clean up duplicate Order records", "CD-0020 Refresh the test sandbox"]


def test_r10_a_change_becomes_one_stamped_row_and_keeps_who_and_why(scoring_eng):
    form = {"decided_by": "desk-lead", "item": "CD-0020 Refresh the test sandbox", "part": "readiness", "points": "9",
            "reason": "The sandbox owner said yes today."}
    out = scoring_eng.call("applyScoreChange", RANKED, WORKING, form, {"run_id": "n8n-5", "decided_at": "2026-11-25T03:00:00.000Z"})
    row = out["rows"][0]
    assert (row["request_id"], row["part"], row["points"], row["decided_by"]) == ("CD-0020", "readiness", 9, "desk-lead")
    assert row["stamp"] == "changedesk P-n8n-5-CD-0020-readiness | no AI | score parts (settings score_weights) | readiness 5 to 9 by desk-lead | 2026-11-25T03:00:00Z"
    same = scoring_eng.call("applyScoreChange", RANKED, WORKING, dict(form, points="5"), {"run_id": "n8n-5"})
    assert same["rows"] == [] and "already 5" in same["message"]
    with pytest.raises(Exception, match="no reason"):
        scoring_eng.call("applyScoreChange", RANKED, WORKING, dict(form, reason=" "), {"run_id": "n8n-5"})


DECIDE = [{"request_id": "CD-0029", "title": "Two-minute guide to merging Opportunity records", "lane": "small", "status": "Triaged",
           "requester_role": "Support lead", "playbook": "crm-training-enablement", "age_days": 86, "age_limit_days": 30, "days_over": 56, "score": 5.0},
          {"request_id": "CD-0016", "title": "Clean up duplicate Order records", "lane": "standard", "status": "Triaged",
           "requester_role": "Head of operations", "playbook": "crm-data-dedupe-merge", "age_days": 125, "age_limit_days": 90, "days_over": 35, "score": 4.9}]
OPEN = [{"request_id": "CD-0140", "title": "Clean up duplicate Account records", "playbook": "crm-data-dedupe-merge", "status": "Triaged"},
        {"request_id": "CD-0016", "title": "Clean up duplicate Order records", "playbook": "crm-data-dedupe-merge", "status": "Triaged"}]


def test_r16_the_decide_form_offers_do_next_merge_and_close(scoring_eng):
    fields = scoring_eng.call("buildDecideForm", DECIDE, OPEN, {"run_id": "n8n-9"})
    opts = {f["fieldName"]: [o["option"] for o in f["fieldOptions"]["values"]] for f in fields if f.get("fieldType") == "dropdown"}
    assert opts["decide_CD_0016"][:3] == ["Leave on the list for now", "Do it next", "Merge into CD-0140 (Clean up duplicate Account records)"]
    assert not any(o.startswith("Merge") for o in opts["decide_CD_0029"])  # no open item shares its playbook
    assert sum(o.startswith("Close: ") for o in opts["decide_CD_0029"]) == 4
    with pytest.raises(Exception, match="nothing is past"):
        scoring_eng.call("buildDecideForm", [], OPEN, {})


def test_r16_choices_become_stamped_rows_and_a_close_has_a_reason(scoring_eng):
    form = {"decided_by": "desk-lead", "decide_CD_0029": "Close: no longer needed", "decide_CD_0016": "Merge into CD-0140 (Clean up duplicate Account records)",
            "note": "Agreed at the desk review."}
    rows = scoring_eng.call("applyDecideChoices", DECIDE, OPEN, form, {"run_id": "n8n-9", "decided_at": "2026-11-25T04:00:00.000Z"})
    by = {r["request_id"]: r for r in rows}
    assert by["CD-0029"]["action"] == "close" and by["CD-0029"]["reason"] == "No longer needed."
    assert by["CD-0016"]["action"] == "merge" and by["CD-0016"]["merge_into"] == "CD-0140"
    assert by["CD-0016"]["reason"] == "the same need as CD-0140"
    assert all(r["note"] == "Agreed at the desk review." for r in rows)  # the note goes on each decision, not into a reason
    assert by["CD-0029"]["stamp"].endswith("| close by desk-lead | 2026-11-25T04:00:00Z")
    left = scoring_eng.call("applyDecideChoices", DECIDE, OPEN, {"decided_by": "x", "decide_CD_0029": "Leave on the list for now"}, {"run_id": "r"})
    assert left == []


# The reviewer's note from test run n8n-8909, word for word: it covers the whole form, names a person and two other items.
SHARED_NOTE = ("Test run on Israel's delegation. CD-0016 is the oldest standard item. CD-0029 is closed as no longer needed. "
               "CD-0037 is merged into CD-0145, which asks for the same thing.")


def test_a_shared_note_never_becomes_an_items_reason_or_reaches_the_drafter(scoring_eng, drafter_eng):
    """Test run n8n-8909: the note was copied into CD-0029's close reason, and the drafter, reading a person's name and
    other items in the reason, flagged the draft possible_injection and personal_data."""
    form = {"decided_by": "courses-2nd (delegated)", "decide_CD_0029": "Close: no longer needed", "decide_CD_0016": "Do it next", "note": SHARED_NOTE}
    rows = scoring_eng.call("applyDecideChoices", DECIDE, OPEN, form, {"run_id": "n8n-8909", "decided_at": "2026-11-24T22:25:34Z"})
    by = {r["request_id"]: r for r in rows}
    assert by["CD-0029"]["reason"] == "No longer needed." and by["CD-0016"]["reason"] == ""
    assert all(r["note"] == SHARED_NOTE for r in rows)
    record = drafter_eng.call("closeRecord", dict(CLOSED, reason=by["CD-0029"]["reason"]))
    assert record["reason_for_closing"] == "No longer needed."
    content = drafter_eng.call("buildCloseDraftRequest", dict(CLOSED, reason=by["CD-0029"]["reason"]), "claude-haiku-5-5")["messages"][0]["content"]
    for leaked in ("Israel", "CD-0016", "CD-0037", "CD-0145", "delegation"):
        assert leaked not in content


def test_the_test_run_draft_passes_the_code_check(drafter_eng):
    """U-n8n-8909-CD-0029, word for word. It read clean, but the old check called its last sentence a promise."""
    body = ("Hello,\n\nThank you for your request CD-0029, \"Two-minute guide to merging Opportunity records\", which you raised on "
            "30 August 2026. We have closed this request because it is no longer needed.\n\nIf the need comes back or your situation "
            "has changed, please raise a new request through the desk's intake form and we will be glad to look at it again.\n\n"
            "Thank you for your patience and for reaching out.")
    assert drafter_eng.call("draftProblems", CLOSED, {"subject": "Your request CD-0029 has been closed", "body": body}) == []


@pytest.mark.parametrize("text,promise", [
    ("Please raise a new request and we will be glad to look at it again.", False),
    ("If it comes back, send a new request and we'll consider it.", False),
    ("Please raise a new request through the desk's intake form and we will take a fresh look at it.", False),  # probe draft #2
    ("Send a new request and we will have it ready within a week.", True),
    ("Raise a new request and we will deliver it next week.", True),     # the ask-again words do not cover a delivery
    ("We will look at it again soon.", True),                            # no new request: a promise about the closed one
    ("We closed it. A new request is welcome. We will have it done by Friday.", True),
])
def test_the_promise_check_reads_one_sentence_at_a_time(drafter_eng, text, promise):
    assert drafter_eng.call("makesPromise", text) is promise


# ---------------------------------------------------------------- the message drafter

CLOSED = {"request_id": "CD-0029", "title": "Two-minute guide to merging Opportunity records", "requester_role": "Support lead",
          "arrived_on": "2026-08-31", "age_days": 86, "reason": "No longer needed.", "decision_id": "D-r-CD-0029", "decided_by": "desk-lead"}


def test_the_drafter_sees_no_score_lane_or_request_text(drafter_eng):
    req = drafter_eng.call("buildCloseDraftRequest", dict(CLOSED, score=5.0, lane="small", body="secret text"), "claude-haiku-5-5")
    content = req["messages"][0]["content"]
    assert "CD-0029" in content and "No longer needed" in content
    assert "5.0" not in content and "small" not in content and "secret text" not in content
    assert req["system"].startswith("You are the message drafter")


def test_r16_a_good_draft_is_logged_as_a_draft_with_a_stamp(drafter_eng):
    good = {"subject": "Your request CD-0029 has been closed", "flags": [],
            "body": "Hello, Support lead. We have closed CD-0029, the two-minute guide to merging Opportunity records, because it is no longer needed. "
                    "If the need comes back, please send a new request through the desk's intake form."}
    out = drafter_eng.call("checkCloseDraft", CLOSED, fake_claude(good), {"run_id": "n8n-9", "model": "claude-haiku-5-5", "now": "2026-11-25T04:01:00Z"})
    d = out["draft"]
    assert d["audience"] == "requester" and d["kind"] == "close" and d["draft_problems"] == ""
    assert d["stamp"] == "changedesk U-n8n-9-CD-0029 | claude-haiku-5-5 | close-message@1.0.1 | drafted by message_drafter | 2026-11-25T04:01:00Z"
    assert out["handoff"]["to_agent"] == "message_drafter" and out["call"]["step"] == "drafter"


@pytest.mark.parametrize("body,problem", [
    ("We closed it because its score was too low. If the need comes back, send a new request.", "names how the desk works"),
    ("We closed CD-0029. We will deliver it next week instead.", "makes a promise"),
    ("We closed CD-0029. Write to help@desk.example with questions.", "contact details"),
    ("We closed the guide request. Send a new request if needed.", "does not name the request id"),
])
def test_the_draft_check_catches_what_a_requester_must_not_get(drafter_eng, body, problem):
    problems = drafter_eng.call("draftProblems", CLOSED, {"subject": "Closed", "body": body})
    assert any(problem in p for p in problems), problems


def test_a_failed_draft_call_gives_no_draft(drafter_eng):
    out = drafter_eng.call("checkCloseDraft", CLOSED, {"error": {"message": "overloaded", "status": 529}}, {"run_id": "r", "model": "m"})
    assert out["draft"] is None and out["call"]["output_valid"] is False and out["call"]["error"]
