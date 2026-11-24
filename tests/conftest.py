"""Shared test helpers: the engines through the same bridge Python uses, the n8n Code node harness, a
rolled-back connection as the app's own login, and a rolled-back owner session for the store's guards.

Tests that need the local store are skipped when it cannot be reached (CI has no database and no .env).
Nothing a test does is kept: every database test runs inside a transaction that is rolled back.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from desk_engine import PLAYBOOK, Engine  # noqa: E402

HARNESS = REPO / "tests" / "n8n_harness.js"
SETTINGS = {s["key"]: s["value"] for s in json.loads((REPO / "settings" / "settings.json").read_text(encoding="utf-8"))["settings"]}
GOALS = json.loads((REPO / "sample" / "goals.json").read_text(encoding="utf-8"))["goals"]
CONTAINER = "supabase_db_hubspot-ai-database"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


@pytest.fixture(scope="session")
def triage_eng():
    if NODE is None:
        pytest.skip("node not installed")
    return Engine("triage")


@pytest.fixture(scope="session")
def scoring_eng():
    if NODE is None:
        pytest.skip("node not installed")
    return Engine("scoring")


@pytest.fixture(scope="session")
def drafter_eng():
    if NODE is None:
        pytest.skip("node not installed")
    return Engine("drafter")


@pytest.fixture(scope="session")
def pb(triage_eng):
    return triage_eng.call("parseTriagePlaybook", PLAYBOOK.read_text(encoding="utf-8"))


def run_node(workflow: str, node: str, items: list[dict] | None = None, outputs: dict | None = None, execution_id: str = "77") -> list[dict]:
    payload = json.dumps({"workflow": str(REPO / "n8n" / workflow), "node": node, "items": items or [], "outputs": outputs or {},
                          "execution_id": execution_id}, default=str)
    out = subprocess.run([NODE, str(HARNESS)], input=payload, capture_output=True, text=True, check=False)
    reply = json.loads(out.stdout or '{"ok": false, "error": "no output"}')
    if not reply["ok"]:
        raise RuntimeError(reply["error"])
    return reply["items"]


def fake_claude(answer: dict, model: str = "claude-haiku-5-5", stop: str = "end_turn") -> dict:
    """A Claude reply in n8n's full-response shape, holding one JSON answer."""
    return {"statusCode": 200, "headers": {"request-id": "req_fake"},
            "body": {"id": "msg_fake", "type": "message", "role": "assistant", "model": model, "stop_reason": stop,
                     "content": [{"type": "text", "text": json.dumps(answer)}], "usage": {"input_tokens": 3200, "output_tokens": 300}}}


def answer(**over) -> dict:
    """A well-formed triage answer for a small field change; override any key."""
    base = {
        "type": "enhancement", "size_hours": 1.5, "lane": "small", "due_date": None, "what_breaks": None, "is_urgent": False,
        "harm_growing": None, "goal_id": "G4", "playbook": "crm-config-field-change", "split": [],
        "score": {"value": {"points": 5, "reason": "Saves the sales team retyping a value each week."},
                  "risk": {"points": 9, "reason": "One picklist value, easy to undo."},
                  "goal_fit": {"points": 6, "reason": "Lets the pipeline report count the source."},
                  "readiness": {"points": 9, "reason": "The value is named; it can start now."}},
        "reason": "Adds one picklist value; about an hour and a half, no date that breaks and no harm growing.",
        "confidence": 0.9, "flags": [],
    }
    base.update(over)
    return base


# ---------------------------------------------------------------- the store

def _app_password() -> str | None:
    from dotenv import dotenv_values

    env = REPO / ".env"
    return (dotenv_values(env).get("CHANGEDESK_DB_PASSWORD") if env.exists() else None) or None


@pytest.fixture
def db():
    """A connection as changedesk_app, inside a transaction that is rolled back after the test."""
    if not _app_password():
        pytest.skip("no local store (.env has no CHANGEDESK_DB_PASSWORD)")
    try:
        import desk_db

        conn = desk_db.connect(autocommit=False)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"local store not reachable ({type(e).__name__})")
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def owner_sql(sql: str) -> subprocess.CompletedProcess:
    """Run SQL as the owner in the db container, inside begin ... rollback. Returns the finished process."""
    if shutil.which("docker") is None:
        pytest.skip("docker not installed")
    up = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=False)
    if CONTAINER not in up.stdout.split():
        pytest.skip("the Supabase db container is not running")
    return subprocess.run(["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1",
                           "-q", "-At"], input=f"begin;\n{sql}\nrollback;\n", capture_output=True, text=True, check=False)


def j(v) -> str:
    return json.dumps(v, default=str)
