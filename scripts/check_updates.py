#!/usr/bin/env python3
"""The R23 check: find the source row of every figure in an update (KB-139 stage 5). A plain script, started by hand.

For each update, every figure in its subject and body (request ids, dates, percentages, money, numbers, and figures
written in words) is found by the same code the drafter's own check uses (engine/figures.js), traced to a fact of the
pack the update was drafted from, and that fact's source row is read again now through changedesk.fact_value, the
store's one reader of facts. It passes only when every figure has a fact and every fact's row still holds the value
the draft used. For a requester's update it also works out again how each open item is answered (R25). A close
message from the decide list is checked the same way, against its record's facts (engine/drafter.js, closeFacts).

  python scripts/check_updates.py                       # every draft waiting for approval
  python scripts/check_updates.py --run up-20261125T001500Z
  python scripts/check_updates.py --update U-up-20261125T001500Z-manager
  python scripts/check_updates.py --all --write         # every update; write docs/reports/updates.md

Exit codes: 0 every figure found its row, 1 a figure has no source or its row now differs, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk_db  # noqa: E402
from desk_engine import REPO, Engine, EngineError  # noqa: E402

REPORT = REPO / "docs" / "reports" / "updates.md"
SELECT = ("select u.*, r.title as request_title, r.arrived_at::date::text as arrived_on, r.close_reason from changedesk.updates u "
          "left join changedesk.requests r on r.request_id = u.request_id")


def source_words(src: dict | None) -> str:
    if not src:
        return "no source"
    where = ", ".join(f"{k} = {'null' if v is None else (' or '.join(v) if isinstance(v, list) else v)}" for k, v in (src.get("where") or {}).items())
    table = src["table"] + (f"({src['as_of']})" if src.get("as_of") else "")
    what = src.get("agg", "value")
    col = src.get("column") or ""
    idx = f"[{src['index']}]" if "index" in src else ""
    read = f"{col}{idx}" if what == "value" else (f"{what}({col})" if col else f"{what} of rows")
    return f"`{table}` where {where or 'every row'}: {read}"


def pack_of(u: dict, drafter: Engine) -> dict:
    """The pack the update was drafted from, as far as the figure check needs it: its facts, its items' titles and
    answers (kept with the coverage), and the other titles it holds."""
    facts = u["facts"] or []
    if u["kind"] == "close" and not facts and u.get("request_id"):
        # A close draft from before stage 5 kept no facts: its record's facts are made again from the request row.
        facts = drafter.call("closeFacts", {"request_id": u["request_id"], "title": u["request_title"], "arrived_on": u["arrived_on"]})
    items = [{"request_id": c["request_id"], "title": c.get("title", ""), "answer": c.get("answer"), "facts": c.get("facts", {}),
              "moved": c.get("moved", False), "on_decide_list": c.get("on_decide_list", False)} for c in (u["coverage"] or [])]
    if u["kind"] == "close":
        items = [{"request_id": u["request_id"], "title": u["request_title"] or ""}]
    titles = [f["value"] for f in facts if f.get("kind") == "text" and (f.get("source") or {}).get("column") == "title" and f.get("value")]
    return {"audience": u["audience"], "facts": facts, "items": items, "titles": titles}


def now_value(conn, src: dict) -> tuple[str | None, str | None]:
    try:
        with conn.transaction():
            return conn.execute("select changedesk.fact_value(%s::jsonb) as v", (json.dumps(src),)).fetchone()["v"], None
    except Exception as e:  # noqa: BLE001 - a row that cannot be read is a finding, not a crash
        return None, str(e).splitlines()[0]


def check_one(conn, u: dict, figures_eng: Engine, updates_eng: Engine, drafter: Engine) -> dict:
    pack = pack_of(u, drafter)
    text = f"{u['subject']}\n{u['body']}"
    traced = figures_eng.call("traceFigures", text, pack)
    facts = {f["id"]: f for f in pack["facts"]}
    rows, fails = [], []
    for fig in traced["figures"]:
        if fig["kind"] == "number_word":
            rows.append({"figure": fig["text"], "fact": "", "source": "a figure written in words", "drafted": "", "now": "", "ok": False})
            fails.append(f'"{fig["text"]}" is written in words')
            continue
        fact = facts.get(fig["fact_id"])
        if fact is None:
            rows.append({"figure": fig["text"], "fact": "", "source": "no fact in the pack has this value", "drafted": "", "now": "", "ok": False})
            fails.append(f'"{fig["text"]}" has no source')
            continue
        now, err = now_value(conn, fact["source"])
        ok = err is None and now == fact["value"]
        rows.append({"figure": fig["text"], "fact": fact["says"], "source": source_words(fact["source"]), "drafted": fact["value"],
                     "now": err or now, "ok": ok})
        if not ok:
            fails.append(f'"{fig["text"]}": its row now gives {err or now}, the draft used {fact["value"]}')
    cover = updates_eng.call("coverage", pack, u["body"]) if u["audience"] == "requester" and u["kind"] == "status" else []
    for c in cover:
        if not c["ok"]:
            fails.append(f"{c['request_id']} is not answered: {', '.join(c['missing'])}")
    return {"update": u, "rows": rows, "coverage": cover, "fails": fails}


def report(results: list[dict], title: str) -> str:
    figs = sum(len(r["rows"]) for r in results)
    bad = sum(1 for r in results if r["fails"])
    lines = [f"# The updates and the source of every figure: {title}", "",
             "Made by `scripts/check_updates.py` (R23). Every figure in each update's subject and body is found by the code the drafter's own "
             "check uses (`engine/figures.js`), traced to a fact of the pack the update was drafted from, and the fact's source row is read "
             "again through `changedesk.fact_value`. For a requester, it also works out how each open item is answered (R25). "
             "Nothing here is sent to anyone: a person approves each update on the n8n approval form, and an approved update goes to the "
             "outbox table only. Every ticket is made up.", "",
             f"**{len(results)} updates, {figs} figures: {'every figure found its row' if not bad else f'{bad} updates have a figure with no source or a row that changed'}.**",
             ""]
    lines += ["| Update | For | Status | Figures | Check |", "|---|---|---|---|---|"]
    for r in results:
        u = r["update"]
        lines.append(f"| `{u['update_id']}` | {u['to_role'] or u['audience']} ({u['audience']}, {u['kind']}) | {u['status']} | {len(r['rows'])} | "
                     f"{'every figure traced' if not r['fails'] else 'FAILS'} |")
    for r in results:
        u = r["update"]
        lines += ["", f"## `{u['update_id']}`", "",
                  f"For **{u['to_role'] or u['audience']}** ({u['audience']}, {u['kind']}). Drafted by {u['drafted_by']} from forecast run "
                  f"`{u['forecast_run_id'] or 'none (a close message)'}`. Status: **{u['status']}**"
                  + (f", by {u['approved_by']}" if u.get("approved_by") else "") + ".", "",
                  f"> **{u['subject']}**", ">"]
        lines += [f"> {line}" if line.strip() else ">" for line in u["body"].splitlines()]
        if u["draft_problems"]:
            lines += ["", f"The drafter's code check found problems, so it can only be rejected: {u['draft_problems']}."]
        lines += ["", "| Figure | Fact | Source row | Drafted | Now | |", "|---|---|---|---|---|---|"]
        for x in r["rows"]:
            lines.append(f"| {x['figure']} | {x['fact']} | {x['source']} | {x['drafted']} | {x['now']} | {'ok' if x['ok'] else '**no**'} |")
        if r["coverage"]:
            lines += ["", "Every open item answered (R25):", "", "| Item | Answer | Answered |", "|---|---|---|"]
            for c in r["coverage"]:
                lines.append(f"| {c['request_id']} {c.get('title', '')} | {c['answer'].replace('_', ' ')}{', moved' if c.get('moved') else ''}"
                             f"{', on the decide list' if c.get('on_decide_list') else ''} | {'yes' if c['ok'] else 'no: ' + ', '.join(c['missing'])} |")
        if r["fails"]:
            lines += ["", "**Fails:** " + "; ".join(r["fails"]) + "."]
    lines += ["", "Every request is made up. The figures show direction, not size.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", help="every update one drafting run made (its run id)")
    ap.add_argument("--update", help="one update id")
    ap.add_argument("--all", action="store_true", help="every update in the store")
    ap.add_argument("--write", action="store_true", help="write docs/reports/updates.md")
    args = ap.parse_args(argv)
    try:
        figures_eng, updates_eng, drafter = Engine("figures"), Engine("updates"), Engine("drafter")
        with desk_db.connect(autocommit=False) as conn:
            if args.update:
                rows, title = desk_db.rows(conn, SELECT + " where u.update_id = %s", (args.update,)), args.update
            elif args.run:
                rows, title = desk_db.rows(conn, SELECT + " where u.run_id = %s order by u.audience desc, u.update_id", (args.run,)), f"run {args.run}"
            elif args.all:
                rows, title = desk_db.rows(conn, SELECT + " order by u.drafted_at, u.update_id"), "every update"
            else:
                rows, title = desk_db.rows(conn, SELECT + " where u.status = 'draft' order by u.drafted_at, u.update_id"), "the drafts waiting for approval"
            results = [check_one(conn, u, figures_eng, updates_eng, drafter) for u in rows]
            conn.rollback()
    except (EngineError, LookupError, OSError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    if not results:
        print(f"No updates to check ({title}).")
        return 0
    for r in results:
        u = r["update"]
        print(f"{'PASS' if not r['fails'] else 'FAIL'} {u['update_id']} ({u['audience']}, {u['status']}): {len(r['rows'])} figures"
              + ("" if not r["fails"] else ": " + "; ".join(r["fails"])))
    if args.write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(report(results, title), encoding="utf-8")
        print(f"Wrote {REPORT.relative_to(REPO)}.")
    return 1 if any(r["fails"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
