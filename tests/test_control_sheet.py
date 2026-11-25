"""The trust-layer spec, A1.5 to A1.7 (R29): the control sheet is one page; every line on it points to a file, a test or a log row; it states
no legal conclusion and names who would decide at an employer; one table matches process, playbook, agent or tool, approval
point, owner and eval. Copied from the GTM pipeline's test (tests/test_control_sheet.py) with this build's paths."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHEET = REPO / "docs" / "control-sheet.md"
TEXT = SHEET.read_text(encoding="utf-8")
LINES = TEXT.splitlines()
SQL = "\n".join(p.read_text(encoding="utf-8") for p in (REPO / "db").glob("*.sql"))

LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
TEST_REF = re.compile(r"`(tests/[\w/]+\.py)::(\w+)`")
FILE_REF = re.compile(r"`((?:scripts|tests|docs|db|skills|n8n|engine)/[\w./-]+\.\w+)`")
LOG_REF = re.compile(r"`(changedesk\.\w+)`")
PRACTICES = ["Decide who is accountable", "Understand impacts and plan accordingly", "Measure and manage risks",
             "Share essential information", "Test and monitor", "Maintain human control"]
LEGAL_CONCLUSIONS = re.compile(
    r"\b(complies|compliant|in compliance|is lawful|is unlawful|is exempt|does not apply|doesn't apply|is not covered|"
    r"is covered by|meets the (duty|law|requirement)|satisfies the (duty|law)|not required to|no disclosure is (needed|required))\b", re.I)


def evidence_lines():
    out = []
    for i, line in enumerate(LINES):
        if line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line) and i + 1 < len(LINES) and re.match(r"^\|[-| ]+\|$", LINES[i + 1]):
            continue  # a header row
        if (line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line)) or re.match(r"^(\d+\.|-) ", line):
            out.append(line)
    return out


def pointers(line):
    found = [("file", t.split("#", 1)[0]) for t in LINK.findall(line) if not t.startswith("http")]
    found += [("test", f"{f}::{name}") for f, name in TEST_REF.findall(line)]
    found += [("file", f"../{f}") for f in FILE_REF.findall(line) if "::" not in f]
    found += [("log", name) for name in LOG_REF.findall(line)]
    return found


def resolves(kind, ref):
    if kind == "file":
        return (SHEET.parent / ref).resolve().exists()
    if kind == "test":
        f, name = ref.split("::")
        path = REPO / f
        return path.is_file() and re.search(rf"^def {name}\(", path.read_text(encoding="utf-8"), re.M) is not None
    return re.search(rf"create (or replace )?(view|function|table)( if not exists)? {re.escape(ref)}\b", SQL) is not None


def test_every_line_points_to_a_file_a_test_or_a_log_row():
    lines = evidence_lines()
    assert len(lines) >= 15
    bare = [line[:80] for line in lines if not pointers(line)]
    assert bare == [], "lines with no evidence:\n" + "\n".join(bare)


def test_every_pointer_on_the_sheet_resolves():
    broken = [f"{kind} {ref}" for line in LINES for kind, ref in pointers(line) if not resolves(kind, ref)]
    assert broken == []


def test_it_fits_one_page():
    visible = re.sub(r"\]\([^)]+\)", "]", TEXT)
    visible = re.sub(r"`[^`]+`", "x", visible)
    assert len(LINES) <= 50 and len(re.findall(r"[A-Za-z0-9$%][\w$%.,'/-]*", visible)) <= 1000


def test_it_is_laid_out_on_the_six_practices_in_order():
    assert re.findall(r"^\d+\. \*\*(.+?)\.\*\*", TEXT, re.M) == PRACTICES
    assert "Guidance for AI Adoption" in TEXT.split("\n## ", 1)[0]


def test_it_holds_the_register_the_approval_points_the_stop_switches_and_the_disclosure_questions():
    assert re.findall(r"^## (.+)$", TEXT, re.M) == ["The AI register (A1.7)", "The six practices", "Approval points and stop switches",
                                                   "The 10/12/2026 disclosure questions"]
    assert "| Process | Playbook | Agent or tool | Approval point | Owner | Eval |" in TEXT
    assert "| Workflow | Where a person decides | Proof | Stop switch |" in TEXT


def test_every_agent_with_a_role_card_is_on_the_register():
    register = TEXT.split("## The AI register", 1)[1].split("\n## ", 1)[0]
    cards = sorted((REPO / "docs" / "role-cards").glob("*.md"))
    assert len(cards) == 3
    for card in cards:
        assert f"](role-cards/{card.name})" in register, card.name


def test_every_workflow_with_an_ai_step_is_on_the_register():
    import json

    with_ai = [p.name for p in (REPO / "n8n").glob("*.json")
               if any(n["type"] == "n8n-nodes-base.httpRequest" for n in json.loads(p.read_text(encoding="utf-8"))["nodes"])]
    assert sorted(with_ai) == ["decide.json", "triage.json"]  # the update drafter runs from scripts/draft_updates.py


def test_it_states_no_legal_conclusion_and_names_who_would_decide():
    assert not LEGAL_CONCLUSIONS.search(TEXT), LEGAL_CONCLUSIONS.search(TEXT)
    assert "states no legal conclusion" in TEXT and TEXT.count("privacy lead") >= 2
    assert "All three tests must be met" in TEXT
    duty = TEXT.split("## The 10/12/2026 disclosure questions", 1)[1]
    assert '"make, or do a thing that is substantially and directly related to making, a decision"' in duty
    assert '"could reasonably be expected to significantly affect the rights or interests of an individual"' in duty


def test_the_checks_catch_a_line_with_no_evidence_and_a_broken_pointer():
    assert pointers("| A row | with | only words |") == []
    assert pointers("| A row | with [a source](https://example.org) |") == []
    assert not resolves("test", "tests/test_control_sheet.py::test_that_does_not_exist")
    assert not resolves("log", "changedesk.no_such_view") and resolves("log", "changedesk.outbox")
    assert not resolves("file", "no-such-file.md")
