"""R30 (KB-137 A5): the cost sheet is made by script from the run log, through a JSON CI can check; no figure on it is
typed by hand; it gives the cost of one triage and of one update. Shaped from the GTM pipeline's test."""
import json
import re
import sys

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import cost_sheet  # noqa: E402

SNAP = json.loads(cost_sheet.SHEET_JSON.read_text(encoding="utf-8"))
FIXTURE = {
    "made_at": "2026-11-25T00:00:00Z", "read_from": "a test fixture",
    "by_step": [
        {"step": "updater", "source": "python", "model": "claude-haiku-5-5", "cases": "", "calls": 7, "failed": 0, "cost_per_call_usd": 0.0008,
         "total_cost_usd": 0.0056, "avg_input_tokens": 3000, "avg_output_tokens": 900},
        {"step": "triage", "source": "eval", "model": "claude-haiku-5-5", "cases": "F", "calls": 90, "failed": 0, "cost_per_call_usd": 0.0009,
         "total_cost_usd": 0.081, "avg_input_tokens": 7000, "avg_output_tokens": 370},
        {"step": "triage", "source": "python", "model": "claude-haiku-5-5", "cases": "", "calls": 10, "failed": 0, "cost_per_call_usd": 0.0009,
         "total_cost_usd": 0.009, "avg_input_tokens": 7000, "avg_output_tokens": 360},
    ],
    "updater_runs": [{"run_id": "up-x", "calls": 7, "failed": 0, "version": "1.0.2", "total_cost_usd": 0.0056, "clean": 6}],
    "prices": [{"model": "claude-haiku-5-5", "input_per_mtok": 0.1, "output_per_mtok": 0.5, "read_on": "2026-11-23", "source": "https://example.org/prices"}],
    "totals": {"calls": 107, "total": 0.0956},
}


def test_the_committed_sheet_is_exactly_what_the_script_makes_from_its_json():
    assert cost_sheet.SHEET.read_text(encoding="utf-8") == cost_sheet.render(SNAP)


def test_the_sheet_gives_one_triage_and_one_update_from_the_rows():
    page = cost_sheet.render(FIXTURE)
    assert "**One triage: US$0.000900** (Haiku 5.5; the average of 100 triage calls, the evals included)." in page
    assert "**One update: US$0.000800** (Haiku 5.5; the average of 7 update drafter calls)." in page
    assert "| Triage eval, the 30 fresh cases (stage 6, playbook 1.0.2 once, 3 rounds) | claude-haiku-5-5 | 90 | 0 | 0.000900 | 0.081000 |" in page
    assert "| `up-x` | 1.0.2 | 7 | 0 | 6 | 0.005600 |" in page


def test_the_committed_sheet_covers_triage_the_drafters_and_both_evals():
    steps = {(r["step"], r["source"], r["cases"]) for r in SNAP["by_step"]}
    assert {("triage", "eval", "E"), ("triage", "eval", "F"), ("updater", "python", ""), ("drafter", "n8n", "")} <= steps
    assert SNAP["totals"]["calls"] == sum(r["calls"] for r in SNAP["by_step"])


def test_every_price_shows_the_date_it_was_read_and_its_source():
    page = cost_sheet.render(SNAP)
    for p in SNAP["prices"]:
        assert f"(read {p['read_on']}, {p['source']})" in page


def test_no_price_or_cost_is_typed_into_the_script():
    source = (REPO / "scripts" / "cost_sheet.py").read_text(encoding="utf-8")
    assert not re.search(r"\b0\.0\d{3,}\b|\b(2|10)\.00\b", source)
