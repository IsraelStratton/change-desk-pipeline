#!/usr/bin/env python3
"""Clean exports: what a committed n8n workflow file may hold, and the cleaner that makes one.

Copied from the GTM pipeline (scripts/clean_exports.py), cut to n8n: this build has no Make or Zapier
exports. Every workflow file in n8n/ is checked on every push (tests/test_clean_exports.py in CI, and
scripts/prepush_check.py on the commit being pushed). A workflow file holds no credential, key,
address, host, username or ID:

  every file   no email address but a reserved example one; no Google client ID or secret; no Claude
               or bearer key
  n8n          only name, nodes, connections and settings at the top (no workflow ID, version,
               instance, sharing, tags or pinned data); every credential named, with no ID
  on this Mac  no value from .env or .prepush-private.local (CI has neither file)

n8n fills in each credential's ID by name when scripts/n8n_publish.py puts a workflow in.

  python scripts/clean_exports.py --check                            # every workflow file in n8n/
  python scripts/clean_exports.py n8n-live "WORKFLOW NAME" OUT.json  # read one from the local n8n API, cleaned

A cleaner replaces what it knows how to replace, then runs the same checks on its result and writes
nothing if anything is left. Findings name the file and the kind of value, never the value.

Exit codes: 0 clean (or written), 1 findings, 2 could not run.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

PLACEHOLDER = re.compile(r"^[A-Z][A-Z0-9_]*$")
N8N_TOP_KEYS = {"name", "nodes", "connections", "settings"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(r"@(?:[A-Za-z0-9-]+\.)*(example\.(com|org|net)|[A-Za-z0-9-]+\.example)$", re.I)
PATTERNS = {
    "a Google OAuth client ID": re.compile(r"\d{6,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com"),
    "a Google OAuth client secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),
    "a Claude API key": re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    "a bearer token": re.compile(r"Bearer [A-Za-z0-9._~+/=-]{20,}"),
}
NS = uuid.UUID("3c1d6e0a-9b2f-4c8e-a1d7-5f0e2b4c6a81")  # fixed, so a cleaned export is the same every time

Reader = Callable[[str], "str | None"]


def text_findings(text: str, private: dict[str, str] | None = None) -> list[str]:
    """What any export must never hold, by kind. `private` maps a label to a value (local runs only)."""
    out = []
    if any(not ALLOWED_EMAIL.search(m) for m in EMAIL.findall(text)):
        out.append("an email address")
    for label, pattern in PATTERNS.items():
        if pattern.search(text):
            out.append(label)
    for label, value in (private or {}).items():
        if value and value in text:
            out.append(f"a private value ({label})")
    return out


def n8n_findings(wf: dict) -> list[str]:
    out = []
    extra = sorted(set(wf) - N8N_TOP_KEYS)
    if extra:
        out.append(f"instance data at the top: {', '.join(extra)}")
    for n in wf.get("nodes", []):
        for cred_type, cred in (n.get("credentials") or {}).items():
            cid = cred.get("id")
            if cid is not None and not PLACEHOLDER.match(str(cid)):
                out.append(f"node {n['name']}: a credential ID ({cred_type})")
            if not cred.get("name"):
                out.append(f"node {n['name']}: a credential with no name ({cred_type})")
        if n.get("pinData"):
            out.append(f"node {n['name']}: pinned data")
    settings = wf.get("settings") or {}
    for key in ("errorWorkflow", "timeSavedPerExecution"):
        if key in settings:
            out.append(f"an instance setting ({key})")
    return out


def export_findings(text: str, private: dict[str, str] | None = None) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ["not valid JSON"]
    return n8n_findings(data) + text_findings(text, private)


def workflow_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "n8n"],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.split() if p.endswith(".json"))


def check_all(read: Reader, private: dict[str, str] | None = None, files: list[str] | None = None) -> list[str]:
    out = []
    names = files if files is not None else workflow_files()
    for rel in names:
        text = read(rel)
        if text is None:
            out.append(f"{rel}: missing")
            continue
        out += [f"{rel}: {f}" for f in export_findings(text, private)]
    return out


def private_values() -> dict[str, str]:
    """The local .env values and the git-ignored private list, as scripts/prepush_check.py reads them."""
    from prepush_check import private_values as read

    return read()


def clean_n8n(raw: dict) -> dict:
    """Keep what n8n needs to import a workflow, and nothing that belongs to one instance."""
    wf = {"name": raw["name"], "nodes": [], "connections": copy.deepcopy(raw.get("connections", {})),
          "settings": {"executionOrder": (raw.get("settings") or {}).get("executionOrder", "v1")}}
    for node in raw["nodes"]:
        n = copy.deepcopy(node)
        n["id"] = str(uuid.uuid5(NS, f"{raw['name']}/{n['name']}"))
        if "webhookId" in n:
            n["webhookId"] = str(uuid.uuid5(NS, f"{raw['name']}/{n['name']}/webhook"))
        for cred in (n.get("credentials") or {}).values():
            cred["id"] = None
        wf["nodes"].append(n)
    return wf


def write_clean(data, out: Path, private: dict[str, str]) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    findings = export_findings(text, private)
    if findings:
        for f in findings:
            print(f"REFUSED {f}")
        print("Nothing written: clean these by hand, then run the cleaner again.")
        return 1
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}: clean.")
    return 0


def read_live_n8n(name: str) -> dict:
    import requests
    from dotenv import dotenv_values

    env = dotenv_values(REPO / ".env")
    key = (env.get("N8N_API_KEY") or "").strip()
    base = (env.get("N8N_BASE_URL") or "http://localhost:5678").strip().rstrip("/")
    if not key:
        raise LookupError("N8N_API_KEY is not in .env")
    headers = {"X-N8N-API-KEY": key}
    found = [w for w in requests.get(f"{base}/api/v1/workflows?limit=250", headers=headers, timeout=15).json().get("data", [])
             if w["name"] == name]
    if len(found) != 1:
        raise LookupError(f"expected one n8n workflow named {name!r}, found {len(found)}")
    return requests.get(f"{base}/api/v1/workflows/{found[0]['id']}", headers=headers, timeout=15).json()


def tree_reader(root: Path = REPO) -> Reader:
    def read(rel: str) -> str | None:
        p = root / rel
        return p.read_text(encoding="utf-8") if p.exists() else None
    return read


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="check every workflow file in n8n/")
    ap.add_argument("kind", nargs="?", choices=["n8n-live"])
    ap.add_argument("source", nargs="?", help="the workflow's name in n8n")
    ap.add_argument("out", nargs="?", help="where to write the clean export")
    args = ap.parse_args(argv)
    try:
        private = private_values()
    except Exception as e:  # noqa: BLE001 - the check still runs without the local values
        print(f"NOTE local private values not read ({type(e).__name__}); checking patterns only")
        private = {}
    if args.check or not args.kind:
        files = workflow_files()
        findings = check_all(tree_reader(), private, files)
        for f in findings:
            print(f"FAIL {f}")
        if not findings:
            print(f"PASS {len(files)} workflow files hold no credential ID, key, address, host or instance data")
        return 1 if findings else 0
    if not (args.source and args.out):
        ap.error("give the workflow name and the output file")
    try:
        return write_clean(clean_n8n(read_live_n8n(args.source)), Path(args.out), private)
    except (LookupError, OSError, ValueError, KeyError) as e:
        print(f"CANNOT RUN {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
