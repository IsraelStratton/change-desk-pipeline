"""scripts/sync_tracker.py, the Notion tracker board (stage 3), with no key and no network: Notion is replaced by a fake
that records every call. The board's property names and options are the reviewer's, read from the board on 25/11/2026.
The script checks them before it writes, maps the store's values to them, upserts by Request ID, never deletes, writes
roles never names, and never prints a secret."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_tracker as T  # noqa: E402

DB, DS = "db-test", "ds-test"


def board():
    """The data source as Notion's API returns it: properties by name, with type and options."""
    props = {}
    for name, kind in T.PROPERTIES.items():
        p = {"id": name[:4], "name": name, "type": kind, kind: {}}
        if name in T.OPTIONS:
            p[kind] = {"options": [{"id": o[:3], "name": o, "color": "default"} for o in sorted(T.OPTIONS[name])]}
        props[name] = p
    props["Notes (the reviewer)"] = {"id": "x", "name": "Notes (the reviewer)", "type": "rich_text", "rich_text": {}}
    return {"object": "data_source", "id": DS, "properties": props}


def row(**over):
    r = {"request_id": "CD-0016", "title": "Clean up duplicate Order records", "lane": "standard", "status": "Triaged", "type": "enhancement",
         "size_hours": 13, "requester_role": "Head of operations", "goal_id": "G2", "goal": "Keep customer data accurate",
         "playbook": "crm-data-dedupe-merge", "triage_reason": "About 13 hours, no date, no harm growing: standard.", "close_reason": None,
         "confidence": 0.89, "due_date": None, "due_breaks": None, "urgent_harm": None, "no_goal": False, "awaiting_confirmation": False,
         "lane_confirmed_by": None, "rank_points": 9.15, "age_days": 125, "past_age_limit": False, "planned_week": "2026-11-23",
         "forecast_kind": "date_range", "p50": "2026-12-01", "p85": "2026-12-02", "p95": "2026-12-03", "service_level_days": None,
         "chance": None, "latest_safe_start": None, "forecast_note": ""}
    r.update(over)
    return r


class FakeNotion:
    def __init__(self, ds=None, pages=None, owner=DS):
        self.ds, self.pages_, self.owner = ds or board(), pages or [], owner
        self.calls = []

    def database(self, db):
        self.calls.append(("database", db))
        return {"data_sources": [{"id": self.owner, "name": "tracker"}]}

    def data_source(self, ds):
        self.calls.append(("data_source", ds))
        return self.ds

    def pages(self, ds):
        self.calls.append(("pages", ds))
        return self.pages_

    def create(self, ds, properties):
        self.calls.append(("create", ds, properties))
        return {"id": "new"}

    def update(self, page_id, properties):
        self.calls.append(("update", page_id, properties))
        return {"id": page_id}


def as_page(pid, want, created="2026-11-25T00:00:00Z"):
    """A board row as Notion returns it, from the values wanted() gives."""
    props = {}
    for k, v in want.items():
        kind = T.PROPERTIES[k]
        n = T.to_notion(k, v)
        if kind in ("title", "rich_text"):
            n[kind] = [dict(t, plain_text=t["text"]["content"]) for t in n[kind]]
        props[k] = dict(n, type=kind)
    return {"object": "page", "id": pid, "created_time": created, "properties": props}


def writes(fake):
    return [c for c in fake.calls if c[0] in ("create", "update")]


def test_the_board_check_passes_on_the_board_as_built():
    assert T.board_problems(board()) == []


@pytest.mark.parametrize("change,problem", [
    (lambda b: b["properties"].pop("Forecast"), "property 'Forecast' is missing"),
    (lambda b: b["properties"]["Score"].update(type="rich_text"), "property 'Score' is a rich_text, not a number"),
    (lambda b: b["properties"]["Status"]["select"]["options"].pop(0), "property 'Status' has no option"),
])
def test_a_missing_or_wrong_property_stops_the_sync_before_any_write(change, problem):
    b = board()
    change(b)
    assert any(p.startswith(problem) for p in T.board_problems(b))
    fake = FakeNotion(ds=b)
    code, lines = T.sync(fake, DB, DS, [row()], "sync")
    assert code == 1 and "nothing was written" in lines[0] and "the reviewer owns the board" in lines[0]
    assert writes(fake) == [] and ("pages", DS) not in fake.calls


def test_a_data_source_that_is_not_the_boards_own_writes_nothing():
    fake = FakeNotion(owner="someone-else")
    code, lines = T.sync(fake, DB, DS, [row()], "sync")
    assert code == 1 and writes(fake) == []


def test_the_stores_values_map_to_the_boards_names_exactly():
    w = T.wanted(row())
    assert set(w) == set(T.PROPERTIES)
    assert (w["Lane"], w["Status"], w["Type"], w["Score"], w["Planned week"]) == ("Standard", "Triaged", "Enhancement", 9.15, "Week of 23/11/2026")
    assert w["Forecast"] == "50% by 01/12/2026 · 85% by 02/12/2026 · 95% by 03/12/2026"
    assert T.wanted(row(lane="small", status="Closed", rank_points=None))["Status"] == "Closed with a reason"
    assert {T.LANE[k] for k in T.LANE} == T.OPTIONS["Lane"] and set(T.STATUS.values()) == T.OPTIONS["Status"]
    fixed = T.wanted(row(lane="fixed_date", forecast_kind="chance_of_date", chance=0.62, latest_safe_start="2026-11-27", due_date="2026-12-04",
                         p50=None, p85=None, p95=None, rank_points=None))
    assert fixed["Forecast"] == "62% chance of 04/12/2026 · latest safe start 27/11/2026" and fixed["Due date"] == "2026-12-04"
    small = T.wanted(row(lane="small", forecast_kind="service_level", service_level_days=17, p50=None, p85=None, p95=None, rank_points=None))
    assert small["Forecast"] == "Service level: 85% of small items done within 17 days"
    assert T.wanted(row(status="Done"))["Forecast"] == "" and T.wanted(row(status="Done"))["Planned week"] == ""
    assert T.wanted(row(playbook="none"))["Playbook"] == "none fits" and T.wanted(row(goal_id=None, no_goal=True))["Goal"] == ""


def test_roles_only_never_a_reviewers_label_or_contact_details():
    assert T.confirmed_by(row(lane_confirmed_by="Jordan Example")) == "Desk reviewer"
    assert T.confirmed_by(row(lane_confirmed_by="courses-2nd (delegated)")) == "Desk reviewer (delegated test run)"
    assert T.confirmed_by(row(lane_confirmed_by="history (made-up)")) == "Made-up history"
    assert T.confirmed_by(row(awaiting_confirmation=True)) == "Waits for a person"
    assert T.confirmed_by(row()) == "Not needed: the lane rule set it" and T.confirmed_by(row(status="New")) == ""
    w = T.wanted(row(requester_role="Sales manager, call 0412 345 678", title="Ask pat@example.com about the report"))
    assert "0412" not in w["Asked by (role)"] and "pat@" not in w["Request"] and "[contact details withheld]" in w["Request"]
    assert len(T.wanted(row(triage_reason="x" * 5000))["Reason"]) == T.MAX_TEXT


def test_the_first_sync_creates_one_row_per_request_with_the_data_source_as_parent():
    fake = FakeNotion()
    code, lines = T.sync(fake, DB, DS, [row(), row(request_id="CD-0020", title="Refresh the test sandbox")], "sync")
    made = [c for c in fake.calls if c[0] == "create"]
    assert code == 0 and len(made) == 2 and {c[1] for c in made} == {DS}
    props = made[0][2]
    assert props["Request"] == {"title": [{"type": "text", "text": {"content": "Clean up duplicate Order records"}}]}
    assert props["Lane"] == {"select": {"name": "Standard"}} and props["Past age limit"] == {"checkbox": False}
    assert props["Due date"] == {"date": None} and props["Score"] == {"number": 9.15}
    assert "Created 2, updated 0" in lines[-1] and "Nothing deleted" in lines[-1]


def test_a_second_sync_updates_only_what_changed_and_deletes_nothing():
    first = T.wanted(row())
    pages = [as_page("p1", first), as_page("p9", T.wanted(row(request_id="CD-9999", title="Made on the board by hand")))]
    fake = FakeNotion(pages=pages)
    code, lines = T.sync(fake, DB, DS, [row(age_days=126, status="Planned")], "sync")
    ups = [c for c in fake.calls if c[0] == "update"]
    assert code == 0 and len(ups) == 1 and ups[0][1] == "p1" and set(ups[0][2]) == {"Age (days)", "Status"}
    assert not [c for c in fake.calls if c[0] == "create"]
    assert any("1 rows whose Request ID is not in the store" in line for line in lines)
    fake2 = FakeNotion(pages=[as_page("p1", first)])
    T.sync(fake2, DB, DS, [row()], "sync")
    assert writes(fake2) == []


def test_a_dry_run_reads_both_sides_and_writes_nothing():
    fake = FakeNotion(pages=[as_page("p1", T.wanted(row()))])
    code, lines = T.sync(fake, DB, DS, [row(age_days=200), row(request_id="CD-0020")], "dry-run")
    assert code == 0 and writes(fake) == [] and "To create 1, to update 1" in lines[1] and "Age (days)" in lines[-1]


def test_a_duplicate_request_id_updates_the_oldest_row_and_reports_the_rest():
    old, new = as_page("old", T.wanted(row(age_days=1)), "2026-11-25T00:00:00Z"), as_page("new", T.wanted(row(age_days=2)), "2026-11-26T00:00:00Z")
    fake = FakeNotion(pages=[new, old])
    code, lines = T.sync(fake, DB, DS, [row()], "sync")
    assert [c[1] for c in fake.calls if c[0] == "update"] == ["old"] and any("more than one row" in line for line in lines)


def test_no_key_means_no_run_and_nothing_printed(capsys):
    assert T.main([], env={}) == 2
    out = capsys.readouterr().out
    assert "CANNOT RUN" in out and "NOTION_CHANGEDESK_TOKEN" in out


def test_a_notion_error_never_prints_the_key(capsys):
    class Resp:
        status_code, content, headers, text = 401, b"x", {}, ""

        @staticmethod
        def json():
            return {"object": "error", "status": 401, "code": "unauthorized", "message": "API token secret_abc123 is invalid."}

    class Session:
        def request(self, *a, **k):
            return Resp()

    client = T.Notion("secret_abc123", session=Session(), pause=0)
    with pytest.raises(T.NotionError) as e:
        client.data_source(DS)
    assert "secret_abc123" not in str(e.value) and "<hidden>" in str(e.value)


def test_the_client_uses_the_current_api_version_and_the_data_source_query():
    seen = []

    class Resp:
        status_code, headers = 200, {}

        def __init__(self, body):
            self.body, self.content = body, b"{}"

        def json(self):
            return self.body

    class Session:
        def request(self, method, url, headers=None, json=None, timeout=None):
            seen.append((method, url, copy.deepcopy(headers), json))
            more = len(seen) == 1
            return Resp({"results": [{"object": "page", "id": str(len(seen))}], "has_more": more, "next_cursor": "c1" if more else None})

    pages = T.Notion("k", session=Session(), pause=0).pages(DS)
    assert [p["id"] for p in pages] == ["1", "2"]
    assert seen[0][0] == "POST" and seen[0][1].endswith(f"/v1/data_sources/{DS}/query") and seen[1][3]["start_cursor"] == "c1"
    assert seen[0][2]["Notion-Version"] == "2026-03-11" and seen[0][2]["Authorization"] == "Bearer k"
