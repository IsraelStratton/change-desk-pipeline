#!/usr/bin/env python3
"""Build the Change Desk's n8n workflows from the engines and the playbook (stages 1 and 2).

  n8n/intake.json         the intake form: a request gets an id and its first status history row (R1)
  n8n/triage.json         run triage by hand: one Claude step per request in the inbox (R2 to R8)
  n8n/confirm-lanes.json  the lane confirmation form: a person confirms urgent, fixed-date,
                          low-confidence and flagged items, and accepts or rejects each split (R5, R8)
  n8n/change-score.json   the score change form: a person changes one part, with who and why (R10)
  n8n/decide.json         the decide list form: do it next, merge, or close with a reason; a close
                          drafts a message to the requester, which nobody sends (R16)

Shaped like the GTM pipeline's builders (scripts/build_n8n_routing.py): made by this script, never edited
by hand; every Code node that needs an engine gets engine/common.js and that engine pasted in whole, so
n8n runs exactly the code pytest tests; the triage playbook's text is put into the nodes that read it,
with its SHA-256 (one change from the pipeline, which mounts its playbook into the n8n container: this
build leaves the container as it is); credentials are named but carry no ID, and n8n matches them by
name and type when scripts/n8n_publish.py puts a workflow in. No workflow has a schedule: every run is
started by hand from its form.

  python scripts/build_n8n.py           # write every file
  python scripts/build_n8n.py --check   # exit 1 if any file is out of date

Exit codes: 0 done (or up to date), 1 out of date, 2 could not build.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "engine"
PLAYBOOK = REPO / "skills" / "triage-playbook" / "SKILL.md"
OUT = REPO / "n8n"
MODEL = "claude-haiku-5-5"
ANTHROPIC_VERSION = "2026-10-21"
CREDENTIALS = {
    # Reused from the GTM pipeline: the same key (Claude Console workspace gtm-pipeline, US$10 monthly limit).
    "claude": {"httpHeaderAuth": {"id": None, "name": "Claude key gtm-pipeline-v2"}},
    # New for this build: the changedesk_app login. Field values in docs/build-guide.md, part B.
    "postgres": {"postgres": {"id": None, "name": "Change Desk (Postgres)"}},
}
EXPORT_MARKER = "// ---------------------------------------------------------------- exports (not pasted into n8n)"
IMPORT_START = "// ---------------------------------------------------------------- imports (not pasted into n8n"
IMPORT_END = "// ---------------------------------------------------------------- end of imports"
NS = uuid.UUID("5b2e8c14-7d3a-4f61-9e08-c1a2b3d4e5f6")  # fixed, so the build is the same every time
FORMS = {"intake": "changedesk-intake", "triage": "changedesk-triage", "confirm": "changedesk-confirm-lanes",
         "score": "changedesk-change-score", "decide": "changedesk-decide"}
TARGETS = {
    "intake": {"file": "intake.json", "name": "Change Desk: intake form", "trigger": "Request Form", "form_path": FORMS["intake"]},
    "triage": {"file": "triage.json", "name": "Change Desk: run triage", "trigger": "Start Triage", "form_path": FORMS["triage"]},
    "confirm": {"file": "confirm-lanes.json", "name": "Change Desk: confirm lanes", "trigger": "Start Confirmation", "form_path": FORMS["confirm"]},
    "score": {"file": "change-score.json", "name": "Change Desk: change a score", "trigger": "Start Score Change", "form_path": FORMS["score"]},
    "decide": {"file": "decide.json", "name": "Change Desk: decide list", "trigger": "Start Decide List", "form_path": FORMS["decide"]},
}

INBOX_SQL = ("select request_id, source, requester_role, title, body, requester_due_date::text as requester_due_date, "
             "requester_says_breaks, requester_says_harm, arrived_at from changedesk.inbox order by arrived_at, request_id;")
GOALS_SQL = "select goal_id, title, description, active from changedesk.goals where active order by goal_id;"
SETTINGS_SQL = "select key, value from changedesk.settings order by key;"
WAITING_SQL = ("select request_id, requester_role, title, body, lane, type, size_hours::float8 as size_hours, due_date::text as due_date, "
               "due_breaks, urgent, urgent_harm, goal_id, playbook, split_proposal, confidence::float8 as confidence, triage_reason, flags, "
               "confirmation_reasons, triage_stamp, lane_waits, split_waits from changedesk.awaiting_confirmation order by arrived_at, request_id;")
RANKED_SQL = ("select rank, request_id, title, status, score::float8 as score, weeks_waited, age_points::float8 as age_points, "
              "rank_points::float8 as rank_points, do_next, awaiting_confirmation from changedesk.standard_ranked order by rank;")
WORKING_SQL = ("select w.request_id, w.part, w.points, w.reason, w.set_by, w.is_change, w.previous_points "
               "from changedesk.score_working w join changedesk.standard_ranked r using (request_id) order by w.request_id, w.part;")
DECIDE_SQL = ("select request_id, title, lane, status, requester_role, playbook, arrived_on::text as arrived_on, age_days, "
              "age_limit_days, days_over, score::float8 as score from changedesk.decide_list;")
OPEN_SQL = ("select request_id, title, playbook, status from changedesk.requests "
            "where status in ('Triaged', 'Planned', 'In progress') order by arrived_at, request_id;")
SUMMARY_SQL = ("select run_id, calls, failed, input_tokens, output_tokens, total_cost_usd::float8 as total_cost_usd, "
               "cost_per_call_usd::float8 as cost_per_call_usd from changedesk.run_summary where run_id = $1;")


def node_id(workflow: str, name: str) -> str:
    return str(uuid.uuid5(NS, f"{workflow}/{name}"))


def engine_source(*modules: str) -> str:
    """engine/common.js, then each module, without their imports and exports sections."""
    parts = []
    for m in ("common",) + modules:
        src = (ENGINE / f"{m}.js").read_text(encoding="utf-8")
        if src.count(EXPORT_MARKER) != 1:
            raise ValueError(f"engine/{m}.js must have exactly one exports marker")
        src = src.split(EXPORT_MARKER)[0]
        if m != "common":
            if src.count(IMPORT_START) != 1 or src.count(IMPORT_END) != 1:
                raise ValueError(f"engine/{m}.js must have one imports section")
            head, rest = src.split(IMPORT_START)
            src = head + rest.split(IMPORT_END, 1)[1]
        parts.append(src.rstrip() + "\n")
    return "\n".join(parts)


def playbook_block() -> str:
    text = PLAYBOOK.read_text(encoding="utf-8")
    return f"// The triage playbook ({PLAYBOOK.relative_to(REPO)}), as built. parseTriagePlaybook works out its SHA-256.\nconst PLAYBOOK_TEXT = {json.dumps(text, ensure_ascii=False)};\n"


def playbook_meta() -> dict:
    text = PLAYBOOK.read_text(encoding="utf-8")
    return {"name": re.search(r"^name: (.+)$", text, re.M)[1].strip(),
            "version": re.search(r'^\s+version: "([0-9.]+)"', text, re.M)[1]}


class Workflow:
    def __init__(self, key: str):
        self.key = key
        self.t = TARGETS[key]
        self.nodes: list[dict] = []
        self.connections: dict = {}
        self.x = 0

    def add(self, node: dict, y: int = 300) -> str:
        node = dict(node)
        node["id"] = node_id(self.key, node["name"])
        node["position"] = [self.x, y]
        self.x += 220
        self.nodes.append(node)
        return node["name"]

    def link(self, a: str, b: str, output: int = 0):
        outs = self.connections.setdefault(a, {"main": []})["main"]
        while len(outs) <= output:
            outs.append([])
        outs[output].append({"node": b, "type": "main", "index": 0})

    def chain(self, *names: str):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def build(self) -> dict:
        return {"name": self.t["name"], "nodes": self.nodes, "connections": self.connections, "settings": {"executionOrder": "v1"}}

    # ---------------------------------------------------------------- node kinds

    def trigger(self, title: str, description: str, fields: list[dict], button: str) -> str:
        # No webhookId on purpose: n8n's editor gives an imported trigger that has one a new ID and
        # overwrites its Form Path with it. scripts/n8n_publish.py gives it one (the pipeline's finding).
        return self.add({"name": self.t["trigger"], "type": "n8n-nodes-base.formTrigger", "typeVersion": 2.5,
                         "parameters": {"formTitle": title, "formDescription": description, "formFields": {"values": fields},
                                        "options": {"path": self.t["form_path"], "buttonLabel": button}}})

    def page(self, name: str, title: str, description: str, fields_from: str, button: str) -> str:
        return self.add({"name": name, "type": "n8n-nodes-base.form", "typeVersion": 2.5, "webhookId": node_id(self.key, f"{name} webhook"),
                         "parameters": {"operation": "page", "defineForm": "json", "jsonOutput": f"={{{{ $('{fields_from}').first().json.form_fields }}}}",
                                        "options": {"formTitle": title, "formDescription": description, "buttonLabel": button}}})

    def done(self, name: str = "Done") -> str:
        return self.add({"name": name, "type": "n8n-nodes-base.form", "typeVersion": 2.5, "webhookId": node_id(self.key, f"{name} webhook"),
                         "parameters": {"operation": "completion", "respondWith": "text", "completionTitle": "={{ $json.title }}",
                                        "completionMessage": "={{ $json.message }}", "options": {}}})

    def code(self, name: str, js: str, each: bool = False, y: int = 300) -> str:
        params = {"jsCode": js}
        if each:
            params["mode"] = "runOnceForEachItem"
        return self.add({"name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "parameters": params}, y)

    def pg(self, name: str, query: str, replacement: str | None = None, read: bool = False, y: int = 300) -> str:
        options = {"queryReplacement": replacement} if replacement else {}
        node = {"name": name, "type": "n8n-nodes-base.postgres", "typeVersion": 2.6, "executeOnce": True,
                "credentials": copy.deepcopy(CREDENTIALS["postgres"]),
                "parameters": {"operation": "executeQuery", "query": query, "options": options}}
        if read:
            node["alwaysOutputData"] = True
        return self.add(node, y)

    def loop(self, name: str, y: int = 300) -> str:
        return self.add({"name": name, "type": "n8n-nodes-base.splitInBatches", "typeVersion": 3,
                         "parameters": {"batchSize": 1, "options": {}}}, y)

    def claude(self, name: str, y: int = 120) -> str:
        return self.add({"name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
                         "credentials": copy.deepcopy(CREDENTIALS["claude"]), "retryOnFail": True, "maxTries": 3,
                         "waitBetweenTries": 3000, "onError": "continueRegularOutput",
                         "parameters": {"method": "POST", "url": "https://api.anthropic.com/v1/messages",
                                        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                                        "sendHeaders": True,
                                        "headerParameters": {"parameters": [{"name": "anthropic-version", "value": ANTHROPIC_VERSION}]},
                                        "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}",
                                        "options": {"response": {"response": {"fullResponse": True}}, "timeout": 120000}}}, y)

    def if_count(self, name: str, expr: str) -> str:
        return self.add({"name": name, "type": "n8n-nodes-base.if", "typeVersion": 2,
                         "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": ""}, "combinator": "and",
                                                       "conditions": [{"id": node_id(self.key, f"{name} condition"), "leftValue": f"={{{{ {expr} }}}}",
                                                                       "rightValue": 0, "operator": {"type": "number", "operation": "gt"}}]},
                                        "options": {}}})


def message_js(title: str, body: str) -> str:
    return f"// Done message\nreturn [{{ json: {{ title: {json.dumps(title)}, message: {body} }} }}];\n"


# ---------------------------------------------------------------- the five workflows

def intake() -> dict:
    w = Workflow("intake")
    w.trigger("Change Desk: ask for a change",
              "Ask the business systems team for a fix or a change. This is a made-up desk for a showcase build: use made-up details only. "
              "Your request gets an id at once. A person, helped by an AI step that only proposes, puts it in a lane; nothing is sent to anyone.",
              [{"fieldLabel": "Your role (not your name)", "fieldName": "requester_role", "fieldType": "text", "requiredField": True, "placeholder": "e.g. Support lead"},
               {"fieldLabel": "Title", "fieldName": "title", "fieldType": "text", "requiredField": True},
               {"fieldLabel": "What do you need, and why?", "fieldName": "body", "fieldType": "textarea", "requiredField": True},
               {"fieldLabel": "A date it must be done by (optional)", "fieldName": "requester_due_date", "fieldType": "date", "requiredField": False},
               {"fieldLabel": "What breaks on that date if it is not done? (optional)", "fieldName": "requester_says_breaks", "fieldType": "textarea", "requiredField": False},
               {"fieldLabel": "Is something broken now? What harm is growing while it waits? (optional)", "fieldName": "requester_says_harm", "fieldType": "textarea", "requiredField": False}],
              "Send the request")
    w.code("Make Request", """// ===== n8n node: Make Request (run once for all items) =====
// The form's answers, as the store's add_request function takes them. The text is data: nothing here reads it as instructions.
const f = $input.first().json;
const s = (k) => (f[k] === undefined || f[k] === null ? '' : String(f[k]).trim());
return [{ json: { request: {
  requester_role: s('requester_role'), title: s('title'), body: s('body'),
  requester_due_date: s('requester_due_date').slice(0, 10), requester_says_breaks: s('requester_says_breaks'),
  requester_says_harm: s('requester_says_harm'), via: `n8n intake form, execution ${$execution.id}`,
} } }];
""")
    w.pg("Add Request", "select changedesk.add_request($1::jsonb) as request_id;", "={{ JSON.stringify($json.request) }}")
    w.code("Done Message", message_js("Request received",
                                      "`Your request is ${$json.request_id}. It waits in the inbox; the desk triages it by hand, and nothing is sent to anyone.`"))
    w.done()
    w.chain(w.t["trigger"], "Make Request", "Add Request", "Done Message", "Done")
    return w.build()


TRIAGE_BUILD = """// ===== n8n node: Build Requests (run once for all items) =====
// One Claude request per request in the inbox. The text goes inside a data block, after the guard rules.
const MODEL = '__MODEL__';
const pb = parseTriagePlaybook(PLAYBOOK_TEXT);
const settings = settingsFromRows($('Read Settings').all().map((i) => i.json));
const goals = $('Read Goals').all().map((i) => i.json).filter((g) => g.goal_id);
const inbox = $('Read Inbox').all().map((i) => i.json).filter((r) => r.request_id);
const runId = `n8n-${$execution.id}`;
const today = new Date().toISOString().slice(0, 10);
if (!inbox.length) return [{ json: { count: 0, run_id: runId } }];
return inbox.map((req) => ({ json: { count: inbox.length, run_id: runId, req, settings, goals, request: buildTriageRequest(pb, req, goals, MODEL, today) } }));
"""
TRIAGE_STAMP = """// ===== n8n node: Stamp Start (run once for each item) =====
return { json: Object.assign({}, $json, { started_ms: Date.now() }) };
"""
TRIAGE_CHECK = """// ===== n8n node: Check Triage (run once for each item) =====
// The guard rails: the fixed shape, the lane rule, the confidence bar, the split, the code screen, the stamp.
let start;
try { start = $('Stamp Start').item.json; } catch (e) { start = $('Stamp Start').first().json; }
const pb = parseTriagePlaybook(PLAYBOOK_TEXT);
return { json: checkTriage(pb, start.req, $json, {
  run_id: start.run_id, source: 'n8n', model: start.request.model, settings: start.settings, goals: start.goals,
  latency_ms: Date.now() - start.started_ms, now: new Date().toISOString(),
}) };
"""
TRIAGE_COLLECT = """// ===== n8n node: Collect (run once for all items) =====
const results = $input.all().map((i) => i.json);
const proposals = results.map((r) => r.proposal);
const log = { calls: results.map((r) => r.call), proposals, handoffs: proposals.map((p) => triageHandoff(p)).filter(Boolean) };
return [{ json: { run_id: proposals.length ? proposals[0].run_id : `n8n-${$execution.id}`, log, summary: summariseTriage(proposals),
  lines: proposals.map((p) => p.output_valid
    ? `${p.request_id}: ${LANE_WORDS[p.lane]}, ${p.size_hours} h, confidence ${p.confidence}${p.needs_confirmation || p.split.length ? ' (waits for a person)' : ''}`
    : `${p.request_id}: no usable answer; it stays in the inbox`) } }];
"""
TRIAGE_DONE = """// ===== n8n node: Done Message (run once for all items) =====
const c = $('Collect').first().json;
const s = $input.first().json || {};
const m = c.summary;
const cost = s.total_cost_usd === undefined || s.total_cost_usd === null ? 'not found in the run log'
  : `US$${Number(s.total_cost_usd).toFixed(6)} for ${s.calls} calls`;
return [{ json: { title: m.failed ? 'Triage finished, with failures' : 'Triage complete', message: [
  `Run ${c.run_id}: ${m.triaged} requests put in lanes (urgent ${m.by_lane.urgent}, fixed date ${m.by_lane.fixed_date}, standard ${m.by_lane.standard}, small ${m.by_lane.small}).`,
  m.failed ? `${m.failed} had no usable answer and stay in the inbox.` : 'Every answer fitted the fixed shape.',
  `${m.wait_for_a_person} wait for a person: open /form/__CONFIRM__ to confirm them. ${m.flagged_injection} were flagged as trying to instruct the AI.`,
  `AI cost: ${cost}. ${c.lines.join(' · ')}`,
].join(' ') } }];
"""


def triage() -> dict:
    w = Workflow("triage")
    w.trigger("Change Desk: run triage",
              "Triage every request in the inbox. One AI step per request proposes its lane, size, the two lane tests, a goal, a playbook, "
              "score parts and a reason. Urgent, fixed-date, low-confidence and flagged items wait for a person on the confirmation form. "
              "Started by hand only; nothing is sent to anyone.",
              [{"fieldLabel": "What to triage", "fieldName": "scope", "fieldType": "dropdown", "requiredField": True,
                "fieldOptions": {"values": [{"option": "Every request in the inbox"}]}}],
              "Run triage")
    w.pg("Read Inbox", INBOX_SQL, read=True)
    w.pg("Read Goals", GOALS_SQL, read=True)
    w.pg("Read Settings", SETTINGS_SQL, read=True)
    engine = engine_source("triage")
    pbk = playbook_block()
    w.code("Build Requests", engine + pbk + TRIAGE_BUILD.replace("__MODEL__", MODEL))
    w.if_count("Anything to Triage?", "$json.count")
    w.loop("Loop Over Requests")
    w.code("Stamp Start", TRIAGE_STAMP, each=True, y=120)
    w.claude("Claude Triage Step")
    w.code("Check Triage", engine + pbk + TRIAGE_CHECK, each=True, y=120)
    w.code("Collect", engine + TRIAGE_COLLECT)
    w.pg("Log Triage", "select changedesk.log_triage(($1::jsonb)->'calls', ($1::jsonb)->'proposals', ($1::jsonb)->'handoffs') as triaged;",
         "={{ JSON.stringify($json.log) }}")
    w.pg("Read Run Summary", SUMMARY_SQL, "={{ $('Collect').first().json.run_id }}", read=True)
    w.code("Done Message", TRIAGE_DONE.replace("__CONFIRM__", FORMS["confirm"]))
    w.code("Nothing Message", message_js("Nothing to triage", "'The inbox is empty: every request has been triaged.'"), y=520)
    w.done()
    w.chain(w.t["trigger"], "Read Inbox", "Read Goals", "Read Settings", "Build Requests", "Anything to Triage?")
    w.link("Anything to Triage?", "Loop Over Requests", 0)
    w.link("Anything to Triage?", "Nothing Message", 1)
    w.link("Loop Over Requests", "Collect", 0)  # output 0 is done, 1 is the loop
    w.link("Loop Over Requests", "Stamp Start", 1)
    w.chain("Stamp Start", "Claude Triage Step", "Check Triage", "Loop Over Requests")
    w.chain("Collect", "Log Triage", "Read Run Summary", "Done Message", "Done")
    w.link("Nothing Message", "Done")
    return w.build()


def confirm() -> dict:
    w = Workflow("confirm")
    meta = playbook_meta()
    w.trigger("Change Desk: confirm lanes",
              "Every request that waits for a person: urgent, fixed-date, low-confidence or flagged, and every proposed split. "
              "Confirm or change each lane, and accept or reject each split. Your name and reason go into the log with a stamp.",
              [{"fieldLabel": "What to confirm", "fieldName": "scope", "fieldType": "dropdown", "requiredField": True,
                "fieldOptions": {"values": [{"option": "Every request that waits for a person"}]}}],
              "Show what waits")
    w.pg("Read Waiting", WAITING_SQL, read=True)
    engine = engine_source("triage")
    w.code("Build Form", engine + """// ===== n8n node: Build Form (run once for all items) =====
const pending = $input.all().map((i) => i.json).filter((r) => r.request_id);
return [{ json: { count: pending.length, run_id: `n8n-${$execution.id}`, pending, form_fields: pending.length ? buildConfirmForm(pending, { run_id: `n8n-${$execution.id}` }) : [] } }];
""")
    w.if_count("Anything Waiting?", "$json.count")
    w.page("Lane Confirmation", "Confirm the lanes", "Nothing is planned until you confirm. Your choices are stamped with your name.", "Build Form",
           "Record my decisions")
    w.code("Apply Choices", engine + f"""// ===== n8n node: Apply Choices (run once for all items) =====
const b = $('Build Form').first().json;
const rows = applyConfirmations(b.pending, $input.first().json, {{ run_id: b.run_id, decided_at: new Date().toISOString(),
  playbook: {{ name: '{meta['name']}', version: '{meta['version']}' }} }});
return [{{ json: {{ run_id: b.run_id, rows, waiting: b.count }} }}];
""")
    w.pg("Confirm Lanes", "select changedesk.confirm_lanes($1::jsonb) as recorded;", "={{ JSON.stringify($json.rows) }}")
    w.code("Done Message", """// ===== n8n node: Done Message (run once for all items) =====
const a = $('Apply Choices').first().json;
const lanes = a.rows.filter((r) => r.kind === 'lane');
const splits = a.rows.filter((r) => r.kind === 'split');
return [{ json: { title: 'Decisions recorded', message: [
  `Run ${a.run_id}: ${lanes.filter((r) => r.action === 'confirmed').length} lanes confirmed, ${lanes.filter((r) => r.action === 'changed').length} changed;`,
  `${splits.filter((r) => r.action === 'accepted').length} splits accepted, ${splits.filter((r) => r.action === 'rejected').length} rejected.`,
  `Each decision carries a stamp with your name; look it up in changedesk.decisions.`,
].join(' ') } }];
""")
    w.code("Nothing Message", message_js("Nothing waits", "'No request waits for a person.'"), y=520)
    w.done()
    w.chain(w.t["trigger"], "Read Waiting", "Build Form", "Anything Waiting?")
    w.link("Anything Waiting?", "Lane Confirmation", 0)
    w.link("Anything Waiting?", "Nothing Message", 1)
    w.chain("Lane Confirmation", "Apply Choices", "Confirm Lanes", "Done Message", "Done")
    w.link("Nothing Message", "Done")
    return w.build()


def score() -> dict:
    w = Workflow("score")
    w.trigger("Change Desk: change a score",
              "The standard lane, ranked by score plus points for each week waited, with each part's reason. Change one part of one item: "
              "the change is logged with your name and reason, and the old value is kept.",
              [{"fieldLabel": "Lane", "fieldName": "scope", "fieldType": "dropdown", "requiredField": True,
                "fieldOptions": {"values": [{"option": "Standard lane"}]}}],
              "Show the ranked lane")
    w.pg("Read Ranked", RANKED_SQL, read=True)
    w.pg("Read Working", WORKING_SQL, read=True)
    engine = engine_source("scoring")
    w.code("Build Form", engine + """// ===== n8n node: Build Form (run once for all items) =====
const ranked = $('Read Ranked').all().map((i) => i.json).filter((r) => r.request_id);
const working = $('Read Working').all().map((i) => i.json).filter((r) => r.request_id);
return [{ json: { count: ranked.length, run_id: `n8n-${$execution.id}`, ranked, working, form_fields: ranked.length ? buildScoreForm(ranked, working, { run_id: `n8n-${$execution.id}` }) : [] } }];
""")
    w.if_count("Anything Ranked?", "$json.count")
    w.page("Score Change", "Change one part of a score", "One part of one item per submission. The old value is kept.", "Build Form", "Record the change")
    w.code("Apply Change", engine + """// ===== n8n node: Apply Change (run once for all items) =====
const b = $('Build Form').first().json;
const out = applyScoreChange(b.ranked, b.working, $input.first().json, { run_id: b.run_id, decided_at: new Date().toISOString() });
return [{ json: Object.assign({ run_id: b.run_id }, out) }];
""")
    w.pg("Change Score", "select changedesk.change_score($1::jsonb) as recorded;", "={{ JSON.stringify($json.rows) }}")
    w.code("Done Message", """// ===== n8n node: Done Message (run once for all items) =====
const a = $('Apply Change').first().json;
return [{ json: { title: a.rows.length ? 'Score changed' : 'No change', message: `${a.message} Run ${a.run_id}.` } }];
""")
    w.code("Nothing Message", message_js("Nothing to rank", "'The standard lane has no waiting items.'"), y=520)
    w.done()
    w.chain(w.t["trigger"], "Read Ranked", "Read Working", "Build Form", "Anything Ranked?")
    w.link("Anything Ranked?", "Score Change", 0)
    w.link("Anything Ranked?", "Nothing Message", 1)
    w.chain("Score Change", "Apply Change", "Change Score", "Done Message", "Done")
    w.link("Nothing Message", "Done")
    return w.build()


def decide() -> dict:
    w = Workflow("decide")
    w.trigger("Change Desk: decide list",
              "Every item past its lane's age limit. Decide each one: do it next, merge it, or close it with a reason. "
              "A close drafts a message to the requester for a person to approve later; nothing is sent to anyone.",
              [{"fieldLabel": "List", "fieldName": "scope", "fieldType": "dropdown", "requiredField": True,
                "fieldOptions": {"values": [{"option": "Items past their age limit"}]}}],
              "Show the decide list")
    w.pg("Read Decide List", DECIDE_SQL, read=True)
    w.pg("Read Open Items", OPEN_SQL, read=True)
    scoring = engine_source("scoring")
    drafter = engine_source("drafter")
    w.code("Build Form", scoring + """// ===== n8n node: Build Form (run once for all items) =====
const list = $('Read Decide List').all().map((i) => i.json).filter((r) => r.request_id);
const open = $('Read Open Items').all().map((i) => i.json).filter((r) => r.request_id);
return [{ json: { count: list.length, run_id: `n8n-${$execution.id}`, list, open, form_fields: list.length ? buildDecideForm(list, open, { run_id: `n8n-${$execution.id}` }) : [] } }];
""")
    w.if_count("Anything Past Its Limit?", "$json.count")
    w.page("Decide", "Decide the old items", "Do it next, merge, or close with a reason. Nothing is sent to anyone.", "Build Form", "Record my decisions")
    w.code("Apply Choices", scoring + """// ===== n8n node: Apply Choices (run once for all items) =====
const b = $('Build Form').first().json;
const rows = applyDecideChoices(b.list, b.open, $input.first().json, { run_id: b.run_id, decided_at: new Date().toISOString() });
return [{ json: { run_id: b.run_id, rows } }];
""")
    w.pg("Record Decisions", "select changedesk.decide($1::jsonb) as closed;", "={{ JSON.stringify($json.rows) }}")
    w.code("Build Drafts", drafter + f"""// ===== n8n node: Build Drafts (run once for all items) =====
// One message draft per closed item. The drafter sees the title, the role and the reason: no score, no request text.
const MODEL = '{MODEL}';
const a = $('Apply Choices').first().json;
const closed = ($input.first().json.closed || []);
if (!closed.length) return [{{ json: {{ count: 0, run_id: a.run_id }} }}];
return closed.map((c) => ({{ json: {{ count: closed.length, run_id: a.run_id, closed: c, request: buildCloseDraftRequest(c, MODEL) }} }}));
""")
    w.if_count("Anything Closed?", "$json.count")
    w.loop("Loop Over Closes")
    w.code("Stamp Start", TRIAGE_STAMP, each=True, y=120)
    w.claude("Claude Message Drafter")
    w.code("Check Draft", drafter + """// ===== n8n node: Check Draft (run once for each item) =====
// The draft is checked in code before anyone sees it: the request id is named, no internal codes, no promise, no contact details.
let start;
try { start = $('Stamp Start').item.json; } catch (e) { start = $('Stamp Start').first().json; }
return { json: checkCloseDraft(start.closed, $json, { run_id: start.run_id, source: 'n8n', model: start.request.model,
  latency_ms: Date.now() - start.started_ms, now: new Date().toISOString() }) };
""", each=True, y=120)
    w.code("Collect Drafts", """// ===== n8n node: Collect Drafts (run once for all items) =====
const r = $input.all().map((i) => i.json);
const log = { calls: r.map((x) => x.call), drafts: r.map((x) => x.draft).filter(Boolean), handoffs: r.map((x) => x.handoff).filter(Boolean) };
return [{ json: { run_id: r.length ? r[0].call.run_id : '', log, drafted: log.drafts.length, failed: r.length - log.drafts.length,
  with_problems: log.drafts.filter((d) => d.draft_problems).length } }];
""")
    w.pg("Log Drafts", "select changedesk.log_drafts(($1::jsonb)->'calls', ($1::jsonb)->'drafts', ($1::jsonb)->'handoffs') as drafted;",
         "={{ JSON.stringify($json.log) }}")
    w.code("Done Message", """// ===== n8n node: Done Message (run once for all items) =====
const a = $('Apply Choices').first().json;
const d = $('Collect Drafts').first().json;
const n = (k) => a.rows.filter((r) => r.action === k).length;
return [{ json: { title: 'Decisions recorded', message: [
  `Run ${a.run_id}: ${n('do_next')} to do next, ${n('merge')} merged, ${n('close')} closed.`,
  `${d.drafted} close messages drafted for a person to approve (${d.with_problems} flagged by the draft check${d.failed ? `, ${d.failed} drafts failed` : ''}). Nothing was sent.`,
].join(' ') } }];
""")
    w.code("No Close Message", """// ===== n8n node: No Close Message (run once for all items) =====
const a = $('Apply Choices').first().json;
const n = (k) => a.rows.filter((r) => r.action === k).length;
return [{ json: { title: 'Decisions recorded', message: `Run ${a.run_id}: ${n('do_next')} to do next, ${n('merge')} merged, nothing closed, so nothing drafted.` } }];
""", y=520)
    w.code("Nothing Message", message_js("Nothing past its limit", "'No item is past its lane\\'s age limit.'"), y=520)
    w.done()
    w.chain(w.t["trigger"], "Read Decide List", "Read Open Items", "Build Form", "Anything Past Its Limit?")
    w.link("Anything Past Its Limit?", "Decide", 0)
    w.link("Anything Past Its Limit?", "Nothing Message", 1)
    w.chain("Decide", "Apply Choices", "Record Decisions", "Build Drafts", "Anything Closed?")
    w.link("Anything Closed?", "Loop Over Closes", 0)
    w.link("Anything Closed?", "No Close Message", 1)
    w.link("Loop Over Closes", "Collect Drafts", 0)
    w.link("Loop Over Closes", "Stamp Start", 1)
    w.chain("Stamp Start", "Claude Message Drafter", "Check Draft", "Loop Over Closes")
    w.chain("Collect Drafts", "Log Drafts", "Done Message", "Done")
    w.link("No Close Message", "Done")
    w.link("Nothing Message", "Done")
    return w.build()


BUILDERS = {"intake": intake, "triage": triage, "confirm": confirm, "score": score, "decide": decide}


def render(wf: dict) -> str:
    return json.dumps(wf, indent=2, ensure_ascii=False) + "\n"


def build(key: str) -> dict:
    return BUILDERS[key]()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if any workflow file is out of date")
    args = ap.parse_args(argv)
    try:
        texts = {k: render(build(k)) for k in TARGETS}
    except (OSError, ValueError, KeyError) as e:
        print(f"CANNOT BUILD {e}")
        return 2
    if args.check:
        stale = [TARGETS[k]["file"] for k, text in texts.items()
                 if not (OUT / TARGETS[k]["file"]).exists() or (OUT / TARGETS[k]["file"]).read_text(encoding="utf-8") != text]
        for f in stale:
            print(f"OUT OF DATE n8n/{f}: run python scripts/build_n8n.py")
        if not stale:
            print(f"All {len(texts)} workflow files are up to date.")
        return 1 if stale else 0
    OUT.mkdir(exist_ok=True)
    for k, text in texts.items():
        (OUT / TARGETS[k]["file"]).write_text(text, encoding="utf-8")
        print(f"Wrote n8n/{TARGETS[k]['file']}: {len(json.loads(text)['nodes'])} nodes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
