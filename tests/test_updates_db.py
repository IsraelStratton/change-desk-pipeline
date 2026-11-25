"""Stage 5 in the store (R22 to R25), as the app's own login inside a transaction that is rolled back. A large change (the
week cut from 40 hours to 24) moves many 85% dates; the real pack builder (scripts/draft_updates.py) makes one pack for
each reader from the rows; a stand-in drafter writes each update from its pack alone, the way the brief asks; the real
engine checks it; changedesk.log_updates stores it. Then the R23 check script, the approval function and the outbox."""
import json
import sys
from datetime import date

import pytest
from conftest import NODE, REPO, fake_claude, j, owner_sql

sys.path.insert(0, str(REPO / "scripts"))
import check_updates  # noqa: E402
import desk_db  # noqa: E402
import draft_updates as DU  # noqa: E402
import forecast as F  # noqa: E402
from desk_engine import Engine  # noqa: E402

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")
WEEK = date(2026, 11, 23)
TODAY = date(2026, 11, 25)
NOW = "2026-11-25T03:00:00Z"


def log_run(db, rid, rows, lanes, made_at):
    run = {"run_id": rid, "purpose": "forecast", "start_week": WEEK.isoformat(), "rule": "lanes", "runs": 120, "horizon_weeks": 26, "seed": 163,
           "load": 1.0, "safe_start_days": 7, "settings": {}, "made_by": "test", "made_at": made_at, "stamp": f"changedesk {rid} | test"}
    db.execute("select changedesk.log_forecast(%s::jsonb, %s::jsonb, '[]'::jsonb)", (j(run), j(rows + lanes)))


def stand_in(figs: Engine, pack: dict) -> str:
    """What a drafter that follows the brief writes: every figure a fact's value, every item answered."""
    shown = dict(zip([f["id"] for f in pack["facts"]], figs.batch([("showFact", [f]) for f in pack["facts"]])))
    if pack["audience"] != "requester":
        picks = [f for f in pack["facts"] if f["kind"] in ("number", "percent", "date") and f["value"] is not None]
        if pack["audience"] == "executive":
            picks = [f for f in picks if "CD-" not in f["says"]]
        return " ".join(f"{f['says'][:1].upper() + f['says'][1:]}: {shown[f['id']]}." for f in picks[:6])
    out = [f"Hello, {pack['to_role']}."]
    for it in pack["items"]:
        f = {k: shown[v] for k, v in it["facts"].items()}
        a = it["answer"]
        s = f"{it['request_id']} {it['title']}: "
        if a == "date_range":
            s += f"we expect it between {f['p50']} and {f['p95']}, and 85% likely by {f['p85']}."
        elif a == "this_week":
            s += f"it is in this week's plan, the week of {f['week']}, and we expect it to be finished this week."
        elif a == "service_level":
            s += f"for small requests like this one, 85% are done within {f['service_level_days']}."
        elif a == "fixed_chance":
            s += f"there is a {f['chance']} chance of meeting {f['due_date']}; the work must start by {f['latest_safe_start']}."
        elif a == "passed_date":
            s += f"its date, {f['due_date']}, has passed. A person is deciding whether it is still needed" + (
                f"; if it is, it is 85% likely to be done by {f['p85']}." if "p85" in f else
                f"; if it is, it is in this week's plan, the week of {f['week']}." if "week" in f else ".")
        elif a == "no_date":
            s += f"no date can be given yet; a person decides on it if it waits more than {f['age_limit_days']}."
        else:
            s += "a person is confirming how it will be handled; there is no date until then."
        if it["moved"] and "old_p85" in f:
            s += f" Before, we expected it by {f['old_p85']}."
        if it["on_decide_list"] and a != "passed_date":
            s += " A person is deciding whether to do it next, merge it or close it."
        out.append(s)
    out.append("If the need has changed, you can raise a new request through the desk's intake form.")
    return "\n\n".join(out)


@pytest.fixture
def stage5(db):
    """Two forecast runs either side of a large change, the trigger logged, the packs built and drafted, the drafts logged."""
    *_, rows, lanes, _n = F.run_forecast(db, WEEK, runs=120)
    log_run(db, "fc-u-a", rows, lanes, "2099-01-01T01:00:00Z")
    db.execute("select changedesk.set_setting('hours_per_week', '24'::jsonb, 'desk-lead (test)', 'stage 5 test, rolled back')")
    *_, rows, lanes, _n = F.run_forecast(db, WEEK, runs=120)
    log_run(db, "fc-u-b", rows, lanes, "2099-01-01T02:00:00Z")
    run = DU.forecast_run(db, "fc-u-b")
    prev = DU.previous_run(db, run)
    triggers = DU.find_triggers(db, run, prev, 7)
    db.execute("select changedesk.log_updates('[]'::jsonb, %s::jsonb, '[]'::jsonb, '[]'::jsonb)", (j(triggers),))
    packs = [p.doc() for p in DU.build_packs(db, run, prev, TODAY, triggers, "up-test")]
    up, figs = Engine("updates"), Engine("figures")
    outs = [up.call("checkUpdateDraft", p, fake_claude({"subject": f"An update for {p['to_role']}", "body": stand_in(figs, p), "flags": []}),
                    {"run_id": "up-test", "model": "claude-haiku-5-5", "now": NOW}) for p in packs]
    n = db.execute("select changedesk.log_updates(%s::jsonb, '[]'::jsonb, %s::jsonb, %s::jsonb) as n",
                   (j([o["call"] for o in outs]), j([o["draft"] for o in outs]), j([o["handoff"] for o in outs]))).fetchone()["n"]
    return {"db": db, "run": run, "prev": prev, "triggers": triggers, "packs": packs, "outs": outs, "n": n, "up": up, "figs": figs}


def drafts(db, run_id="up-test"):
    return desk_db.rows(db, check_updates.SELECT + " where u.run_id = %s order by u.audience desc, u.update_id", (run_id,))


def test_r20_a_large_change_triggers_from_the_store_rows(stage5):
    assert stage5["prev"]["run_id"] == "fc-u-a" and len(stage5["triggers"]) >= 10
    rows = desk_db.rows(stage5["db"], "select why, moved_days from changedesk.update_triggers where run_id = 'fc-u-b'")
    assert len(rows) == len(stage5["triggers"]) and all(r["why"] != "moved" or r["moved_days"] > 7 for r in rows)


def test_r22_three_audiences_are_drafted_from_one_run(stage5):
    got = drafts(stage5["db"])
    assert stage5["n"] == len(got) == len(stage5["packs"])
    assert {u["audience"] for u in got} == {"requester", "manager", "executive"}
    assert {(u["run_id"], u["forecast_run_id"], u["status"], u["kind"]) for u in got} == {("up-test", "fc-u-b", "draft", "status")}
    assert all(u["draft_problems"] == "" for u in got), [(u["update_id"], u["draft_problems"]) for u in got if u["draft_problems"]]
    assert all(u["stamp"].startswith(f"changedesk {u['update_id']} | claude-haiku-5-5 | status-update@") for u in got)
    calls = desk_db.rows(stage5["db"], "select step, update_id, request_id from changedesk.run_log where run_id = 'up-test'")
    assert {c["step"] for c in calls} == {"updater"} and {c["update_id"] for c in calls} == {u["update_id"] for u in got}


def test_r22_pipe_data_only_no_request_text_reaches_the_drafter(stage5):
    db, up = stage5["db"], stage5["up"]
    bodies = [r["body"] for r in desk_db.rows(db, "select body from changedesk.requests where status in ('Triaged','Planned','In progress')")]
    for p in stage5["packs"]:
        sent = up.call("buildUpdateRequest", p, "claude-haiku-5-5")["messages"][0]["content"]
        assert not any(b in sent for b in bodies if len(b) > 30)
        assert all(f["source"]["table"] in ("forecasts", "requests", "settings", "settings_history", "update_triggers", "week_plan",
                                            "decide_list_at", "awaiting_confirmation") for f in p["facts"])
        assert all(f["source"].get("column") != "body" for f in p["facts"])


def test_r23_the_check_script_finds_the_row_of_every_figure(stage5):
    db = stage5["db"]
    eng = (Engine("figures"), stage5["up"], Engine("drafter"))
    results = [check_updates.check_one(db, u, *eng) for u in drafts(db)]
    assert all(r["fails"] == [] for r in results), [r["fails"] for r in results if r["fails"]]
    assert all(r["rows"] for r in results) and all(x["ok"] and x["now"] == x["drafted"] for r in results for x in r["rows"])
    assert "`forecasts` where run_id = fc-u-b" in check_updates.report(results, "test")


def test_r23_a_figure_from_nowhere_is_a_problem_and_the_check_script_fails_it(stage5):
    db, up = stage5["db"], stage5["up"]
    p = next(x for x in stage5["packs"] if x["audience"] == "manager")
    bad = up.call("checkUpdateDraft", dict(p, update_id="U-up-test-bad"), fake_claude({"subject": "Manager update", "flags": [],
                                                                                        "body": "The team finished 61 requests this quarter."}),
                  {"run_id": "up-test", "model": "m", "now": NOW})
    assert 'no source in the pack: "61"' in bad["draft"]["draft_problems"]
    db.execute("select changedesk.log_updates(%s::jsonb, '[]'::jsonb, %s::jsonb, '[]'::jsonb)", (j([bad["call"]]), j([bad["draft"]])))
    u = desk_db.rows(db, check_updates.SELECT + " where u.update_id = 'U-up-test-bad'")[0]
    assert check_updates.check_one(db, u, Engine("figures"), up, Engine("drafter"))["fails"] == ['"61" has no source']
    with pytest.raises(Exception, match="it can only be rejected"):
        db.execute("select changedesk.approve_updates(%s::jsonb)", (j([approval("U-up-test-bad", "approved")]),))


def test_r23_a_fact_that_is_not_its_rows_value_is_refused(stage5):
    db, out = stage5["db"], stage5["outs"][-1]
    forged = json.loads(json.dumps(out["draft"]))
    forged["update_id"] = "U-up-test-forged"
    f = next(x for x in forged["facts"] if x["kind"] == "number")
    f["value"] = str(float(f["value"] or 0) + 99)
    with pytest.raises(Exception, match="holds facts that are not their rows' values"):
        db.execute("select changedesk.log_updates('[]'::jsonb, '[]'::jsonb, %s::jsonb, '[]'::jsonb)", (j([forged]),))


def test_r23_a_fact_may_read_only_the_listed_tables_and_columns(db):
    for src, msg in (({"table": "requests", "where": {"request_id": "CD-0016"}, "column": "body"}, "has no column body"),
                     ({"table": "run_log", "agg": "count"}, "is not a table a fact may read"),
                     ({"table": "requests", "where": {"lane = 'x' or true; --": "1"}, "column": "title"}, "cannot be filtered on"),
                     ({"table": "requests", "where": {"lane": "small"}, "column": "title"}, "not one")):
        db.execute("savepoint s")
        with pytest.raises(Exception, match=msg):
            db.execute("select changedesk.fact_value(%s::jsonb)", (j(src),))
        db.execute("rollback to savepoint s")


def test_r22_a_draft_must_sit_behind_a_trigger_and_cover_its_requesters_items_only(stage5):
    db, out = stage5["db"], next(o for o in stage5["outs"] if o["draft"]["audience"] == "requester")
    untriggered = dict(out["draft"], update_id="U-up-test-x", forecast_run_id="fc-u-a")
    db.execute("savepoint s")
    with pytest.raises(Exception, match="is not behind a trigger"):
        db.execute("select changedesk.log_updates('[]'::jsonb, '[]'::jsonb, %s::jsonb, '[]'::jsonb)", (j([untriggered]),))
    db.execute("rollback to savepoint s")
    other = db.execute("select request_id from changedesk.requests where status = 'Triaged' and requester_role <> %s limit 1",
                       (out["draft"]["to_role"],)).fetchone()["request_id"]
    foreign = dict(out["draft"], update_id="U-up-test-y", items=out["draft"]["items"] + [other])
    with pytest.raises(Exception, match="names items that are not"):
        db.execute("select changedesk.log_updates('[]'::jsonb, '[]'::jsonb, %s::jsonb, '[]'::jsonb)", (j([foreign]),))


def test_r25_every_open_item_of_a_requester_is_answered(stage5):
    db = stage5["db"]
    req = [u for u in drafts(db) if u["audience"] == "requester"]
    assert len(req) >= 5, "five drafts to read through"
    for u in req:
        open_ids = {r["request_id"] for r in desk_db.rows(db, "select request_id from changedesk.requests where requester_role = %s "
                                                              "and status in ('Triaged','Planned','In progress')", (u["to_role"],))}
        assert set(u["items"]) == open_ids
        assert {c["request_id"] for c in u["coverage"]} == open_ids and all(c["ok"] for c in u["coverage"])
        assert {c["answer"] for c in u["coverage"]} <= {"date_range", "this_week", "service_level", "fixed_chance", "passed_date", "no_date", "waits"}
    p = next(x for x in stage5["packs"] if x["audience"] == "requester" and len(x["items"]) >= 2)
    short = stand_in(stage5["figs"], dict(p, items=p["items"][:-1]))
    d = stage5["up"].call("checkUpdateDraft", p, fake_claude({"subject": "s", "body": short, "flags": []}), {"run_id": "t", "model": "m"})["draft"]
    assert f"{p['items'][-1]['request_id']} is not answered: it is not named" in d["draft_problems"]


def approval(uid, action, who="desk-lead (test)", reason=""):
    did = f"A-test-{uid}"
    return {"decision_id": did, "run_id": "n8n-test", "update_id": uid, "action": action, "reason": reason, "decided_by": who,
            "decided_at": NOW, "note": "", "stamp": f"changedesk {did} | no AI | approval form | {action} by {who} | {NOW}"}


def test_r24_a_person_approves_and_the_update_goes_to_the_outbox_and_nowhere_else(stage5):
    db = stage5["db"]
    got = {u["audience"]: u for u in drafts(db)}
    r, m, e = got["requester"]["update_id"], got["manager"]["update_id"], got["executive"]["update_id"]
    res = db.execute("select changedesk.approve_updates(%s::jsonb) as r", (j([approval(r, "approved"),
                                                                              approval(m, "rejected", reason="the wording is not right")]),)).fetchone()["r"]
    assert res == {"approved": [r], "rejected": [m], "outbox": [f"O-{r}"]}
    box = desk_db.rows(db, "select * from changedesk.outbox where update_id = %s", (r,))[0]
    dec = desk_db.rows(db, "select * from changedesk.decisions where decision_id = %s", (box["decision_id"],))[0]
    assert (dec["kind"], dec["action"], dec["decided_by"], dec["detail"]["update_id"]) == ("update", "approved", "desk-lead (test)", r)
    assert box["held"].startswith("Held in the outbox: nothing is sent") and box["body"] == got["requester"]["body"]
    assert desk_db.rows(db, "select status, approved_by from changedesk.updates where update_id = %s", (m,))[0] == {
        "status": "rejected", "approved_by": "desk-lead (test)"}
    assert not desk_db.rows(db, "select 1 from changedesk.outbox where update_id = %s", (m,))
    for bad, msg in ((approval(r, "approved"), "is approved already"), (approval(e, "rejected"), "needs a reason"),
                     (approval(e, "approved", who="update_drafter"), "a person approves"), (approval(e, "approved", who=" "), "who decided")):
        db.execute("savepoint s")
        with pytest.raises(Exception, match=msg):
            db.execute("select changedesk.approve_updates(%s::jsonb)", (j([bad]),))
        db.execute("rollback to savepoint s")


def test_r24_an_update_the_pipe_has_overtaken_cannot_be_approved(stage5):
    db = stage5["db"]
    m = next(u for u in drafts(db) if u["audience"] == "manager")
    db.execute("select changedesk.set_setting('hours_per_week', '30'::jsonb, 'desk-lead (test)', 'stage 5 test, rolled back')")
    stale = desk_db.rows(db, "select * from changedesk.stale_facts(%s)", (m["update_id"],))
    assert [s["says"] for s in stale] == ["hours of work a week"] and (stale[0]["drafted"], stale[0]["now"]) == ("24", "30")
    with pytest.raises(Exception, match="no longer matches the pipe"):
        db.execute("select changedesk.approve_updates(%s::jsonb)", (j([approval(m["update_id"], "approved")]),))


def test_r24_the_outbox_takes_no_row_without_an_approval_even_from_the_owner():
    """As the database owner, inside a transaction that is rolled back: a row with no approval decision is refused, and so is
    any change to a row that is there. The test makes its own draft, so it does not depend on what the store holds (after
    the demo reset there is no draft at all)."""
    own = """
      insert into changedesk.updates (update_id, run_id, audience, kind, request_id, to_role, subject, body, drafted_by, drafted_at, status, stamp)
      select 'U-owner-test', 'owner-test', 'requester', 'close', request_id, requester_role, 'Closed', 'A test message.', 'test', now(), 'draft',
        'changedesk U-owner-test | test' from changedesk.requests order by request_id limit 1;"""
    no_approval = owner_sql(own + """
      insert into changedesk.decisions (decision_id, run_id, request_id, kind, action, detail, decided_by, decided_at, note, stamp)
      select 'A-t', 't', request_id, 'update', 'rejected', jsonb_build_object('update_id', update_id), 'desk-lead', now(), '', 'changedesk A-t'
      from changedesk.updates where update_id = 'U-owner-test';
      insert into changedesk.outbox (outbox_id, update_id, decision_id, audience, to_role, subject, body, approved_by, approved_at, stamp)
      select 'O-t', update_id, 'A-t', audience, to_role, subject, body, 'desk-lead', now(), 'changedesk A-t'
      from changedesk.updates where update_id = 'U-owner-test';""")
    assert no_approval.returncode != 0 and "has no approval row" in no_approval.stderr, no_approval.stderr
    changed = owner_sql(own + """
      insert into changedesk.decisions (decision_id, run_id, request_id, kind, action, detail, decided_by, decided_at, note, stamp)
      select 'A-t', 't', request_id, 'update', 'approved', jsonb_build_object('update_id', update_id), 'desk-lead', now(), '', 'changedesk A-t'
      from changedesk.updates where update_id = 'U-owner-test';
      update changedesk.updates set status = 'approved', approved_by = 'desk-lead', approved_at = now(), decision_id = 'A-t'
      where update_id = 'U-owner-test';
      insert into changedesk.outbox (outbox_id, update_id, decision_id, audience, to_role, subject, body, approved_by, approved_at, stamp)
      select 'O-t', update_id, 'A-t', audience, to_role, subject, body, 'desk-lead', now(), 'changedesk A-t'
      from changedesk.updates where update_id = 'U-owner-test';
      select 'placed ' || count(*) from changedesk.outbox where outbox_id = 'O-t';
      update changedesk.outbox set body = 'changed after approval' where outbox_id = 'O-t';""")
    assert "placed 1" in changed.stdout, "an approved row goes in"
    assert changed.returncode != 0 and "the outbox is add-only" in changed.stderr, changed.stderr
