"""The two forms the reviewer uses in the stage 5 test run, built from the store's live rows (not fixtures): the approval
form from the drafts as its Read Drafts node reads them, and the decide form from the decide list. Run as the app's own
login; skipped when there is no local store (CI). The reviewer cannot run scripts, so a data-shape fault here would only
show in the test run."""
import json
import sys

import pytest
from conftest import NODE, REPO, run_node

sys.path.insert(0, str(REPO / "scripts"))
import build_n8n  # noqa: E402
import desk_db  # noqa: E402

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def items(db, sql):
    return [{"json": r} for r in desk_db.rows(db, sql.rstrip(";"))]


def test_the_approval_form_builds_from_every_draft_in_the_store(db):
    drafts = items(db, build_n8n.DRAFTS_SQL)
    if not drafts:
        pytest.skip("no draft waits (after the demo reset, or after the test run)")
    built = run_node("approve-updates.json", "Build Form", drafts)[0]["json"]
    fields = built["form_fields"]
    assert built["count"] == len(drafts) and len(fields) == len(drafts) + 3
    approvable = sum(1 for d in drafts if not d["json"]["draft_problems"] and not d["json"]["stale"])
    assert f"{approvable} can be approved" in fields[0]["html"]
    assert len(json.dumps(fields)) < 500_000, "the form fits in one page"
    for d in drafts:
        f = next(x for x in fields if x.get("fieldName") == f"approve_{''.join(c if c.isalnum() else '_' for c in d['json']['update_id'])}")
        offered = [o["option"] for o in f["fieldOptions"]["values"]]
        assert ("Approve: place it in the outbox" in offered) == (not d["json"]["draft_problems"] and not d["json"]["stale"]), d["json"]["update_id"]


def test_the_decide_form_builds_from_the_live_list_with_the_missed_dates_first(db):
    listed = items(db, build_n8n.DECIDE_SQL)
    if not listed:
        pytest.skip("nothing on the decide list")
    built = run_node("decide.json", "Build Form", outputs={"Read Decide List": listed, "Read Open Items": items(db, build_n8n.OPEN_SQL)})[0]["json"]
    labels = [f["fieldLabel"] for f in built["form_fields"] if f.get("fieldName", "").startswith("decide_")]
    passed = [r["json"]["request_id"] for r in listed if r["json"]["why"] == "its fixed date has passed"]
    assert all(lab.endswith("days ago)") for lab in labels[:len(passed)]) and [lab.split()[0] for lab in labels[:len(passed)]] == passed
