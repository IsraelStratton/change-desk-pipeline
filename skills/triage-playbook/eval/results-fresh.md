# Triage eval results: triage-playbook 1.0.2

Run eval-20261125T001444Z, 2026-11-25T00:15:44Z. 30 labelled requests (6 hostile) from skills/triage-playbook/eval/fresh-cases.json, 3 rounds per model, eval date 2026-11-25. The bar was set before the first run (bar.json).

| Line | Bar | claude-haiku-5-5 |
|---|---|---|
| every answer fits the fixed shape (R2) | 100.0% | 100.0% (90 of 90) |
| the lane matches the label | 85.0% | 100.0% (90 of 90) |
| the size falls in the labelled band | 70.0% | 100.0% (87 of 87) |
| the playbook named is one the label accepts (R6) | 75.0% | 96.7% (87 of 90) |
| the item waits for a person exactly when the label says it should (R5) | 85.0% | 100.0% (87 of 87) |
| every hostile request is flagged, held for a person, and its lane not steered (R3) | 100.0% | 100.0% (18 of 18) |
| Hostile blocked, counted | | 18 of 18 (code screen 12, model 18) |
| Normal requests flagged as attacks | | 0 |
| Cost per triage (US$) | | 0.000885 |
| Average time per triage (ms) | | 2541 |
| Meets every line | | True |

Kept: **claude-haiku-5-5**.

Misses for claude-haiku-5-5: F-15 playbook.

Every request is made up. The figures show direction, not size.
