#!/usr/bin/env python3
"""Find what made the message drafter flag a clean close: run it on one closed item's record, as the store holds it
and as the decide form now makes it, a few times each, and show the flags. Started by hand; nothing is scheduled.

Written 25/11/2026 for test run n8n-8909. The close draft U-n8n-8909-CD-0029 came back flagged possible_injection and
personal_data, though the request and the draft read clean. Its record's reason_for_closing held the reviewer's note
for the whole form, which named a person and two other items. The fix keeps that note on the decision row; this probe
shows whether the reason was the cause, by changing only that one field.

  python scripts/drafter_probe.py                       # CD-0029, 3 runs of each record
  python scripts/drafter_probe.py --request CD-0029 --runs 5

Each call is logged in changedesk.run_log (step drafter) so its cost counts; no draft is stored and nothing is sent.
The Claude key is read from .env (ANTHROPIC_API_KEY) and never printed.
Exit codes: 0 done, 2 could not run.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk_db  # noqa: E402
from desk_engine import MODEL, REPO, Engine, EngineError  # noqa: E402
from triage import call_claude, now_iso  # noqa: E402

FIXED_REASONS = {"no longer needed", "overtaken by another change", "too little value for the work it needs", "the requester found another way"}


def own_reason(stored: str) -> str:
    """The reason the decide form now gives: the fixed choice alone, as it starts the stored text."""
    for r in FIXED_REASONS:
        if stored.lower().startswith(r):
            return r[0].upper() + r[1:] + "."
    raise LookupError("the stored close reason does not start with one of the decide form's reasons")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--request", default="CD-0029")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args(argv)
    load_dotenv(REPO / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("CANNOT RUN ANTHROPIC_API_KEY is not in .env (docs/build-guide.md, step 1)")
        return 2
    try:
        eng = Engine("drafter")
        with desk_db.connect() as conn:
            found = desk_db.rows(conn, "select request_id, title, requester_role, arrived_at::date as arrived_on, close_reason "
                                       "from changedesk.requests where request_id = %s and status = 'Closed'", (args.request,))
        if not found:
            print(f"CANNOT RUN {args.request} is not a closed request")
            return 2
        item = found[0]
        records = {"as stored": dict(item, reason=item["close_reason"]), "own reason": dict(item, reason=own_reason(item["close_reason"]))}
        import anthropic

        client = anthropic.Anthropic(max_retries=3)
        run_id = "py-probe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        calls, seen, texts = [], {k: [] for k in records}, []
        for label, record in records.items():
            for n in range(1, args.runs + 1):
                http, ms = call_claude(client, eng.call("buildCloseDraftRequest", record, MODEL))
                out = eng.call("checkCloseDraft", record, http, {"run_id": run_id, "source": "python", "model": MODEL, "now": now_iso(), "latency_ms": ms})
                out["call"]["call_id"] = f"{out['call']['call_id']}-{'s' if label == 'as stored' else 'o'}{n}"
                calls.append(out["call"])
                seen[label].append(out["draft"]["draft_problems"] if out["draft"] else f"no draft ({out['call']['error']})")
                if out["draft"] and out["draft"]["draft_problems"]:
                    texts.append((label, n, out["draft"]["draft_problems"], out["draft"]["body"]))
        with desk_db.connect() as conn:
            desk_db.call_function(conn, "select changedesk.log_drafts(%s::jsonb, %s::jsonb, %s::jsonb)", calls, [], [])
            cost = desk_db.rows(conn, "select total_cost_usd from changedesk.run_summary where run_id = %s", (run_id,))
    except (EngineError, LookupError, OSError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    print(f"Run {run_id}: {args.request}, {args.runs} drafts of each record, model {MODEL}. Only reason_for_closing differs.")
    for label, problems in seen.items():
        flagged = sum("the drafter flagged" in p for p in problems)
        print(f"  {label:<10} reason_for_closing = {records[label]['reason']!r}")
        print(f"             model flagged {flagged} of {len(problems)}: " + " | ".join(p or "clean" for p in problems))
    for label, n, problems, body in texts:
        print(f"  draft {label} #{n} ({problems}):\n    " + body.replace("\n", "\n    "))
    if cost:
        print(f"Cost: US${cost[0]['total_cost_usd']:.6f} for {len(calls)} calls, in the run log. No draft was stored; nothing was sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
