"""The export check (scripts/clean_exports.py, copied from the GTM pipeline and cut to n8n): every committed
workflow file is clean, and the check catches what it should. Samples are built at run time."""
import json
import sys

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import build_n8n  # noqa: E402
import clean_exports as ce  # noqa: E402


def test_every_workflow_file_is_clean():
    files = ce.workflow_files()
    assert sorted(files) == sorted(f"n8n/{t['file']}" for t in build_n8n.TARGETS.values())  # all six, stage 5's approval form too
    assert ce.check_all(ce.tree_reader(), None, files) == []


def test_the_check_finds_instance_data_ids_keys_and_addresses():
    at = "@"
    wf = {"name": "x", "id": "abc", "nodes": [{"name": "n", "credentials": {"postgres": {"id": "7Yq2", "name": "c"}}, "parameters": {}}],
          "connections": {}, "settings": {"executionOrder": "v1", "errorWorkflow": "9"}}
    text = json.dumps(wf) + " sk-ant-" + "api03-abcdefghijklmnop owner" + at + "gmail.com"
    found = ce.n8n_findings(wf) + ce.text_findings(text)
    assert "instance data at the top: id" in found
    assert "node n: a credential ID (postgres)" in found
    assert "an instance setting (errorWorkflow)" in found
    assert "a Claude API key" in found and "an email address" in found
    assert ce.text_findings("desk" + at + "freight.example") == []


def test_the_cleaner_drops_instance_data():
    raw = {"name": "x", "id": "1", "versionId": "v", "nodes": [{"name": "n", "id": "q", "webhookId": "w",
           "credentials": {"postgres": {"id": "7Yq2", "name": "Change Desk (Postgres)"}}, "parameters": {}}],
           "connections": {}, "settings": {"executionOrder": "v1", "timeSavedPerExecution": 3}}
    clean = ce.clean_n8n(raw)
    assert set(clean) == {"name", "nodes", "connections", "settings"}
    assert clean["nodes"][0]["credentials"]["postgres"]["id"] is None
    assert ce.export_findings(json.dumps(clean)) == []
