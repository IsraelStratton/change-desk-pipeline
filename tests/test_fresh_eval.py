"""Stage 6, the fresh eval set (R27): at least 20 labelled requests the playbook has never seen, hostile ones among them,
with labels committed before any run; and its one result, which is reported whatever it shows and never tuned on."""
import hashlib
import json
import re

from conftest import REPO

EVAL = REPO / "skills" / "triage-playbook" / "eval"
FRESH_TEXT = (EVAL / "fresh-cases.json").read_text(encoding="utf-8")
FRESH = json.loads(FRESH_TEXT)
TUNED = json.loads((EVAL / "cases.json").read_text(encoding="utf-8"))
LANES = {"urgent", "fixed_date", "standard", "small"}


def grams(text, n=6):
    words = re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def test_the_fresh_set_has_at_least_twenty_cases_with_hostile_ones_among_them():
    cases = FRESH["cases"]
    assert len(cases) >= 20 and len({c["case_id"] for c in cases}) == len(cases)
    hostile = [c for c in cases if c["label"]["hostile"]]
    assert 5 <= len(hostile) < len(cases) / 2
    assert all(c["label"]["needs_person"] is True for c in hostile)
    assert {c["label"]["lane"].split("|")[0] for c in cases} >= LANES, "every lane is in it"


def test_every_label_uses_the_playbooks_codes(pb):
    codes = set(pb["playbooks"]) | {"none"}
    for c in FRESH["cases"]:
        lab = c["label"]
        assert set(lab["lane"].split("|")) <= LANES, c["case_id"]
        assert lab["size_band"] is None or set(lab["size_band"].split("|")) <= {"small", "medium", "large"}, c["case_id"]
        assert lab["playbooks"] and set(lab["playbooks"]) <= codes, c["case_id"]
        assert lab["needs_person"] in (True, False, None)


def test_the_playbook_has_never_seen_these_requests():
    """No fresh request shares six words in a row with any of the 40 cases the playbook was tuned on."""
    tuned = set()
    for c in TUNED["cases"]:
        tuned |= grams(" ".join(str(c.get(k) or "") for k in ("title", "body", "requester_says_breaks", "requester_says_harm")))
    for c in FRESH["cases"]:
        shared = grams(" ".join(str(c.get(k) or "") for k in ("title", "body", "requester_says_breaks", "requester_says_harm"))) & tuned
        assert not shared, (c["case_id"], sorted(shared)[:3])


def test_the_fresh_result_is_of_the_committed_set_and_the_live_playbook_unchanged():
    """The result file (skills/triage-playbook/eval/results-fresh.json) was made from exactly these labels and from the
    playbook the tuned result kept (1.0.2): the same SHA-256 as the tuned run's, so nothing was tuned in between."""
    path = EVAL / "results-fresh.json"
    if not path.exists():
        return  # before the one run
    fresh = json.loads(path.read_text(encoding="utf-8"))
    tuned = json.loads((EVAL / "results.json").read_text(encoding="utf-8"))
    live = (REPO / "skills" / "triage-playbook" / "SKILL.md").read_text(encoding="utf-8")
    assert fresh["cases_sha256"] == hashlib.sha256(FRESH_TEXT.encode("utf-8")).hexdigest()
    assert fresh["playbook"]["sha256"] == tuned["playbook"]["sha256"] == hashlib.sha256(live.encode("utf-8")).hexdigest()
    assert fresh["playbook"]["version"] == "1.0.2" and fresh["cases"] == len(FRESH["cases"])
    assert fresh["bar_sha256"] == tuned["bar_sha256"], "the same bar, set before the first run of stage 1"


def test_the_phone_numbers_in_the_eval_cases_are_from_acmas_fiction_ranges():
    """Israel, 25/11/2026: before the repository can go public, no case may hold a number that could be a real person's. ACMA
    reserves mobile 0491 570 006 (and others) and geographic (02) 5550 xxxx for creative works. E-31 was changed and run again
    (its re-run is recorded in results.json); F-24 was in the range already."""
    tuned = {c["case_id"]: c for c in TUNED["cases"]}
    fresh = {c["case_id"]: c for c in FRESH["cases"]}
    assert "+61 491 570 006" in tuned["E-31"]["body"] and "+61 2 5550 1234" in fresh["F-24"]["body"]
    phone = re.compile(r"\+?\d[\d\s().-]{7,}\d")
    for c in list(tuned.values()) + list(fresh.values()):
        for m in phone.findall(" ".join(str(c.get(k) or "") for k in ("body", "requester_says_breaks", "requester_says_harm"))):
            digits = re.sub(r"\D", "", m)
            if len(digits) >= 8:
                assert digits.endswith("491570006") or "25550" in digits, (c["case_id"], "a number outside the fiction ranges")
    results = json.loads((EVAL / "results.json").read_text(encoding="utf-8"))
    assert [r["cases"] for r in results["reruns"]] == [["E-31"]] and "ACMA" in results["reruns"][0]["why"]
