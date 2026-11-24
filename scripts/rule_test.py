#!/usr/bin/env python3
"""The rule test (KB-139 stage 4, R26): three order rules on the sample history, then on the histories of seeds 163
to 172, with the spread. The proof for the design, as the eval is for the triage step. A plain script, no database.

KB-136 section 6.6 kept the policy test that found the fault: 300 runs of made-up tickets. Here the same three rules
work the sample history's own arrivals again, week by week, through the planner's plan_week() (R13: the code that makes
the real week's plan):
  - highest score first (urgent counted as 10): how the history was worked. The replay must give back the history's
    own work log hour for hour, and it is checked on every seed: so the test runs the code the plan runs;
  - value per hour first: urgent first, then the value part per hour of size;
  - lanes: this design (R12), with the starting settings of settings/settings.json.
The measures are the policy test's. "Done %" counts items that arrived before the last four weeks; items a person
closed or merged count neither way. The table goes in the README whatever it shows.

  python scripts/rule_test.py           # print it, write docs/reports/rule-test.md and the README's table
  python scripts/rule_test.py --check   # exit 1 if either is not what the script makes now

Every ticket is made up; the figures show direction, not size. Exit codes: 0 done (or up to date), 1 out of date or a
replay did not give back its history, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_history  # noqa: E402
import planner as P  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HISTORY = REPO / "sample" / "history.json"
SETTINGS = REPO / "settings" / "settings.json"
REPORT = REPO / "docs" / "reports" / "rule-test.md"
README = REPO / "README.md"
START, END = "<!-- rule-test:start (made by scripts/rule_test.py) -->", "<!-- rule-test:end -->"
SEEDS = range(163, 173)
LABELS = {"small done %": "Small items done", "oldest small waiting (weeks)": "Oldest small item still waiting",
          "fixed dates met %": "Fixed dates met", "oldest standard waiting (weeks)": "Oldest standard item still waiting",
          "open at the end": "Items open at the end", "value delivered": "Value delivered (first column = 100)"}


def settings() -> dict:
    return {s["key"]: s["value"] for s in json.loads(SETTINGS.read_text(encoding="utf-8"))["settings"]}


def run_one(doc: dict, s: dict) -> tuple[dict[str, dict[str, float]], bool, int]:
    """The three rules on one history. Returns the measures by rule, whether the old rule gave back the work log, and
    the safe-start days used."""
    items, ends = P.history_items(doc, s["score_weights"])
    ssd = P.history_safe_start_days(doc, float(s["latest_safe_start_percentile"]))
    ps = P.PlanSettings.from_settings(s, ssd)
    week_one = date.fromisoformat(doc["week_one"])
    out, same = {}, False
    for rule in P.RULES:
        rp = P.replay(items, ends, week_one, doc["weeks"], ps, rule)
        out[rule] = P.replay_measures(rp, week_one, doc["weeks"])
        if rule == "highest score first":
            want = {(w["request_id"], date.fromisoformat(w["week_start"])): float(w["hours"]) for w in doc["work_log"]}
            same = want == {k: round(v, 1) for k, v in rp.worked.items()}
    base = out[P.RULES[0]]["value delivered"] or 1
    for rule in P.RULES:
        out[rule]["value delivered"] = round(100 * out[rule]["value delivered"] / base)
    return out, same, ssd


def fmt(key: str, v: float | None) -> str:
    if v is None:
        return "none fell due"
    if key.endswith("%"):
        return f"{v:g}%"
    if "weeks" in key:
        return f"{v:g} weeks"
    return f"{v:g}"


def spread(key: str, vals: list[float | None]) -> str:
    """The median, with the lowest and highest; a history where nothing fell due is left out, and the count says so."""
    have = [v for v in vals if v is not None]
    if not have:
        return fmt(key, None)
    med, lo, hi = st.median(have), min(have), max(have)
    text = fmt(key, round(med, 1)) if lo == hi else f"{fmt(key, round(med, 1))} ({fmt(key, lo)} to {fmt(key, hi)})"
    return text if len(have) == len(vals) else f"{text}, {len(have)} of {len(vals)} seeds"


def build() -> tuple[str, str, bool]:
    s = settings()
    doc = json.loads(HISTORY.read_text(encoding="utf-8"))
    sample, sample_same, ssd = run_one(doc, s)
    per_seed, fidelity, counts = {}, {}, {}
    for seed in SEEDS:
        d = json.loads(make_history.render(make_history.Maker(seed).make()))
        per_seed[seed], fidelity[seed], _ = run_one(d, s)
        counts[seed] = d["counts"]["by_lane"]
    same_all = sample_same and all(fidelity.values())
    head = "| Measure | " + " | ".join(r.capitalize() for r in P.RULES) + " |\n|---|---|---|---|\n"
    table1 = head + "".join(f"| {LABELS[k]} | " + " | ".join(fmt(k, sample[r][k]) for r in P.RULES) + " |\n" for k in P.MEASURES)
    table2 = head + "".join(f"| {LABELS[k]} | " + " | ".join(spread(k, [per_seed[sd][r][k] for sd in SEEDS]) for r in P.RULES) + " |\n"
                            for k in P.MEASURES)
    fixed = [counts[sd].get("fixed_date", 0) for sd in SEEDS]
    note = (f"Settings: the starting values in `settings/settings.json` (40 hours a week; urgent buffer 10%, small 20%, standard 70%; "
            f"0.25 points a week waited); latest safe start, the due date less {ssd} days. The \"highest score first\" replay gives back "
            f"the history's own work log hour for hour on {'every' if same_all else 'NOT every'} history ({1 + len(SEEDS)} of "
            f"{1 + len(SEEDS)} checked)." if same_all else "")
    readme_block = "\n".join([
        f"**On the sample history (seed {doc['seed']}, {doc['weeks']} weeks, {doc['counts']['requests']} requests):**", "", table1,
        f"**The same test on the histories of seeds {SEEDS[0]} to {SEEDS[-1]}:** the median, with the lowest and highest in brackets.", "",
        table2, note])
    report = "\n".join([
        "# The rule test: three order rules on the sample history", "",
        "Made by `scripts/rule_test.py`; every week of every replay is planned by the planner's `plan_week()` (R13). Every ticket is made up: "
        "the figures show direction, not size.", "",
        readme_block, "",
        "## Each seed", "",
        "| Seed | Fixed-date items | Rule | " + " | ".join(LABELS[k] for k in P.MEASURES) + " |",
        "|---|---|---|" + "---|" * len(P.MEASURES)] +
        [f"| {sd} | {counts[sd].get('fixed_date', 0)} | {r} | " + " | ".join(fmt(k, per_seed[sd][r][k]) for k in P.MEASURES) + " |"
         for sd in SEEDS for r in P.RULES] +
        ["", f"Fixed-date items per seed: {fixed}. A seed with few fixed dates moves the \"fixed dates met\" figure a lot: one missed date "
             "out of three is 67%.", ""])
    return report, readme_block, same_all


def with_block(text: str, block: str) -> str:
    if START not in text or END not in text:
        raise LookupError("README.md has no rule-test markers")
    a, rest = text.split(START, 1)
    _, b = rest.split(END, 1)
    return f"{a}{START}\n{block}\n{END}{b}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    try:
        report, block, same = build()
        readme = with_block(README.read_text(encoding="utf-8"), block)
    except (LookupError, OSError, ValueError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    if not same:
        print("FAIL the highest-score-first replay did not give back a history's own work log")
        return 1
    if args.check:
        stale = [p.name for p, t in ((REPORT, report), (README, readme)) if not p.exists() or p.read_text(encoding="utf-8") != t]
        print("The rule test's report and README table are what the script makes." if not stale else f"OUT OF DATE {', '.join(stale)}: run python scripts/rule_test.py")
        return 1 if stale else 0
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    README.write_text(readme, encoding="utf-8")
    print(block)
    print(f"\nWrote {REPORT.relative_to(REPO)} and the table in README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
