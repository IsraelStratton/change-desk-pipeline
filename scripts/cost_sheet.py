#!/usr/bin/env python3
"""The cost sheet (R30, KB-137 A5): what each AI call has cost, from the run log alone. Writes docs/cost-sheet.json and
docs/cost-sheet.md.

Shaped from the GTM pipeline (scripts/cost_sheet.py): every figure comes from changedesk.run_log and the price table
(pricing/claude_prices.json, loaded into changedesk.model_prices); nothing is typed in. The run log is read as the app's
own login into docs/cost-sheet.json, and the page is made from that file alone, so CI (which has no database) checks the
committed page is exactly what the file gives (tests/test_cost_sheet.py). The two figures R30 asks for are on top: the
cost of one triage and the cost of one update.

  python scripts/cost_sheet.py               # read the run log; write the JSON and the page
  python scripts/cost_sheet.py --from-json   # remake the page from the committed JSON
  python scripts/cost_sheet.py --print       # print it only

Exit codes: 0 written, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[1]
SHEET = REPO / "docs" / "cost-sheet.md"
SHEET_JSON = REPO / "docs" / "cost-sheet.json"
WHAT = {("triage", "eval", "E"): "Triage eval, the 40 tuned cases (stage 1, 3 playbooks x 3 rounds)",
        ("triage", "eval", "F"): "Triage eval, the 30 fresh cases (stage 6, playbook 1.0.2 once, 3 rounds)",
        ("triage", "python", ""): "Triage, run by hand from Python", ("triage", "n8n", ""): "Triage, run from the n8n form",
        ("drafter", "n8n", ""): "Close message drafts (decide list)",
        ("drafter", "python", ""): "Close message drafter probe, from Python (no draft stored)",
        ("updater", "python", ""): "Updates for three audiences (stage 5)"}

BY_STEP_SQL = """
select step, source, model, case when source = 'eval' then left(coalesce(case_id, ''), 1) else '' end as cases,
  count(*) as calls, count(*) filter (where not output_valid) as failed,
  round(avg(cost_usd), 8)::float8 as cost_per_call_usd, round(sum(cost_usd), 6)::float8 as total_cost_usd,
  round(avg(input_tokens))::int as avg_input_tokens, round(avg(output_tokens))::int as avg_output_tokens
from changedesk.call_cost group by 1, 2, 3, 4 order by 1 desc, 2, 4, 3
"""
UPDATER_RUNS_SQL = """
select run_id, count(*) as calls, count(*) filter (where not output_valid) as failed, min(engine_version) as version,
  round(sum(cost_usd), 6)::float8 as total_cost_usd,
  (select count(*) from changedesk.updates u where u.run_id = c.run_id and u.draft_problems = '') as clean
from changedesk.call_cost c where step = 'updater' group by run_id order by run_id
"""


def read_store() -> dict:
    import desk_db

    with desk_db.connect() as conn:
        return {
            "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "read_from": "changedesk.call_cost (the run log with the price table)",
            "by_step": desk_db.rows(conn, BY_STEP_SQL),
            "updater_runs": desk_db.rows(conn, UPDATER_RUNS_SQL),
            "prices": desk_db.rows(conn, "select model, input_per_mtok::float8 as input_per_mtok, output_per_mtok::float8 as output_per_mtok, "
                                         "read_on, source from changedesk.model_prices order by model"),
            "totals": desk_db.rows(conn, "select count(*) as calls, coalesce(sum(cost_usd), 0)::float8 as total from changedesk.call_cost")[0],
        }


def per_call(rows: list[dict], step: str, live_only: bool) -> tuple[float, int]:
    """The average cost of one call of a step, over its live calls (or over every call)."""
    picked = [r for r in rows if r["step"] == step and (not live_only or r["source"] != "eval")]
    calls = sum(r["calls"] for r in picked)
    total = sum(r["total_cost_usd"] for r in picked)
    return (total / calls if calls else 0.0), calls


def render(snap: dict) -> str:
    rows = snap["by_step"]
    triage, tn = per_call(rows, "triage", live_only=False)
    update, un = per_call(rows, "updater", live_only=False)
    lines = ["# Cost sheet", "",
             "Made by `scripts/cost_sheet.py` from the run log (`changedesk.run_log`) and the price table, through `docs/cost-sheet.json`. "
             "Every call the AI steps made is in it, failed ones too. No paid plan: calls are billed to the build's capped Claude key "
             "(workspace gtm-pipeline, US$10 monthly limit). Every request is made up.", "",
             "## The cost of one triage and one update (R30)", "",
             f"- **One triage: US${triage:.6f}** (Haiku 5.5; the average of {tn} triage calls, the evals included).",
             f"- **One update: US${update:.6f}** (Haiku 5.5; the average of {un} update drafter calls). A drafting run for one forecast "
             "drafts one update for each reader: each requester with an item that moved, the manager and the executive.", "",
             "## Every call, by step", "",
             "| What | Model | Calls | Failed | Cost per call (US$) | Total (US$) | Average tokens in / out |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        what = WHAT.get((r["step"], r["source"], r["cases"]), f"{r['step']}, {r['source']}")
        lines.append(f"| {what} | {r['model']} | {r['calls']} | {r['failed']} | {r['cost_per_call_usd']:.6f} | {r['total_cost_usd']:.6f} | "
                     f"{r['avg_input_tokens']} / {r['avg_output_tokens']} |")
    if snap["updater_runs"]:
        lines += ["", "## The update drafter's runs (stage 5)", "",
                  "| Run | Drafter | Calls | Failed | Drafts that passed every check | Total (US$) |", "|---|---|---|---|---|---|"]
        for r in snap["updater_runs"]:
            lines.append(f"| `{r['run_id']}` | {r['version']} | {r['calls']} | {r['failed']} | {r['clean']} | {r['total_cost_usd']:.6f} |")
    t = snap["totals"]
    lines += ["", f"All calls: {t['calls']}, US${t['total']:.6f}. One stage 1 eval run of about US$0.10 is not in the run log (lost to a path "
              "bug before its results were saved; stage 1 notes).", "", "Prices used (per million tokens):", ""]
    for p in snap["prices"]:
        lines.append(f"- {p['model']}: US${p['input_per_mtok']:.2f} in, US${p['output_per_mtok']:.2f} out (read {p['read_on']}, {p['source']})")
    lines += ["", f"Read from {snap['read_from']} at {snap['made_at']}.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--from-json", action="store_true")
    args = ap.parse_args(argv)
    try:
        snap = json.loads(SHEET_JSON.read_text(encoding="utf-8")) if args.from_json else read_store()
    except Exception as e:  # noqa: BLE001
        print(f"CANNOT RUN {type(e).__name__}: {e}")
        return 2
    text = render(snap)
    if args.print:
        print(text)
        return 0
    if not args.from_json:
        SHEET_JSON.write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    SHEET.write_text(text, encoding="utf-8")
    print(f"Wrote docs/cost-sheet.md: {snap['totals']['calls']} calls, US${snap['totals']['total']:.6f}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
