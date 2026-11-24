"""scripts/n8n_publish.py check: n8n 2.x runs a workflow's published version, not its saved draft. After test run
n8n-8905 to n8n-8909, the five workflows were switched on and off in the n8n screens (Publish, then Unpublish), which
saves a named version. The check now reads the published version too. No network: n8n's replies are made up here."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_n8n  # noqa: E402
import n8n_publish as pub  # noqa: E402

WANTED = build_n8n.build("intake")


def live(active: bool, active_id: str | None, version_id: str = "v2") -> dict:
    return {"name": WANTED["name"], "nodes": WANTED["nodes"], "connections": WANTED["connections"],
            "settings": {"executionOrder": "v1", "callerPolicy": "workflowsFromSameOwner"}, "active": active,
            "activeVersionId": active_id, "versionId": version_id}


def version(nodes=None) -> dict:
    return {"versionId": "v2", "name": "Version v2", "nodes": nodes or WANTED["nodes"], "connections": WANTED["connections"]}


def test_off_with_no_published_version_is_in_step():
    """What the check found on 25/11/2026: off, unpublished, with a named version saved by the n8n screens."""
    assert pub.published_problems(live(False, None), None, WANTED) == []


def test_off_but_still_published_is_reported():
    assert pub.published_problems(live(False, "v2"), version(), WANTED) == ["it is off but still has a published version (v2)"]


def test_on_and_published_from_the_latest_saved_version_that_matches_the_file():
    assert pub.published_problems(live(True, "v2"), version(), WANTED) == []


def test_on_but_running_an_older_version_is_reported():
    assert "the published version is not the latest saved version" in pub.published_problems(live(True, "v1"), version(), WANTED)


def test_a_published_version_that_differs_from_the_file_is_reported():
    nodes = [dict(n, parameters=dict(n.get("parameters") or {}, jsCode="return [];")) if n["type"].endswith(".code") else n
             for n in WANTED["nodes"]]
    problems = pub.published_problems(live(True, "v2"), version(nodes), WANTED)
    assert problems and all(p.startswith("published version: node ") for p in problems)


def test_on_with_no_published_version_is_reported():
    assert pub.published_problems(live(True, None), None, WANTED) == ["it is on but n8n reports no published version"]
