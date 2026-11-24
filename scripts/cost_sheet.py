#!/usr/bin/env python3
"""The cost sheet (R30, KB-137 A5): what each AI call has cost, from the run log alone. Writes docs/cost-sheet.md.

Shaped from the GTM pipeline (scripts/cost_sheet.py). Every figure comes from changedesk.run_log and the price
table (pricing/claude_prices.json, loaded into changedesk.model_prices); nothing is typed in. Read as the app's
own login.

  python scripts/cost_sheet.py           # write docs/cost-sheet.md
  python scripts/cost_sheet.py --print   # print it only

Exit codes: 0 written, 2 could not run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk_db  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SHEET = REPO / "docs" / "cost-sheet.md"
WHAT = {("triage", "eval"): "Triage eval (labelled requests)", ("triage", "python"): "Triage, run by hand from Python",
        ("triage", "n8n"): "Triage, run from the n8n form", ("drafter", "n8n"): "Close message drafts (decide list)",
        ("drafter", "python"): "Close message drafts, from Python"}


def render(rows: list[dict], prices: list[dict], totals: dict) -> str:
    lines = ["# Cost sheet", "",
             "Made by `scripts/cost_sheet.py` from the run log (`changedesk.run_log`) and the price table. Every call the AI steps made "
             "is in it, failed ones too. Free tiers only: the Claude key's workspace has a US$10 monthly limit.", "",
             "| What | Model | Calls | Cost per call (US$) | Total (US$) | Average tokens in / out |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {WHAT.get((r['step'], r['source']), r['step'] + ', ' + r['source'])} | {r['model']} | {r['calls']} | "
                     f"{r['cost_per_call_usd']:.6f} | {r['total_cost_usd']:.6f} | {int(r['avg_input_tokens'] or 0)} / {int(r['avg_output_tokens'] or 0)} |")
    lines += ["", f"All calls: {totals['calls']}, US${totals['total']:.6f}.", "", "Prices used (per million tokens):", ""]
    for p in prices:
        lines.append(f"- {p['model']}: US${p['input_per_mtok']:.2f} in, US${p['output_per_mtok']:.2f} out (read {p['read_on']}, {p['source']})")
    lines += ["", "Every request is made up. The figures show direction, not size.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args(argv)
    try:
        with desk_db.connect() as conn:
            rows = desk_db.rows(conn, "select * from changedesk.cost_by_step order by step desc, source, model")
            prices = desk_db.rows(conn, "select * from changedesk.model_prices order by model")
            totals = desk_db.rows(conn, "select count(*) as calls, coalesce(sum(cost_usd), 0)::float8 as total from changedesk.call_cost")[0]
    except Exception as e:  # noqa: BLE001
        print(f"CANNOT RUN {type(e).__name__}: {e}")
        return 2
    text = render(rows, prices, totals)
    if args.print:
        print(text)
        return 0
    SHEET.write_text(text, encoding="utf-8")
    print(f"Wrote docs/cost-sheet.md: {totals['calls']} calls, US${totals['total']:.6f}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
