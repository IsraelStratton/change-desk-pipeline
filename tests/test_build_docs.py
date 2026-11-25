"""R28 (the trust-layer spec, A4.2): the diagrams and the step lists are made from the workflow files by a script, and a test checks the
README's generated parts and docs/workflows.md match a fresh build. CI runs this on every push. Shaped from the GTM
pipeline's tests/test_build_docs.py."""
import re
import sys

import pytest
from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import build_docs as bd  # noqa: E402
import build_n8n  # noqa: E402

NODE_LINE = re.compile(r'^  (s\d+)(\(\["|\[\("|\{\{"|\[\["|\{"|\[")(\d+)\. ([^"]+)("\]\)|"\)\]|"\}\}|"\]\]|"\}|"\])$')
EDGE_LINE = re.compile(r"^  (s\d+) -->(?:\|([^|]+)\|)? (s\d+)$")


def parse(text):
    nodes, edges = {}, []
    for line in text.splitlines():
        if m := NODE_LINE.match(line):
            assert m.group(1) == f"s{m.group(3)}", line
            nodes[m.group(1)] = m.group(4)
        elif m := EDGE_LINE.match(line):
            edges.append((m.group(1), m.group(3), m.group(2) or ""))
        else:
            assert line in ("```mermaid", "flowchart TD", "```"), line
    return nodes, edges


def test_the_readme_and_the_workflows_page_match_a_fresh_build():
    assert bd.check_all() == []


def test_the_readme_has_each_generated_part_once():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    for name in bd.BLOCKS:
        assert text.count(f"<!-- generated:{name} start") == 1 and text.count(f"<!-- generated:{name} end -->") == 1, name


@pytest.mark.parametrize("key", sorted(build_n8n.TARGETS))
def test_every_workflow_is_drawn_with_every_node_once_and_every_connection(key):
    wf = bd.workflow(key)
    nodes, edges = parse(bd.diagram(wf))
    assert sorted(nodes.values()) == sorted(n["name"] for n in wf["nodes"])
    names = {v: k for k, v in nodes.items()}
    assert len(edges) == len(bd.edges(wf))
    for src, dst, _ in bd.edges(wf):
        assert any(a == names[src] and b == names[dst] for a, b, _ in edges), (src, dst)
    steps = re.findall(r"^(\d+)\. \*\*(.+?)\*\* \(", bd.steps(wf), re.M)
    assert [(f"s{i}", name) for i, name in steps] == sorted(nodes.items(), key=lambda kv: int(kv[0][1:])), "the list's numbers are the diagram's"


def test_the_run_order_starts_at_the_form_and_a_loop_reads_its_body_before_what_follows():
    order = bd.run_order(bd.workflow("decide"))
    pos = {n: i for i, n in enumerate(order)}
    assert order[0] == "Start Decide List"
    assert pos["Stamp Start"] < pos["Claude Message Drafter"] < pos["Check Draft"] < pos["Collect Drafts"] < pos["Log Drafts"]
    order = bd.run_order(bd.workflow("approve"))
    assert order[:3] == ["Start Approval", "Read Drafts", "Build Form"] and order.index("Approve Updates") > order.index("Approval")
    nodes, edges = parse(bd.diagram(bd.workflow("triage")))
    assert ("s7", "s8", "next one") in edges and any(label == "all done" for _, _, label in edges), "the loop's two ways out are labelled"


# The internal names, spelled in pieces so this file does not hold them itself.
INTERNAL = re.compile(r"\b(?:" + "|".join(["K" + "B", "IN" + "IT", "A" + "DR", "S" + "OR", "PR" + "OJ"]) + r")-\d+\b|"
                      + "|".join(re.escape(x) for x in ["COURSES" + " 2ND", "courses" + "-2nd", "Code" + " chat", "planning" + " chat",
                                                        "Evolution" + " Copilot"]) + r"|\bIs" + r"rael\b", re.I)
# What may stay, and why. The reviewer label is data: the real test runs (n8n-8905 to n8n-8912) made their decisions under it.
ALLOWED_EVERYWHERE = ["courses" + "-2nd (delegated)"]
ALLOWED_IN = {
    # The triage playbook names its process catalogue. Its SHA-256 is pinned by both eval results, and the fresh eval was run
    # once, by design: changing one word would need it run again. The not-kept 1.0.1 candidate is the file that was tested,
    # and the triage workflow carries the playbook as built.
    "skills/triage-playbook/SKILL.md": ["K" + "B-115"],
    "skills/triage-playbook/eval/playbook-1.0.1-not-kept.md": ["K" + "B-115"],
    "n8n/triage.json": ["K" + "B-115"],
    # The copyright line names the copyright holder, as a licence must.
    "LICENSE": ["Is" + "rael Stratton"],
}


def test_no_tracked_file_holds_an_internal_name():
    """The owner, 25/11/2026: before the repository can go public, no tracked file names an internal page, initiative,
    decision record, session or person. Each is said in plain words: the design note, the spec, the reviewer, the owner.
    Only the reviewer label (data from the real test runs) and the few pinned or legal texts above may stay."""
    import subprocess

    files = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    found = []
    for f in files:
        try:
            text = (REPO / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for ok in ALLOWED_EVERYWHERE + ALLOWED_IN.get(f, []):
            text = text.replace(ok, "")
        found += [f"{f}: {m.group(0)}" for m in INTERNAL.finditer(text)]
    assert found == [], found[:20]


def test_the_readme_reads_cold_with_no_internal_names_and_no_label():
    """The README says what each thing is in plain words, and does not quote the reviewer label either."""
    assert INTERNAL.findall((REPO / "README.md").read_text(encoding="utf-8")) == []


def test_the_names_check_catches_what_it_should():
    assert INTERNAL.search("as K" + "B-139 says") and INTERNAL.search("the Code" + " chat") and INTERNAL.search("Is" + "rael's yes")
    assert not INTERNAL.search("IsraelStratton/change-desk-pipeline") and not INTERNAL.search("CD-0139 and R16")
