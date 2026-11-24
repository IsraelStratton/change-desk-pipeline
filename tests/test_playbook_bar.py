"""The push gate for the triage playbook (scripts/playbook_bar.py): the live playbook was tested as it is and meets
its bar. Also run in CI, so a playbook change that skipped the eval fails on GitHub too."""
import json
import sys

import pytest
from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import playbook_bar as gate  # noqa: E402


def test_the_live_playbook_meets_its_bar():
    if not (REPO / gate.REL["results"]).exists():
        pytest.skip("the eval has not been run yet")
    assert gate.check_all(gate.tree_reader()) == []


def fake_tree(over: dict):
    base = {rel: (REPO / rel).read_text(encoding="utf-8") if (REPO / rel).exists() else None for rel in gate.REL.values()}
    base.update(over)
    return lambda rel: base.get(rel)


def test_an_edited_playbook_cannot_be_pushed_untested():
    if not (REPO / gate.REL["results"]).exists():
        pytest.skip("the eval has not been run yet")
    edited = (REPO / gate.REL["playbook"]).read_text(encoding="utf-8") + "\nOne more rule.\n"
    found = gate.check_all(fake_tree({gate.REL["playbook"]: edited}))
    assert any("changed since its eval was run" in f for f in found)


def test_a_moved_bar_or_a_result_below_it_is_refused():
    if not (REPO / gate.REL["results"]).exists():
        pytest.skip("the eval has not been run yet")
    bar = json.loads((REPO / gate.REL["bar"]).read_text(encoding="utf-8"))
    bar["lines"]["lane"]["at_least"] = 0.5
    assert any("the bar is set before a run" in f for f in gate.check_all(fake_tree({gate.REL["bar"]: json.dumps(bar)})))
    res = json.loads((REPO / gate.REL["results"]).read_text(encoding="utf-8"))
    res["kept_model"] = None
    assert any("no model met every line" in f for f in gate.check_all(fake_tree({gate.REL["results"]: json.dumps(res)})))


def test_no_results_means_no_push():
    assert gate.check_all(fake_tree({gate.REL["results"]: None})) == [
        f"{gate.REL['results']}: missing (run python scripts/triage_eval.py eval --log --save)"]
