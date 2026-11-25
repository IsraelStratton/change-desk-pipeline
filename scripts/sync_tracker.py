#!/usr/bin/env python3
"""Fill the Notion tracker board from the store, by hand (the spec's stage 3): one row for each request, upserted by
"Request ID". Started by hand; nothing is scheduled.

The board ("Change Desk — tracker (made-up tickets)") is the reviewer's: it was built in Notion with its properties,
options and views. This script never changes it. It first reads the board's properties and checks every one it writes
is there, with the right type and every option it needs (Notion would otherwise add a missing select option to the
board). If anything is missing or wrong it says what and writes nothing. It never deletes a row: a row on the board
whose Request ID is not in the store is reported and left alone.

What it writes comes from the view changedesk.tracker, read as the app's own login. Roles only, never names: "Asked by"
is the requester's role, and "Lane confirmed by" is a role worked out from who confirmed it (a person, the made-up
history, or no one yet); a reviewer's own label is never copied to the board. Contact details are never written.

The Notion key and the board's ids live only in .env (NOTION_CHANGEDESK_TOKEN, NOTION_CHANGEDESK_DB,
NOTION_CHANGEDESK_DATA_SOURCE) and are never printed. The key's own connection reaches this one board only.
Notion API version 2026-03-11, with the data sources it brought in (docs read 25/11/2026): the board's rows are
pages whose parent is the data source; they are read with POST /v1/data_sources/{id}/query.

  python scripts/sync_tracker.py              # check the board, then create and update rows
  python scripts/sync_tracker.py --check      # check the board's properties only
  python scripts/sync_tracker.py --dry-run    # check, read both sides, say what would change; write nothing

Exit codes: 0 done (or in step), 1 the board is not as expected or a write failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[1]
API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
ENV_KEYS = ("NOTION_CHANGEDESK_TOKEN", "NOTION_CHANGEDESK_DB", "NOTION_CHANGEDESK_DATA_SOURCE")
MAX_TEXT = 2000

# The board's properties, exactly as the reviewer built them, and the Notion type each must be.
PROPERTIES = {
    "Request": "title", "Request ID": "rich_text", "Lane": "select", "Status": "select", "Type": "select",
    "Size (hours)": "number", "Score": "number", "Age (days)": "number", "Past age limit": "checkbox", "Due date": "date",
    "What breaks on the date": "rich_text", "Harm growing now": "rich_text", "Goal": "rich_text", "No goal": "checkbox",
    "Playbook": "rich_text", "Asked by (role)": "rich_text", "Confidence": "number", "Lane confirmed by": "rich_text",
    "Planned week": "rich_text", "Forecast": "rich_text", "Reason": "rich_text",
}
LANE = {"urgent": "Urgent", "fixed_date": "Fixed date", "standard": "Standard", "small": "Small and quick"}
STATUS = {"New": "New", "Triaged": "Triaged", "Planned": "Planned", "In progress": "In progress", "Done": "Done",
          "Merged": "Merged", "Closed": "Closed with a reason", "Split": "Split"}
TYPE = {"bug": "Bug", "enhancement": "Enhancement"}
OPTIONS = {"Lane": set(LANE.values()), "Status": set(STATUS.values()), "Type": set(TYPE.values())}
OPEN = ("Triaged", "Planned", "In progress")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")
PHONE_RE = re.compile(r"\+?\d[\d ().-]{7,}\d")

TRACKER_SQL = "select * from changedesk.tracker order by request_id"


class NotionError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"Notion API {status} {code}: {message}")
        self.status, self.code = status, code


class Notion:
    """A small client for the few calls this script makes. Keeps under Notion's limit of about three requests a
    second, waits as asked on 429, and retries a read on a passing server error. A write is not repeated blindly."""

    def __init__(self, token: str, session=None, pause: float = 0.35):
        self.token = token
        self.s = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"}
        self.pause = pause
        self.last = 0.0

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        read = method == "GET" or path.endswith("/query")
        for attempt in range(6):
            wait = self.pause - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            resp = self.s.request(method, f"{API}{path}", headers=self.headers, json=body, timeout=30)
            if resp.status_code < 400:
                return resp.json() if resp.content else {}
            retry = resp.status_code == 429 or resp.status_code in (500, 502, 504, 529) or (resp.status_code == 503 and read)
            if retry and attempt < 5:
                time.sleep(float(resp.headers.get("Retry-After") or 2 ** attempt))
                continue
            try:
                err = resp.json()
            except ValueError:
                err = {}
            msg = str(err.get("message") or resp.text[:200]).replace(self.token, "<hidden>")
            raise NotionError(resp.status_code, str(err.get("code") or ""), msg)
        raise NotionError(0, "gave_up", "too many retries")

    def data_source(self, ds: str) -> dict:
        return self.call("GET", f"/data_sources/{ds}")

    def database(self, db: str) -> dict:
        return self.call("GET", f"/databases/{db}")

    def pages(self, ds: str) -> list[dict]:
        out, cursor = [], None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            page = self.call("POST", f"/data_sources/{ds}/query", body)
            out += [p for p in page.get("results", []) if p.get("object") == "page"]
            if not page.get("has_more"):
                return out
            cursor = page.get("next_cursor")

    def create(self, ds: str, properties: dict) -> dict:
        return self.call("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": ds}, "properties": properties})

    def update(self, page_id: str, properties: dict) -> dict:
        return self.call("PATCH", f"/pages/{page_id}", {"properties": properties})


# ---------------------------------------------------------------- the board's properties

def board_problems(ds: dict) -> list[str]:
    """What is missing or wrong on the board for this script to write, without changing it."""
    props = ds.get("properties") or {}
    problems = []
    for name, kind in PROPERTIES.items():
        p = props.get(name)
        if p is None:
            problems.append(f"property '{name}' is missing (a {kind} property is needed)")
            continue
        if p.get("type") != kind:
            problems.append(f"property '{name}' is a {p.get('type')}, not a {kind}")
            continue
        if name in OPTIONS:
            have = {o.get("name") for o in (p.get(kind) or {}).get("options", [])}
            for o in sorted(OPTIONS[name] - have):
                problems.append(f"property '{name}' has no option '{o}'")
    return problems


# ---------------------------------------------------------------- what each row says

def clean(s) -> str:
    """Plain text for the board: contact details withheld, at most Notion's 2000 characters."""
    t = " ".join(str(s or "").split())
    t = EMAIL_RE.sub("[contact details withheld]", t)
    t = PHONE_RE.sub(lambda m: "[contact details withheld]" if len(re.sub(r"\D", "", m.group(0))) >= 8 else m.group(0), t)
    return t if len(t) <= MAX_TEXT else t[:MAX_TEXT - 1] + "…"


def confirmed_by(row: dict) -> str:
    """A role, never a label: the store keeps who confirmed it, with the stamp."""
    who = str(row.get("lane_confirmed_by") or "")
    if not who:
        if row.get("awaiting_confirmation"):
            return "Waits for a person"
        return "" if row.get("status") == "New" else "Not needed: the lane rule set it"
    if who == "history (made-up)":
        return "Made-up history"
    if "(delegated)" in who:
        return "Desk reviewer (delegated test run)"
    return "Desk reviewer"


def dmy(x) -> str:
    return date.fromisoformat(str(x)[:10]).strftime("%d/%m/%Y")


def forecast_text(row: dict) -> str:
    if row.get("status") not in OPEN or not row.get("forecast_kind"):
        return ""
    kind = row["forecast_kind"]
    if kind == "date_range" and row.get("p95"):
        return f"50% by {dmy(row['p50'])} · 85% by {dmy(row['p85'])} · 95% by {dmy(row['p95'])}"
    if kind == "chance_of_date" and row.get("chance") is not None and row.get("latest_safe_start"):
        due = row.get("due_date")
        if due and row.get("chance") == 0 and "passed" in str(row.get("forecast_note") or ""):
            return f"The date {dmy(due)} has passed: it cannot be met"
        return f"{float(row['chance']):.0%} chance of {dmy(due)} · latest safe start {dmy(row['latest_safe_start'])}"
    if kind == "service_level" and row.get("service_level_days") is not None:
        return f"Service level: 85% of small items done within {float(row['service_level_days']):g} days"
    return clean(row.get("forecast_note"))


def wanted(row: dict) -> dict:
    """The board's values for one request, as plain Python values (None: empty)."""
    status = row["status"]
    goal = f"{row['goal_id']} {row['goal']}" if row.get("goal_id") else ""
    return {
        "Request": clean(row["title"]), "Request ID": row["request_id"],
        "Lane": LANE.get(row.get("lane") or ""), "Status": STATUS[status], "Type": TYPE.get(row.get("type") or ""),
        "Size (hours)": float(row["size_hours"]) if row.get("size_hours") is not None else None,
        "Score": float(row["rank_points"]) if row.get("rank_points") is not None else None,
        "Age (days)": float(row["age_days"]) if row.get("age_days") is not None else None,
        "Past age limit": bool(row.get("past_age_limit")),
        "Due date": str(row["due_date"])[:10] if row.get("due_date") else None,
        "What breaks on the date": clean(row.get("due_breaks")), "Harm growing now": clean(row.get("urgent_harm")),
        "Goal": clean(goal), "No goal": bool(row.get("no_goal")),
        "Playbook": "" if not row.get("playbook") else ("none fits" if row["playbook"] == "none" else row["playbook"]),
        "Asked by (role)": clean(row.get("requester_role")),
        "Confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
        "Lane confirmed by": confirmed_by(row),
        "Planned week": f"Week of {dmy(row['planned_week'])}" if row.get("planned_week") and status in OPEN else "",
        "Forecast": forecast_text(row), "Reason": clean(row.get("triage_reason")),
    }


def to_notion(name: str, value) -> dict:
    kind = PROPERTIES[name]
    if kind in ("title", "rich_text"):
        return {kind: [{"type": "text", "text": {"content": value}}] if value else []}
    if kind == "number":
        return {"number": value}
    if kind == "checkbox":
        return {"checkbox": bool(value)}
    if kind == "select":
        return {"select": {"name": value} if value else None}
    if kind == "date":
        return {"date": {"start": value} if value else None}
    raise ValueError(kind)


def from_notion(prop: dict | None):
    """A page's property as the same plain value wanted() gives."""
    if not prop:
        return None
    kind = prop.get("type")
    if kind in ("title", "rich_text"):
        return "".join(t.get("plain_text") or (t.get("text") or {}).get("content", "") for t in prop.get(kind) or [])
    if kind == "number":
        return prop.get("number")
    if kind == "checkbox":
        return bool(prop.get("checkbox"))
    if kind == "select":
        return (prop.get("select") or {}).get("name")
    if kind == "date":
        return ((prop.get("date") or {}).get("start") or "")[:10] or None
    return None


def same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(float(a) - float(b)) < 1e-6
    return (a or None) == (b or None) if not isinstance(a, bool) else a == bool(b)


def changes(want: dict, page: dict) -> dict:
    props = page.get("properties") or {}
    return {k: v for k, v in want.items() if not same(v, from_notion(props.get(k)))}


def plan_sync(rows: list[dict], pages: list[dict]) -> dict:
    """What a sync would do: create, update (with only the changed properties), leave, and report."""
    by_id: dict[str, list[dict]] = {}
    for p in sorted(pages, key=lambda p: p.get("created_time") or ""):
        rid = from_notion((p.get("properties") or {}).get("Request ID"))
        if rid:
            by_id.setdefault(rid, []).append(p)
    out = {"create": [], "update": [], "same": 0, "duplicates": sorted(r for r, ps in by_id.items() if len(ps) > 1),
           "not_in_store": sorted(set(by_id) - {r["request_id"] for r in rows}),
           "no_request_id": sum(1 for p in pages if not from_notion((p.get("properties") or {}).get("Request ID")))}
    for r in rows:
        want = wanted(r)
        found = by_id.get(r["request_id"])
        if not found:
            out["create"].append(want)
            continue
        diff = changes(want, found[0])
        if diff:
            out["update"].append((found[0]["id"], r["request_id"], diff))
        else:
            out["same"] += 1
    return out


def sync(client: Notion, db: str, ds: str, rows: list[dict], mode: str = "sync") -> tuple[int, list[str]]:
    """Returns (exit code, lines to print). mode: check, dry-run or sync."""
    lines = []
    owner = client.database(db)
    if ds not in {x.get("id") for x in owner.get("data_sources") or []}:
        return 1, ["FAIL the data source in .env is not the tracker database's own: nothing written"]
    problems = board_problems(client.data_source(ds))
    if problems:
        return 1, ["FAIL the board is not as this script expects, so nothing was written (the reviewer owns the board):"] + [f"  - {p}" for p in problems]
    lines.append(f"The board has all {len(PROPERTIES)} properties this script writes, with the right types and options.")
    if mode == "check":
        return 0, lines
    pages = client.pages(ds)
    plan = plan_sync(rows, pages)
    lines.append(f"Store: {len(rows)} requests. Board: {len(pages)} rows. To create {len(plan['create'])}, to update {len(plan['update'])}, "
                 f"already the same {plan['same']}.")
    if plan["duplicates"]:
        lines.append(f"  {len(plan['duplicates'])} Request IDs have more than one row on the board ({', '.join(plan['duplicates'])}): "
                     "the oldest row is updated, the others are left for the reviewer.")
    if plan["not_in_store"] or plan["no_request_id"]:
        lines.append(f"  Left alone: {len(plan['not_in_store'])} rows whose Request ID is not in the store, {plan['no_request_id']} with no Request ID.")
    if mode == "dry-run":
        changed = sorted({k for _, _, diff in plan["update"] for k in diff})
        lines.append("Dry run: nothing written." + (f" Properties that would change: {', '.join(changed)}." if changed else ""))
        return 0, lines
    created = updated = failed = 0
    for want in plan["create"]:
        try:
            client.create(ds, {k: to_notion(k, v) for k, v in want.items()})
            created += 1
        except NotionError as e:
            failed += 1
            lines.append(f"  could not create {want['Request ID']}: {e}")
    for page_id, rid, diff in plan["update"]:
        try:
            client.update(page_id, {k: to_notion(k, v) for k, v in diff.items()})
            updated += 1
        except NotionError as e:
            failed += 1
            lines.append(f"  could not update {rid}: {e}")
    lines.append(f"Created {created}, updated {updated}, left {plan['same']} as they were; {failed} failed. Nothing deleted.")
    return (1 if failed else 0), lines


def main(argv: list[str] | None = None, env: dict | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    env = dotenv_values(REPO / ".env") if env is None else env
    token, db, ds = ((env.get(k) or "").strip() for k in ENV_KEYS)
    missing = [k for k, v in zip(ENV_KEYS, (token, db, ds)) if not v]
    if missing:
        print(f"CANNOT RUN {', '.join(missing)} not in .env (the owner pastes the key; docs/build-guide.md, part E)")
        return 2
    mode = "check" if args.check else "dry-run" if args.dry_run else "sync"
    try:
        rows = []
        if mode != "check":
            import desk_db

            with desk_db.connect() as conn:
                rows = desk_db.rows(conn, TRACKER_SQL)
        code, lines = sync(Notion(token), db, ds, rows, mode)
    except NotionError as e:
        print(f"CANNOT RUN {str(e).replace(token, '<hidden>').replace(db, '<board>').replace(ds, '<board>')}")
        return 2
    except (LookupError, OSError, requests.RequestException) as e:
        print(f"CANNOT RUN {type(e).__name__}: {str(e).replace(token, '<hidden>').replace(db, '<board>').replace(ds, '<board>')}")
        return 2
    for line in lines:
        print(line.replace(token, "<hidden>").replace(db, "<board>").replace(ds, "<board>"))
    return code


if __name__ == "__main__":
    sys.exit(main())
