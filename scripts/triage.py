#!/usr/bin/env python3
"""Run the AI triage step on the inbox by hand: every request still New gets a lane, with a reason (stage 1).

The same engine n8n runs (engine/triage.js, through engine/cli.js): the playbook, the request with the
text inside a data block, the guard rules, the code screen, the fixed output shape (the spec's triage shape),
the lane rule, the stamp. One Claude call per request, Haiku 5.5 first. Results go to the store through
changedesk.log_triage as the app's own login: standard and small items with a sure answer are
Triaged; urgent, fixed-date, low-confidence and flagged items, and every split, wait for a person on
the lane confirmation form (n8n). Nothing is sent to anyone.

  python scripts/triage.py                       # every request in the inbox
  python scripts/triage.py --only CD-0157,CD-1001
  python scripts/triage.py --dry-run             # build the requests, call nothing, write nothing

The Claude key is read from .env (ANTHROPIC_API_KEY) and never printed. Nothing is scheduled.
Exit codes: 0 done, 1 a call or the write failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk_db  # noqa: E402
from desk_engine import MODEL, PLAYBOOK, REPO, Engine, EngineError  # noqa: E402


def call_claude(client, request: dict) -> tuple[dict, int]:
    """One Messages call. Returns the result in the engine's HTTP shape, and the time taken in ms.
    Copied from the GTM pipeline (scripts/route_leads.py)."""
    import anthropic

    started = time.perf_counter()
    try:
        message = client.messages.create(**request)
        http = {"statusCode": 200, "headers": {"request-id": message._request_id}, "body": message.to_dict()}
    except anthropic.APIStatusError as e:
        http = {"error": {"message": e.message, "status": e.status_code}}
    except anthropic.APIConnectionError as e:
        http = {"error": {"message": f"connection error: {type(e).__name__}"}}
    return http, round((time.perf_counter() - started) * 1000)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def triage_all(eng: Engine, client, pb: dict, settings: dict, goals: list[dict], inbox: list[dict], run_id: str,
               model: str, today: str, source: str = "python") -> tuple[list[dict], list[dict], list[dict]]:
    calls, proposals, handoffs = [], [], []
    for req in inbox:
        request = eng.call("buildTriageRequest", pb, req, goals, model, today)
        http, ms = call_claude(client, request)
        out = eng.call("checkTriage", pb, req, http, {"run_id": run_id, "source": source, "model": model, "settings": settings,
                                                      "goals": goals, "now": now_iso(), "latency_ms": ms})
        calls.append(out["call"])
        proposals.append(out["proposal"])
        h = eng.call("triageHandoff", out["proposal"])
        if h:
            handoffs.append(h)
    return calls, proposals, handoffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="comma-separated request ids")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry-run", action="store_true", help="build the requests; call nothing; write nothing")
    args = ap.parse_args(argv)
    load_dotenv(REPO / ".env")
    try:
        eng = Engine("triage")
        pb = eng.call("parseTriagePlaybook", PLAYBOOK.read_text(encoding="utf-8"))
        with desk_db.connect() as conn:
            settings = eng.call("settingsFromRows", desk_db.settings(conn))
            goals = desk_db.goals(conn)
            inbox = desk_db.rows(conn, "select * from changedesk.inbox order by arrived_at, request_id")
        if args.only:
            wanted = {x.strip() for x in args.only.split(",") if x.strip()}
            inbox = [r for r in inbox if r["request_id"] in wanted]
        if not inbox:
            print("The inbox is empty: nothing to triage.")
            return 0
        today = date.today().isoformat()
        if args.dry_run:
            req = eng.call("buildTriageRequest", pb, inbox[0], goals, args.model, today)
            print(f"Dry run: {len(inbox)} requests would be triaged with {args.model}, playbook {pb['name']} {pb['version']}.")
            print(f"System prompt {len(req['system'])} characters; first request {inbox[0]['request_id']}, "
                  f"message {len(req['messages'][0]['content'])} characters. Nothing was called or written.")
            return 0
        import anthropic
        import os

        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            print("CANNOT RUN ANTHROPIC_API_KEY is not in .env (see docs/build-guide.md, step 1)")
            return 2
        client = anthropic.Anthropic(max_retries=3)
        run_id = "py-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        calls, proposals, handoffs = triage_all(eng, client, pb, settings, goals, inbox, run_id, args.model, today)
        with desk_db.connect() as conn:
            logged = desk_db.call_function(conn, "select changedesk.log_triage(%s::jsonb, %s::jsonb, %s::jsonb) as n",
                                           calls, proposals, handoffs)["n"]
            summary = desk_db.rows(conn, "select * from changedesk.run_summary where run_id = %s", (run_id,))
    except (EngineError, LookupError, OSError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    print(f"Run {run_id}: {len(proposals)} requests, {logged} triaged into lanes, model {args.model}, playbook {pb['name']} {pb['version']}.")
    for p in proposals:
        if not p["output_valid"]:
            print(f"  {p['request_id']}: NO USABLE ANSWER, stays New ({p['confirmation_detail']})")
            continue
        waits = p["needs_confirmation"] or bool(p["split"])
        print(f"  {p['request_id']}: {p['lane']:<10} {p['size_hours']:>5} h  conf {p['confidence']:.2f}  "
              f"{'WAITS: ' + ', '.join(p['confirmation_reasons'] + (['split'] if p['split'] else [])) if waits else 'set'}"
              f"{'  flags ' + '|'.join(p['flags']) if p['flags'] else ''}")
        print(f"      {p['reason']}")
    if summary:
        s = summary[0]
        print(f"Cost: US${s['total_cost_usd']:.6f} for {s['calls']} calls, US${s['cost_per_call_usd']:.6f} a call "
              f"({s['input_tokens']} tokens in, {s['output_tokens']} out). Failed calls: {s['failed']}.")
    waiting = sum(1 for p in proposals if p["output_valid"] and (p["needs_confirmation"] or p["split"]))
    print(f"{waiting} wait for a person: the lane confirmation form (n8n, /form/changedesk-confirm-lanes).")
    return 0 if all(p["output_valid"] for p in proposals) else 1


if __name__ == "__main__":
    sys.exit(main())
