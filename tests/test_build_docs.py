"""R28 (KB-137 A4.2): the diagrams and the step lists are made from the workflow files by a script, and a test checks the
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
