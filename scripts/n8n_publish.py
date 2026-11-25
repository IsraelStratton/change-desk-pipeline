#!/usr/bin/env python3
"""Put the Change Desk's workflows into the local n8n through its API, check the live copies, and switch them on or off.

Copied from the GTM pipeline (scripts/n8n_publish_routing.py) and shaped for this build's six workflows.

  python scripts/n8n_publish.py publish           # create or update all six; they stay OFF
  python scripts/n8n_publish.py check             # compare the live copies with the files; change nothing
  python scripts/n8n_publish.py on                # switch all six on, for a test session (forms answer)
  python scripts/n8n_publish.py off               # switch all six off again
  python scripts/n8n_publish.py on --target intake

What publish does, so nothing is clicked by hand and nothing drifts:
  1. builds each workflow with scripts/build_n8n.py, exactly as the committed file;
  2. finds each credential the file names in n8n, by name and type, and fills in its ID. It never reads
     or sends a secret: n8n keeps those. A credential that does not exist yet stops it (docs/build-guide.md);
  3. creates the workflow, or updates the one with the same name, and leaves it off. The file ships the
     form trigger without a webhook ID (n8n's editor import would copy a new ID over the Form Path), so
     the script keeps the live trigger's ID, or gives a new trigger a fresh one.
check reads each live workflow and reports any node, setting or connection that differs from the file
(positions and IDs aside). n8n leaves out a parameter that equals the node's default, so a key the file
sets and n8n does not hold is taken as that default; every value n8n does hold must equal the file's, and
every Code node's JavaScript must match in full. n8n 2.x runs a workflow's published version, not its
saved draft, so check also reads the published version when there is one: an active workflow's must be
its latest saved version and match the file, and an inactive one must have none (Publish and Unpublish
in the n8n screens save a named version; that alone is no difference). The reviewer switches the workflows
on and off in the n8n screens and cannot run this script: a workflow switched on and off there, and left off,
is in step (tests/test_n8n_publish.py walks all six through that cycle). One left on is reported with a note.

No workflow has a schedule. A form only answers while its workflow is on; turn them off after a session.
The n8n API key is read from .env (N8N_API_KEY) and never printed.
Exit codes: 0 done (or in step), 1 a live copy differs or a check failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import uuid
from pathlib import Path

import requests
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_n8n as build  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
IGNORED_NODE_KEYS = {"id", "position", "webhookId"}


class N8n:
    def __init__(self, base: str, key: str):
        self.base = base.rstrip("/")
        self.headers = {"X-N8N-API-KEY": key, "accept": "application/json"}

    def call(self, method: str, path: str, body: dict | None = None):
        resp = requests.request(method, f"{self.base}/api/v1{path}", headers=self.headers, json=body, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"n8n API {method} {path.split('?')[0]}: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json() if resp.content else {}

    def all(self, path: str) -> list[dict]:
        items, cursor = [], None
        while True:
            page = self.call("GET", f"{path}?limit=100" + (f"&cursor={cursor}" if cursor else ""))
            items += page.get("data", [])
            cursor = page.get("nextCursor")
            if not cursor:
                return items


def with_credential_ids(wf: dict, credentials: list[dict]) -> dict:
    """Fill each node's credential ID from n8n, matched by name and type."""
    by_key = {(c["type"], c["name"]): c["id"] for c in credentials}
    out = copy.deepcopy(wf)
    missing = []
    for node in out["nodes"]:
        for cred_type, cred in (node.get("credentials") or {}).items():
            cid = by_key.get((cred_type, cred["name"]))
            if cid is None:
                missing.append(f"'{cred['name']}' ({cred_type}), used by {node['name']}")
            cred["id"] = cid
    if missing:
        raise LookupError("these n8n credentials do not exist yet (docs/build-guide.md, part B): " + "; ".join(sorted(set(missing))))
    return out


def comparable(wf: dict) -> dict:
    nodes = {}
    for n in wf["nodes"]:
        n = {k: v for k, v in n.items() if k not in IGNORED_NODE_KEYS}
        for cred in (n.get("credentials") or {}).values():
            cred.pop("id", None)
        nodes[n["name"]] = n
    return {"name": wf["name"], "nodes": nodes, "connections": wf["connections"],
            "executionOrder": (wf.get("settings") or {}).get("executionOrder")}


def matches(live, file) -> bool:
    """live as n8n holds it, file as built. n8n drops parameters that equal their default."""
    if isinstance(live, dict) and isinstance(file, dict):
        return all(k in file and matches(v, file[k]) for k, v in live.items())
    if isinstance(live, list) and isinstance(file, list):
        return len(live) == len(file) and all(matches(x, y) for x, y in zip(live, file))
    return live == file


def differences(live: dict, wanted: dict) -> list[str]:
    a, b = comparable(live), comparable(wanted)
    out = []
    if a["name"] != b["name"]:
        out.append("the workflow name")
    for name in sorted(set(a["nodes"]) | set(b["nodes"])):
        if name not in a["nodes"]:
            out.append(f"node {name}: missing in n8n")
        elif name not in b["nodes"]:
            out.append(f"node {name}: in n8n but not in the file")
        else:
            x, y = a["nodes"][name], b["nodes"][name]
            keys = sorted(k for k in set(x) | set(y) if not matches(x.get(k), y.get(k)))
            code = (x.get("parameters") or {}).get("jsCode") != (y.get("parameters") or {}).get("jsCode")
            if keys or code:
                out.append(f"node {name}: {', '.join(keys) or 'jsCode'} differ")
    if a["connections"] != b["connections"]:
        out.append("the connections")
    if a["executionOrder"] != b["executionOrder"]:
        out.append("the execution order setting")
    return out


def as_workflow(live: dict, version: dict) -> dict:
    """A saved version from n8n's workflow history, in the shape differences() reads."""
    return {"name": live["name"], "nodes": version["nodes"], "connections": version["connections"], "settings": live.get("settings")}


def published_problems(live: dict, published: dict | None, wanted: dict) -> list[str]:
    """n8n 2.x runs the published version, not the saved draft. Publish and Unpublish in the n8n screens
    also save a named version. So: an active workflow must have a published version, that version must be
    the latest saved one, and it must match the file. An inactive one must have none."""
    active_id = live.get("activeVersionId")
    if not live.get("active"):
        return [f"it is off but still has a published version ({active_id})"] if active_id else []
    if not active_id or published is None:
        return ["it is on but n8n reports no published version"]
    out = []
    if active_id != live.get("versionId"):
        out.append("the published version is not the latest saved version")
    out += [f"published version: {d}" for d in differences(as_workflow(live, published), wanted)]
    return out


def request_body(wanted: dict, live: dict | None, trigger: str) -> dict:
    """What is sent to n8n: the file's workflow, with the form trigger's webhook ID kept from the live copy
    or, for a trigger that has none, a new one (n8n registers no webhook without it)."""
    body = copy.deepcopy({k: wanted[k] for k in ("name", "nodes", "connections", "settings")})
    live_id = next((n.get("webhookId") for n in (live or {}).get("nodes", []) if n["name"] == trigger), None)
    next(n for n in body["nodes"] if n["name"] == trigger)["webhookId"] = live_id or str(uuid.uuid4())
    return body


def find_live(n8n: N8n, name: str) -> dict | None:
    found = [w for w in n8n.all("/workflows") if w["name"] == name]
    if len(found) > 1:
        raise LookupError(f"{len(found)} workflows in n8n are named '{name}'; keep one")
    return n8n.call("GET", f"/workflows/{found[0]['id']}") if found else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["publish", "check", "on", "off"])
    ap.add_argument("--target", choices=["all"] + sorted(build.TARGETS), default="all")
    args = ap.parse_args(argv)
    env = dotenv_values(REPO / ".env")
    key = (env.get("N8N_API_KEY") or "").strip()
    base = (env.get("N8N_BASE_URL") or os.environ.get("N8N_BASE_URL") or "http://localhost:5678").strip()
    if not key:
        print("CANNOT RUN N8N_API_KEY is not in .env (docs/build-guide.md, step 1)")
        return 2
    n8n = N8n(base, key)
    keys = sorted(build.TARGETS) if args.target == "all" else [args.target]
    ok = True
    try:
        credentials = n8n.all("/credentials") if args.action in ("publish", "check") else []
        for k in keys:
            t = build.TARGETS[k]
            live = find_live(n8n, t["name"])
            if args.action == "publish":
                wanted = with_credential_ids(build.build(k), credentials)
                body = request_body(wanted, live, t["trigger"])
                if live is not None:
                    saved = n8n.call("PUT", f"/workflows/{live['id']}", body)
                    verb = "Updated"
                else:
                    saved = n8n.call("POST", "/workflows", body)
                    verb = "Created"
                print(f"{verb} '{t['name']}' ({len(body['nodes'])} nodes); {'on' if saved.get('active') else 'off'}. "
                      f"Form /form/{t['form_path']} answers while it is on.")
            elif args.action == "check":
                if live is None:
                    print(f"NOT IN N8N '{t['name']}'")
                    ok = False
                    continue
                wanted = with_credential_ids(build.build(k), credentials)
                diff = differences(live, wanted)
                active_id = live.get("activeVersionId")
                published = n8n.call("GET", f"/workflows/{live['id']}/{active_id}") if active_id else None
                diff += published_problems(live, published, wanted)
                for d in diff:
                    print(f"DIFFERS {t['name']}: {d}")
                ok = ok and not diff
                print(f"{'In step' if not diff else 'Out of step'}: '{t['name']}' {'matches' if not diff else 'does not match'} "
                      f"n8n/{t['file']}; {'on' if live.get('active') else 'off'}.")
                if live.get("active"):
                    print(f"NOTE '{t['name']}' is on: its form answers. Switch it off when the test session ends "
                          "(Unpublish in the n8n screens, or python scripts/n8n_publish.py off).")
            else:
                if live is None:
                    print(f"NOT IN N8N '{t['name']}': run publish first")
                    ok = False
                    continue
                n8n.call("POST", f"/workflows/{live['id']}/{'activate' if args.action == 'on' else 'deactivate'}", {})
                now = n8n.call("GET", f"/workflows/{live['id']}")
                status = ""
                if args.action == "on":
                    form_url = f"{base.rstrip('/')}/form/{t['form_path']}"
                    status = f" Form /form/{t['form_path']}: HTTP {requests.get(form_url, timeout=15).status_code}."
                    if now.get("activeVersionId") != now.get("versionId"):
                        status += " WARNING the published version is not the latest saved one: run check."
                        ok = False
                elif now.get("active") or now.get("activeVersionId"):
                    status = " WARNING n8n still reports it on or published: run check."
                    ok = False
                print(f"'{t['name']}' is {args.action}.{status}")
    except LookupError as e:
        print(f"CANNOT RUN {e}")
        return 2
    except (RuntimeError, requests.RequestException) as e:
        print(f"CANNOT RUN {str(e).replace(key, '<hidden>')}")
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
