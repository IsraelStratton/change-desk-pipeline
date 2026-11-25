#!/usr/bin/env python3
"""Make the docs that describe the workflows from the workflow files themselves (R28; the trust-layer spec, A4.2).

Shaped from the GTM pipeline (scripts/build_docs.py), cut to what this build needs:
  docs/workflows.md   every n8n workflow (n8n/*.json, the files scripts/build_n8n.py writes): a diagram and a
                      numbered step list, made from the file alone. The diagram's numbers are the list's numbers
  README.md           only the parts between <!-- generated:NAME start --> and <!-- generated:NAME end -->:
                        workflows  one line per workflow: its form, its steps, its AI steps, the store functions it calls
                        diagram    the stage 5 approval workflow, drawn from n8n/approve-updates.json
                      Everything else in the README is written by hand.

So the diagrams and the step lists cannot drift from the files: tests/test_build_docs.py makes them again and fails
if they differ, in CI on every push and in the test run before each push.

  python scripts/build_docs.py           # write both files
  python scripts/build_docs.py --check   # exit 1 if either is out of date

Exit codes: 0 done (or up to date), 1 out of date, 2 could not build.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_n8n  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
WORKFLOWS_MD = REPO / "docs" / "workflows.md"
MAIN = "approve"
SHAPES = {  # n8n node type: (open, close) of the Mermaid shape
    "n8n-nodes-base.formTrigger": ('(["', '"])'), "n8n-nodes-base.form": ('(["', '"])'), "n8n-nodes-base.code": ('["', '"]'),
    "n8n-nodes-base.postgres": ('[("', '")]'), "n8n-nodes-base.httpRequest": ('{{"', '"}}'), "n8n-nodes-base.if": ('{"', '"}'),
    "n8n-nodes-base.splitInBatches": ('[["', '"]]'),
}
OUTPUT_WORDS = {"n8n-nodes-base.if": ["yes", "no"], "n8n-nodes-base.splitInBatches": ["all done", "next one"]}
KIND_WORDS = {"n8n-nodes-base.formTrigger": "form, started by hand", "n8n-nodes-base.form": "form page", "n8n-nodes-base.code": "code",
              "n8n-nodes-base.postgres": "store", "n8n-nodes-base.httpRequest": "Claude API, the one AI step", "n8n-nodes-base.if": "check",
              "n8n-nodes-base.splitInBatches": "one at a time"}


# The functions the engines define: a Code node is described by the ones it calls.
ENGINE_FUNCTIONS = {m for f in (REPO / "engine").glob("*.js") for m in re.findall(r"^function (\w+)\(", f.read_text(encoding="utf-8"), re.M)}


def workflow(key: str) -> dict:
    return json.loads((REPO / "n8n" / build_n8n.TARGETS[key]["file"]).read_text(encoding="utf-8"))


def edges(wf: dict) -> list[tuple[str, str, int]]:
    out = []
    for src, conns in wf["connections"].items():
        for i, outs in enumerate(conns.get("main", [])):
            for c in outs:
                out.append((src, c["node"], i))
    return out


def run_order(wf: dict) -> list[str]:
    """The nodes in the order a run meets them: from the trigger, each node's outputs in turn (depth first)."""
    by = {n["name"]: n for n in wf["nodes"]}
    start = next(n["name"] for n in wf["nodes"] if n["type"] == "n8n-nodes-base.formTrigger")
    nxt: dict[str, list[str]] = {}
    for a, b, i in sorted(edges(wf), key=lambda e: (e[0], -e[2] if by[e[0]]["type"] == "n8n-nodes-base.splitInBatches" else e[2])):
        nxt.setdefault(a, []).append(b)
    seen: list[str] = []

    def visit(name: str):
        if name in seen:
            return
        seen.append(name)
        for b in nxt.get(name, []):
            visit(b)
    visit(start)
    return seen + [n["name"] for n in wf["nodes"] if n["name"] not in seen]


def diagram(wf: dict) -> str:
    by = {n["name"]: n for n in wf["nodes"]}
    num = {name: i + 1 for i, name in enumerate(run_order(wf))}
    lines = ["```mermaid", "flowchart TD"]
    for name, i in sorted(num.items(), key=lambda kv: kv[1]):
        a, b = SHAPES.get(by[name]["type"], ('["', '"]'))
        lines.append(f"  s{i}{a}{i}. {name}{b}")
    for src, dst, out in edges(wf):
        words = OUTPUT_WORDS.get(by[src]["type"])
        label = f"|{words[out]}|" if words else ""
        lines.append(f"  s{num[src]} -->{label} s{num[dst]}")
    lines.append("```")
    return "\n".join(lines)


def what_it_does(n: dict) -> str:
    p = n.get("parameters") or {}
    if n["type"] == "n8n-nodes-base.formTrigger":
        return p.get("formTitle", "")
    if n["type"] == "n8n-nodes-base.form":
        return (p.get("options") or {}).get("formTitle") or ("the closing message" if p.get("operation") == "completion" else "")
    if n["type"] == "n8n-nodes-base.postgres":
        fn = re.findall(r"changedesk\.(\w+)", p.get("query", ""))
        return "reads " + ", ".join(dict.fromkeys(fn)) if not any(f in ("add_request", "log_triage", "confirm_lanes", "change_score", "decide",
                                                                         "log_drafts", "approve_updates") for f in fn) \
            else "writes through " + ", ".join(f for f in dict.fromkeys(fn) if not f.startswith(("stale_", "inbox")))
    if n["type"] == "n8n-nodes-base.httpRequest":
        return "one Messages call, Haiku 5.5, structured output"
    if n["type"] == "n8n-nodes-base.code":
        js = p.get("jsCode", "")
        m = re.search(r"// ===== n8n node: [^=]+ =====\n// (.+)", js)
        if m:
            return m.group(1).strip()
        own = js.split("// ===== n8n node:", 1)[-1]
        called = [f for f in dict.fromkeys(re.findall(r"\b([a-z][A-Za-z]+)\(", own)) if f in ENGINE_FUNCTIONS]
        if called:
            return "the engine's " + ", ".join(f"`{f}`" for f in called)
        if "started_ms" in own:
            return "notes when the AI call starts"
        if "title:" in own:
            return "the words of the closing message"
        return ""
    return ""


def steps(wf: dict) -> str:
    by = {n["name"]: n for n in wf["nodes"]}
    out = []
    for i, name in enumerate(run_order(wf), 1):
        n = by[name]
        what = what_it_does(n)
        out.append(f"{i}. **{name}** ({KIND_WORDS.get(n['type'], n['type'])}){': ' + what if what else ''}")
    return "\n".join(out)


def ai_steps(wf: dict) -> int:
    return sum(1 for n in wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequest")


def writes(wf: dict) -> list[str]:
    fns = []
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.postgres":
            for f in re.findall(r"changedesk\.(\w+)\(", n["parameters"]["query"]):
                if f in ("add_request", "log_triage", "confirm_lanes", "change_score", "decide", "log_drafts", "approve_updates"):
                    fns.append(f)
    return list(dict.fromkeys(fns))


def workflows_md() -> str:
    lines = ["# The workflows, drawn from their files", "",
             "Made by `scripts/build_docs.py` from `n8n/*.json` (the files `scripts/build_n8n.py` writes and `scripts/n8n_publish.py` "
             "puts into n8n). Each diagram's numbers are its step list's numbers. Every workflow starts from a form, by hand: none has a "
             "schedule. Every write goes through one of the store's checked functions. Nothing sends: an approved update goes to the "
             "outbox table only. `tests/test_build_docs.py` fails if this page differs from the files.", ""]
    for key, t in build_n8n.TARGETS.items():
        wf = workflow(key)
        lines += [f"## {t['name']}", "", f"File `n8n/{t['file']}`; form `/form/{t['form_path']}`; {len(wf['nodes'])} nodes; "
                  f"{ai_steps(wf)} AI step{'s' if ai_steps(wf) != 1 else ''}; writes through {', '.join(f'`{w}`' for w in writes(wf)) or 'nothing'}.",
                  "", diagram(wf), "", steps(wf), ""]
    return "\n".join(lines)


def block_workflows() -> str:
    lines = ["| Workflow | Form | Nodes | AI steps | Writes through |", "|---|---|---|---|---|"]
    for key, t in build_n8n.TARGETS.items():
        wf = workflow(key)
        lines.append(f"| {t['name']} | `/form/{t['form_path']}` | {len(wf['nodes'])} | {ai_steps(wf)} | "
                     f"{', '.join(f'`{w}`' for w in writes(wf)) or 'nothing'} |")
    return "\n".join(lines)


def block_diagram() -> str:
    wf = workflow(MAIN)
    return f"{diagram(wf)}\n\n{steps(wf)}"


BLOCKS = {"workflows": block_workflows, "diagram": block_diagram}


def fill(readme: str) -> str:
    for name, make in BLOCKS.items():
        start = f"<!-- generated:{name} start (made by scripts/build_docs.py) -->"
        end = f"<!-- generated:{name} end -->"
        if readme.count(start) != 1 or readme.count(end) != 1:
            raise ValueError(f"README.md must hold the generated:{name} markers once")
        head, rest = readme.split(start)
        _, tail = rest.split(end)
        readme = f"{head}{start}\n{make()}\n{end}{tail}"
    return readme


def check_all() -> list[str]:
    out = []
    if not WORKFLOWS_MD.exists() or WORKFLOWS_MD.read_text(encoding="utf-8") != workflows_md():
        out.append("docs/workflows.md is out of date")
    readme = README.read_text(encoding="utf-8")
    if fill(readme) != readme:
        out.append("README.md's generated parts are out of date")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.check:
            found = check_all()
            for f in found:
                print(f"OUT OF DATE {f}: run python scripts/build_docs.py")
            if not found:
                print("docs/workflows.md and the README's generated parts match the workflow files.")
            return 1 if found else 0
        WORKFLOWS_MD.write_text(workflows_md(), encoding="utf-8")
        README.write_text(fill(README.read_text(encoding="utf-8")), encoding="utf-8")
    except (OSError, ValueError, KeyError) as e:
        print(f"CANNOT BUILD {e}")
        return 2
    print(f"Wrote docs/workflows.md ({len(build_n8n.TARGETS)} workflows) and the README's generated parts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
