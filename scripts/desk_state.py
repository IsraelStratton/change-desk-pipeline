"""Read the Change Desk's open work, settings and history from the store, as the planner's items (stages 3 and 4).

Used by scripts/plan_week.py, scripts/forecast.py and scripts/health_report.py, as the app's own login (read only).
The planner itself (scripts/planner.py) never touches the store, so the rule test and the back-check run on the
sample history file with no database, in CI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import desk_db
import planner as P

OPEN_SQL = """
select r.request_id, r.lane, r.status, r.title, r.requester_role, r.size_hours::float8 as size, r.arrived_at, r.due_date,
  r.do_next, (r.needs_confirmation and r.lane_confirmed_by is null) as lane_waits,
  (r.split_proposal is not null and jsonb_array_length(r.split_proposal) > 0 and r.split_decision is null) as split_waits,
  t.score::float8 as score, v.points as value, coalesce(w.logged, 0)::float8 as logged
from changedesk.requests r
left join changedesk.score_totals t on t.request_id = r.request_id
left join changedesk.current_scores v on v.request_id = r.request_id and v.part = 'value'
left join (select request_id, sum(hours) as logged from changedesk.work_log group by request_id) w on w.request_id = r.request_id
where r.status in ('Triaged', 'Planned', 'In progress') and r.lane is not null
order by r.arrived_at, r.request_id
"""

# Every triaged request but a split's parent (its pieces stand for it), for each lane's own history of arrivals.
ARRIVALS_SQL = """
select r.request_id, r.lane, r.size_hours::float8 as size, r.arrived_at, r.due_date, t.score::float8 as score, v.points as value
from changedesk.requests r
left join changedesk.score_totals t on t.request_id = r.request_id
left join changedesk.current_scores v on v.request_id = r.request_id and v.part = 'value'
where r.lane is not null and r.status <> 'Split'
"""

SPANS_SQL = """
select w.request_id, w.week_start from changedesk.work_log w join changedesk.requests r on r.request_id = w.request_id
where r.lane = 'fixed_date' and r.status = 'Done'
"""


@dataclass
class DeskState:
    settings: dict
    items: list[P.Item]                       # open work the planner may plan
    waiting: list[dict] = field(default_factory=list)   # open work that waits for a person (lane or split)
    rows: dict[str, dict] = field(default_factory=dict)  # every open row as read, by id
    spans: list[int] = field(default_factory=list)
    first_week: date | None = None
    assumed_left: list[str] = field(default_factory=list)

    def plan_settings(self) -> P.PlanSettings:
        return P.PlanSettings.from_settings(self.settings, self.safe_start_days())

    def safe_start_days(self) -> int:
        return P.safe_start_days(self.spans, float(self.settings["latest_safe_start_percentile"]))


def item_of(r: dict) -> P.Item:
    return P.Item(r["request_id"], r["lane"], float(r["size"]), float(r["size"]), P.parse_ts(r["arrived_at"]),
                  float(r["score"] or 0), float(r["value"] or 0), date.fromisoformat(r["due_date"]) if r.get("due_date") else None,
                  bool(r.get("do_next")), r.get("status") or "Triaged", r.get("title") or "")


def load(conn) -> DeskState:
    settings = {s["key"]: s["value"] for s in desk_db.settings(conn)}
    st = DeskState(settings, [])
    for r in desk_db.rows(conn, OPEN_SQL):
        st.rows[r["request_id"]] = r
        if r["lane_waits"] or r["split_waits"]:
            st.waiting.append(r)
            continue
        it = item_of(r)
        it.left = it.size - float(r["logged"])
        if it.left <= 0:
            # Logged hours reached the size but the item is not done: half an hour is taken to finish it.
            it.left = 0.5
            st.assumed_left.append(it.request_id)
        st.items.append(it)
    st.spans = P.work_spans(desk_db.rows(conn, SPANS_SQL), {r["request_id"] for r in desk_db.rows(conn, SPANS_SQL)})
    first = conn.execute("select min(week_start) as w from changedesk.work_log").fetchone()["w"]
    st.first_week = first
    return st


def arrivals(conn) -> list[P.Item]:
    return [item_of(dict(r, status="Done")) for r in desk_db.rows(conn, ARRIVALS_SQL)]


def history_weeks(st: DeskState, start_week: date) -> int:
    """The whole weeks of history before the start week, from the first week work was logged."""
    if st.first_week is None:
        return 0
    return max(0, (start_week - st.first_week).days // 7)
