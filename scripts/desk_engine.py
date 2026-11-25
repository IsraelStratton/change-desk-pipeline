"""Call the Change Desk engines (engine/*.js) from Python. Copied from the GTM pipeline (scripts/routing_engine.py).

The engines are JavaScript because the same files run inside the n8n Code nodes. Python reaches
them through engine/cli.js, so the triage runner, the tests and the eval all use exactly the code
that n8n runs.

    from desk_engine import Engine, PLAYBOOK
    eng = Engine("triage")
    pb = eng.call("parseTriagePlaybook", PLAYBOOK.read_text(encoding="utf-8"))
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CLI_JS = REPO / "engine" / "cli.js"
PLAYBOOK = REPO / "skills" / "triage-playbook" / "SKILL.md"
MODEL = "claude-haiku-5-5"


class EngineError(RuntimeError):
    pass


class Ref(dict):
    """Use the result of an earlier call in the same batch: Ref(0) is the first result."""

    def __init__(self, index: int):
        super().__init__({"$ref": index})


class Engine:
    """module: "triage", "scoring", "drafter", "updates" or "common"."""

    def __init__(self, module: str = "triage", node: str | None = None):
        self.node = node or shutil.which("node")
        self.module = module
        if not self.node:
            raise EngineError("node is not installed; the engines need Node.js 18 or later")

    def batch(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        payload = json.dumps({"module": self.module, "calls": [{"fn": fn, "args": args} for fn, args in calls]}, default=str)
        out = subprocess.run([self.node, str(CLI_JS)], input=payload, capture_output=True, text=True, check=False)
        if out.returncode != 0 and not out.stdout:
            raise EngineError(out.stderr.strip() or f"node exited with {out.returncode}")
        reply = json.loads(out.stdout)
        if not reply["ok"]:
            raise EngineError(reply["error"])
        return reply["results"]

    def call(self, fn: str, *args: Any) -> Any:
        return self.batch([(fn, list(args))])[0]
