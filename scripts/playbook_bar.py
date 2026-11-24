#!/usr/bin/env python3
"""The push gate for the triage playbook: the live playbook must have been tested, and must meet its bar.

Copied from the GTM pipeline (scripts/playbook_bar.py, KB-137 A3.4) and cut to this build's one playbook.
For the commit being pushed (scripts/prepush_check.py) and in CI (tests/test_playbook_bar.py):
  - skills/triage-playbook/eval/results.json exists;
  - it was made from exactly the live playbook, the labelled cases and the bar now committed
    (their SHA-256s match), so an edit to any of them after the run cannot be pushed untested;
  - it kept a model, and that model's rates meet every line of the bar.
Findings name the file and the line, never a value from .env.

  python scripts/playbook_bar.py          # check the working tree
Exit codes: 0 meets the bar, 1 findings.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
REL = {"playbook": "skills/triage-playbook/SKILL.md", "cases": "skills/triage-playbook/eval/cases.json",
       "bar": "skills/triage-playbook/eval/bar.json", "results": "skills/triage-playbook/eval/results.json"}
Reader = Callable[[str], "str | None"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_all(read: Reader) -> list[str]:
    texts = {k: read(v) for k, v in REL.items()}
    missing = [REL[k] for k, v in texts.items() if v is None]
    if missing:
        return [f"{m}: missing (run python scripts/triage_eval.py eval --log --save)" for m in missing]
    try:
        results = json.loads(texts["results"])
        bar = json.loads(texts["bar"])
    except json.JSONDecodeError as e:
        return [f"results or bar: not valid JSON ({e.msg})"]
    out = []
    if results.get("playbook", {}).get("sha256") != sha256(texts["playbook"]):
        out.append(f"{REL['playbook']}: changed since its eval was run; test it again before pushing")
    if results.get("cases_sha256") != sha256(texts["cases"]):
        out.append(f"{REL['cases']}: changed since the eval was run")
    if results.get("bar_sha256") != sha256(texts["bar"]):
        out.append(f"{REL['bar']}: changed since the eval was run; the bar is set before a run, never after")
    kept = results.get("kept_model")
    if not kept:
        out.append(f"{REL['results']}: no model met every line of the bar")
        return out
    s = (results.get("summaries") or {}).get(kept) or {}
    for line, rule in bar["lines"].items():
        rate = (s.get("rates") or {}).get(line)
        if rate is None or rate < rule["at_least"]:
            out.append(f"{REL['results']}: {kept} is below the bar on {line}")
    return out


def tree_reader(root: Path = REPO) -> Reader:
    def read(rel: str) -> str | None:
        p = root / rel
        return p.read_text(encoding="utf-8") if p.exists() else None
    return read


def git_reader(ref: str, root: Path = REPO) -> Reader:
    def read(rel: str) -> str | None:
        out = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=root, capture_output=True, text=True, check=False)
        return out.stdout if out.returncode == 0 else None
    return read


def main(argv: list[str] | None = None) -> int:
    findings = check_all(tree_reader())
    for f in findings:
        print(f"FAIL {f}")
    if not findings:
        print("PASS the live triage playbook was tested as it is, and meets every line of its bar")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
