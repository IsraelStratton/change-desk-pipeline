"""The Change Desk's planner: a plain script, not a model (KB-139 stage 3, R12 to R14), and the forecast and rule test
that run on it (stage 4, R18 to R21, R26).

R13, one piece of code: plan_week() below makes every week's plan there is. The week's plan (scripts/plan_week.py) is
one call of it. The forecast (scripts/forecast.py) and the back-check (scripts/back_check.py) call it for every week of
every run, with new arrivals drawn from each lane's own history. The rule test (scripts/rule_test.py) calls it for every
week of the sample history under each of three order rules. No other file holds a copy of any rule. The standard lane's
order (standard_order) is the store's changedesk.ranked_standard, and tests/test_planner_db.py checks they agree.

The lanes rule (R12), one week of hours (setting hours_per_week):
  1. Urgent first, one at a time, oldest first. The urgent buffer (urgent_buffer_share of the week) is what urgent work
     is expected to take; it takes more if it must, and the plan says how many hours beyond the buffer it took.
  2. Fixed-date items from their latest safe start: an item whose latest safe start falls in this week or earlier
     (its due date less the time such work has needed 85% of the time, safe_start_days) is planned next, earliest due
     date first.
  3. The small lane's reserved share (small_share of the week), oldest first.
  4. Standard work by score plus age (standard_share of the week): "do it next" from the decide list first, then rank
     points, the score plus age_points_per_week for each whole week waited.
  5. Unused hours flow to the other lanes: on down the standard order, then the small lane, then fixed-date work
     ahead of its latest safe start.
Everything comes from the settings the caller passes in: change a setting and the next plan changes (R14).

The two older rules, for the rule test (KB-136 section 6.6): "highest score first" (urgent counts as 10) is how the
made-up history was worked (scripts/make_history.py), and the rule test checks it reproduces that history hour for
hour; "value per hour first" puts urgent work first, then the value part per hour of size.

Pure functions and plain data only: no database, no network, no clock. All data is made up.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone

PLANNER_VERSION = "1.0.0"
LANES = ("urgent", "fixed_date", "small", "standard")
LANE_WORDS = {"urgent": "Urgent", "fixed_date": "Fixed date", "small": "Small and quick", "standard": "Standard"}
RULES = ("highest score first", "value per hour first", "lanes")
OPEN_STATUSES = ("Triaged", "Planned", "In progress")
SCORE_PARTS = ("value", "effort", "risk", "goal_fit", "readiness")
TEAM_TZ = timezone(timedelta(hours=11))  # the made-up team works in Sydney summer time, as in scripts/make_history.py
WORKDAYS = 5
EPS = 1e-9


# ---------------------------------------------------------------- items and settings

@dataclass
class Item:
    """One piece of open work. left: the hours still to do. score: the five-part score (no age points)."""
    request_id: str
    lane: str
    size: float
    left: float
    arrived_at: datetime
    score: float = 0.0
    value: float = 0.0
    due: date | None = None
    do_next: bool = False
    status: str = "Triaged"
    title: str = ""
    new: bool = False              # arrived inside a forecast run
    ended: bool = False            # closed or merged by a person (history replay only)
    done_on: date | None = None    # set by work_week()

    @property
    def arrived(self) -> date:
        """The arrival date as the store reads it (arrived_at::date in a UTC session), so ages agree with its views."""
        return self.arrived_at.astimezone(timezone.utc).date()

    @property
    def arrived_local(self) -> date:
        return self.arrived_at.astimezone(TEAM_TZ).date()


@dataclass(frozen=True)
class PlanSettings:
    hours_per_week: float
    urgent_buffer_share: float
    small_share: float
    standard_share: float
    age_points_per_week: float
    safe_start_days: int

    @classmethod
    def from_settings(cls, s: dict, safe_start_days: int) -> "PlanSettings":
        return cls(float(s["hours_per_week"]), float(s["urgent_buffer_share"]), float(s["small_share"]),
                   float(s["standard_share"]), float(s["age_points_per_week"]), int(safe_start_days))


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_of(dt: datetime) -> date:
    """The Monday of the team's own week holding this moment."""
    return monday(dt.astimezone(TEAM_TZ).date())


def weeks_waited(item: Item, as_of: date) -> int:
    return max(0, (as_of - item.arrived).days // 7)


def rank_points(item: Item, as_of: date, rate: float) -> float:
    return round(item.score + weeks_waited(item, as_of) * rate, 2)


def latest_safe_start(item: Item, ps: PlanSettings) -> date | None:
    return item.due - timedelta(days=ps.safe_start_days) if item.due else None


def nearest_rank(values: list, p: float):
    """The p-th percentile by the nearest-rank rule: the smallest value with at least p of all values at or below it.
    None sorts last (not done within the horizon), so a level that falls on a None has no value."""
    xs = sorted(values, key=lambda v: (v is None, v))
    if not xs:
        return None
    return xs[max(1, math.ceil(p * len(xs) - 1e-9)) - 1]


def safe_start_days(spans_days: list[int], p: float, fallback: int = 7) -> int:
    """Latest safe start (KB-139 section 7): the due date less the time such work has needed p of the time. The time a
    fixed-date item needed is its span in the work log, from the Monday of its first week of work to the Sunday of its
    last. With no fixed-date item done yet, one week (the plan's own step) is used."""
    return int(nearest_rank(spans_days, p)) if spans_days else fallback


def work_spans(work_rows: list[dict], ids: set[str]) -> list[int]:
    weeks: dict[str, list[date]] = {}
    for w in work_rows:
        if w["request_id"] in ids:
            weeks.setdefault(w["request_id"], []).append(date.fromisoformat(str(w["week_start"])[:10]))
    return sorted((max(ws) - min(ws)).days + 7 for ws in weeks.values())


# ---------------------------------------------------------------- the order inside each lane

def urgent_order(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda i: (i.arrived_at, i.request_id))


def fixed_order(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda i: (i.due or date.max, i.arrived_at, i.request_id))


def small_order(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda i: (not i.do_next, i.arrived_at, i.request_id))


def standard_order(items: list[Item], as_of: date, rate: float) -> list[Item]:
    """changedesk.ranked_standard: do it next first, then score plus age points, then the oldest, then the id."""
    return sorted(items, key=lambda i: (not i.do_next, -rank_points(i, as_of, rate), i.arrived_at, i.request_id))


# ---------------------------------------------------------------- one week's plan (R12)

@dataclass
class Segment:
    item: Item
    hours: float
    step: str
    why: str


@dataclass
class Step:
    name: str
    budget: float
    used: float
    note: str = ""


@dataclass
class WeekPlan:
    week_start: date
    rule: str
    hours: float
    segments: list[Segment] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    urgent_beyond_buffer: float = 0.0

    @property
    def used(self) -> float:
        return sum(s.hours for s in self.segments)

    def rows(self) -> list[dict]:
        """One row per item, in the order first given hours, for changedesk.save_plan."""
        out: dict[str, dict] = {}
        for s in self.segments:
            r = out.setdefault(s.item.request_id, {"request_id": s.item.request_id, "lane": s.item.lane, "hours": 0.0,
                                                   "position": len(out) + 1, "why": []})
            r["hours"] += s.hours
            if s.why not in r["why"]:
                r["why"].append(s.why)
        return [dict(r, hours=round(r["hours"], 1), why="; ".join(r["why"])) for r in out.values()]


def plan_week(items: list[Item], week_start: date, ps: PlanSettings, rule: str = "lanes") -> WeekPlan:
    """The plan for one week. items: the open work that may be planned (the caller leaves out what waits for a person).
    Each segment gives an item hours, in the order the hours are worked."""
    if rule not in RULES:
        raise ValueError(f"unknown order rule {rule!r}")
    plan = WeekPlan(week_start, rule, ps.hours_per_week)
    pool = [i for i in items if i.left > EPS]
    given: dict[str, float] = {}
    left = [ps.hours_per_week]

    def spend(queue: list[Item], budget: float, step: str, why) -> float:
        budget = min(budget, left[0])
        used = 0.0
        for it in queue:
            if budget - used <= EPS:
                break
            need = it.left - given.get(it.request_id, 0.0)
            if need <= EPS:
                continue
            h = min(need, budget - used)
            given[it.request_id] = given.get(it.request_id, 0.0) + h
            used += h
            plan.segments.append(Segment(it, h, step, why(it)))
        left[0] -= used
        return used

    if rule == "highest score first":
        queue = sorted(pool, key=lambda i: (-(10 if i.lane == "urgent" else i.score), i.arrived_at, i.request_id))
        used = spend(queue, ps.hours_per_week, "score", lambda i: f"highest score first: {'urgent, counted as 10' if i.lane == 'urgent' else f'score {i.score:g}'}")
        plan.steps.append(Step("Highest score first, urgent counted as 10", ps.hours_per_week, used))
        return plan
    if rule == "value per hour first":
        queue = sorted(pool, key=lambda i: (0 if i.lane == "urgent" else 1, -(i.value / i.size), i.arrived_at, i.request_id))
        used = spend(queue, ps.hours_per_week, "value per hour", lambda i: "urgent first" if i.lane == "urgent"
                     else f"value per hour first: {i.value / i.size:.2f}")
        plan.steps.append(Step("Urgent first, then value per hour", ps.hours_per_week, used))
        return plan

    rate = ps.age_points_per_week
    last_day = week_start + timedelta(days=6)
    by_lane = {lane: [i for i in pool if i.lane == lane] for lane in LANES}

    # 1. Urgent first, one at a time, oldest first. It takes more than the buffer if it must.
    buffer = ps.hours_per_week * ps.urgent_buffer_share
    used = spend(urgent_order(by_lane["urgent"]), left[0], "urgent", lambda i: "urgent: harm is growing now")
    plan.urgent_beyond_buffer = max(0.0, used - buffer)
    plan.steps.append(Step("1. Urgent, one at a time, oldest first", buffer, used,
                           f"took {plan.urgent_beyond_buffer:g} hours beyond the {buffer:g}-hour buffer" if plan.urgent_beyond_buffer > EPS
                           else f"the buffer is {buffer:g} hours"))

    # 2. Fixed-date items from their latest safe start.
    fixed_now = [i for i in by_lane["fixed_date"] if latest_safe_start(i, ps) <= last_day]
    fixed_later = [i for i in by_lane["fixed_date"] if latest_safe_start(i, ps) > last_day]

    def fixed_why(i: Item) -> str:
        lss = latest_safe_start(i, ps)
        if i.due < week_start:
            return f"fixed date {i.due:%d/%m/%Y} has passed; still open"
        return f"fixed date {i.due:%d/%m/%Y}: latest safe start {lss:%d/%m/%Y}"
    used = spend(fixed_order(fixed_now), left[0], "fixed_date", fixed_why)
    plan.steps.append(Step(f"2. Fixed dates from their latest safe start (due date less {ps.safe_start_days} days)", used, used,
                           f"{len(fixed_now)} items at or past their latest safe start; {len(fixed_later)} not yet"))

    # 3. The small lane's reserved share, oldest first.
    small_budget = ps.hours_per_week * ps.small_share
    small_q = small_order(by_lane["small"])
    used = spend(small_q, small_budget, "small", lambda i: "do it next (decide list)" if i.do_next else "small: the lane's reserved share, oldest first")
    plan.steps.append(Step(f"3. Small and quick, {ps.small_share:.0%} of the week, oldest first", min(small_budget, used + left[0]), used))

    # 4. Standard work by score plus age.
    std_q = standard_order(by_lane["standard"], week_start, rate)

    def std_why(i: Item) -> str:
        if i.do_next:
            return "do it next (decide list)"
        return f"standard: {rank_points(i, week_start, rate):g} rank points (score {i.score:g} + {weeks_waited(i, week_start)} weeks x {rate:g})"
    std_budget = ps.hours_per_week * ps.standard_share
    used = spend(std_q, std_budget, "standard", std_why)
    plan.steps.append(Step(f"4. Standard, {ps.standard_share:.0%} of the week, by score plus age", min(std_budget, used + left[0]), used))

    # 5. Unused hours flow to the other lanes.
    before = left[0]
    flow = spend(std_q, left[0], "flow", lambda i: f"unused hours flow: {std_why(i)}")
    flow += spend(small_q, left[0], "flow", lambda i: "unused hours flow: small, oldest first")
    flow += spend(fixed_order(fixed_later), left[0], "flow", lambda i: f"unused hours flow: {fixed_why(i)}, ahead of it")
    plan.steps.append(Step("5. Unused hours flow to the other lanes", before, flow, f"{left[0]:g} hours left unplanned"))
    return plan


def work_week(plan: WeekPlan, ps: PlanSettings) -> list[Item]:
    """Work the plan: each segment's hours come off its item, in order. An item is done on the working day its last hour
    falls on (the week's hours spread evenly over five days), and never before it arrived. Returns the items finished."""
    day_hours = ps.hours_per_week / WORKDAYS
    cum = 0.0
    finished = []
    for seg in plan.segments:
        cum += seg.hours
        it = seg.item
        it.left -= seg.hours
        if it.left <= EPS and it.done_on is None:
            it.left = 0.0
            day = min(WORKDAYS - 1, int((cum - EPS) // day_hours)) if day_hours > 0 else WORKDAYS - 1
            it.done_on = max(plan.week_start + timedelta(days=day), it.arrived_local)
            finished.append(it)
    return finished


# ---------------------------------------------------------------- the sample history (rule test and back-check)

def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def score_of(parts: dict[str, int], weights: dict[str, float]) -> float:
    """As changedesk.score_totals: each part's points times its weight, rounded to cents, summed."""
    return round(sum(round(parts[p] * float(weights[p]), 2) for p in SCORE_PARTS), 2)


def history_items(doc: dict, weights: dict[str, float]) -> tuple[list[Item], dict[str, datetime]]:
    """Every triaged request in a history file (scripts/make_history.py), with its whole size still to do, and when a
    person closed or merged it, if one did."""
    parts: dict[str, dict[str, int]] = {}
    for s in sorted(doc["scores"], key=lambda s: s["set_at"]):
        parts.setdefault(s["request_id"], {})[s["part"]] = int(s["points"])
    items = []
    for r in doc["requests"]:
        if r["status"] == "New" or not r.get("lane"):
            continue
        p = parts[r["request_id"]]
        items.append(Item(r["request_id"], r["lane"], float(r["size_hours"]), float(r["size_hours"]), parse_ts(r["arrived_at"]),
                          score_of(p, weights), float(p["value"]), date.fromisoformat(r["due_date"]) if r.get("due_date") else None,
                          title=r["title"]))
    ends = {h["request_id"]: parse_ts(h["changed_at"]) for h in doc["status_history"] if h["to_status"] in ("Closed", "Merged")}
    return items, ends


def history_safe_start_days(doc: dict, p: float) -> int:
    done = {h["request_id"] for h in doc["status_history"] if h["to_status"] == "Done"}
    fixed = {r["request_id"] for r in doc["requests"] if r.get("lane") == "fixed_date"}
    return safe_start_days(work_spans(doc["work_log"], done & fixed), p)


@dataclass
class Replay:
    rule: str
    items: dict[str, Item]
    worked: dict[tuple[str, date], float]
    plans: list[WeekPlan]


def replay(items: list[Item], person_ends: dict[str, datetime], week_one: date, weeks: int, ps: PlanSettings, rule: str) -> Replay:
    """Work the history's own arrivals again, week by week, under one order rule. An item is there to be planned from
    the week it arrived (by 17:00 on the Friday, as the history was made). An item a person closed or merged leaves in
    the week it was closed, under every rule, unless that rule finished it first."""
    state = {i.request_id: replace(i, left=i.size, done_on=None, ended=False) for i in items}
    worked: dict[tuple[str, date], float] = {}
    plans = []
    for w in range(weeks):
        ws = week_one + timedelta(weeks=w)
        cutoff = datetime.combine(ws + timedelta(days=4), time(17), TEAM_TZ)
        for rid, when in person_ends.items():
            it = state.get(rid)
            if it and it.done_on is None and week_of(when) == ws:
                it.ended = True
        avail = [i for i in state.values() if i.done_on is None and not i.ended and i.arrived_at <= cutoff and i.left > EPS]
        plan = plan_week(avail, ws, ps, rule)
        work_week(plan, ps)
        for s in plan.segments:
            key = (s.item.request_id, ws)
            worked[key] = worked.get(key, 0.0) + s.hours
        plans.append(plan)
    return Replay(rule, state, worked, plans)


MEASURES = ("small done %", "oldest small waiting (weeks)", "fixed dates met %", "oldest standard waiting (weeks)",
            "open at the end", "value delivered")


def replay_measures(rp: Replay, week_one: date, weeks: int) -> dict[str, float]:
    """The policy test's measures (KB-136 section 6.6), on one replay. Settled items (for "done %") arrived before the
    last four weeks, as there. Items a person closed or merged count neither way."""
    end = week_one + timedelta(weeks=weeks)
    settled_by = datetime.combine(week_one + timedelta(weeks=weeks - 4), time(0), TEAM_TZ)
    live = [i for i in rp.items.values() if not i.ended]
    out: dict[str, float] = {}
    small = [i for i in live if i.lane == "small" and i.arrived_at < settled_by]
    out["small done %"] = round(100 * sum(i.done_on is not None for i in small) / max(1, len(small)), 1)
    for lane, key in (("small", "oldest small waiting (weeks)"), ("standard", "oldest standard waiting (weeks)")):
        still = [i for i in live if i.lane == lane and i.done_on is None]
        out[key] = round(max(((end - i.arrived_local).days / 7 for i in still), default=0.0), 1)
    dated = [i for i in live if i.lane == "fixed_date" and i.due and i.due < end]
    # None when no fixed date fell due inside the weeks: nothing was met or missed (seed 166 has two, both due after it).
    out["fixed dates met %"] = round(100 * sum(i.done_on is not None and i.done_on <= i.due for i in dated) / len(dated), 1) if dated else None
    out["open at the end"] = float(sum(i.done_on is None for i in live))
    out["value delivered"] = float(sum(i.value for i in live if i.done_on is not None))
    return out


# ---------------------------------------------------------------- the forecast (R18, R19): many runs of the weeks ahead

@dataclass(frozen=True)
class Arrival:
    """One past arrival, as a pattern for new ones: its size, score, value, the day of its week, and how many days after
    it arrived its date fell due (fixed-date items)."""
    lane: str
    size: float
    score: float
    value: float
    weekday: int
    due_days: int | None


def lane_history(items: list[Item], first_week: date, weeks: int) -> dict[str, list[list[Arrival]]]:
    """Each lane's own arrivals, week by week, over the given weeks of history: what a forecast run draws new work from."""
    out = {lane: [[] for _ in range(weeks)] for lane in LANES}
    for i in items:
        k = (week_of(i.arrived_at) - first_week).days // 7
        if 0 <= k < weeks:
            out[i.lane][k].append(Arrival(i.lane, i.size, i.score, i.value, i.arrived_local.weekday(),
                                          (i.due - i.arrived_local).days if i.due else None))
    return out


@dataclass
class SimResult:
    start_week: date
    runs: int
    horizon: int
    finish: dict[str, list[date | None]]
    hours_in_per_week: dict[str, float]
    hours_out_per_week: dict[str, float]
    new_small_settled: int
    new_small_cycle_days: list[int | None]


def simulate(items: list[Item], history: dict[str, list[list[Arrival]]], ps: PlanSettings, start_week: date, rule: str,
             runs: int, horizon: int, seed: int, load: float = 1.0, arrivals_from: int = 1) -> SimResult:
    """Run the weeks ahead many times. Each run starts from the same open work; from week arrivals_from on, each lane
    gets new arrivals each week, copied from one of its own past weeks drawn at random (load scales how many: 1.5 draws
    one past week and, half the time, a second). Every week is planned by plan_week() and worked by work_week()."""
    rng = random.Random(seed)
    finish: dict[str, list[date | None]] = {i.request_id: [] for i in items}
    hin = {lane: 0.0 for lane in LANES}
    hout = {lane: 0.0 for lane in LANES}
    settled_weeks = max(1, horizon - 4)
    cycles: list[int | None] = []
    for r in range(runs):
        mine = [replace(i, done_on=None, new=False) for i in items]
        active = list(mine)
        new_small = []
        n = 0
        for k in range(horizon):
            ws = start_week + timedelta(weeks=k)
            if k >= arrivals_from:
                for lane in LANES:
                    past = history.get(lane) or []
                    if not past:
                        continue
                    draws = int(load) + (1 if rng.random() < load - int(load) else 0)
                    for _ in range(draws):
                        for a in rng.choice(past):
                            n += 1
                            at = datetime.combine(ws + timedelta(days=a.weekday), time(10), TEAM_TZ)
                            it = Item(f"NEW-{r}-{n}", lane, a.size, a.size, at, a.score, a.value,
                                      at.date() + timedelta(days=a.due_days) if a.due_days is not None else None, new=True)
                            active.append(it)
                            hin[lane] += a.size
                            if lane == "small" and k < settled_weeks:
                                new_small.append(it)
            plan = plan_week(active, ws, ps, rule)
            for s in plan.segments:
                hout[s.item.lane] += s.hours
            work_week(plan, ps)
            active = [i for i in active if i.done_on is None]
        for i in mine:
            finish[i.request_id].append(i.done_on)
        cycles += [(i.done_on - i.arrived_local).days if i.done_on else None for i in new_small]
    arrival_weeks = max(1, horizon - arrivals_from) * runs
    return SimResult(start_week, runs, horizon, finish,
                     {lane: round(h / arrival_weeks, 1) for lane, h in hin.items()},
                     {lane: round(h / (horizon * runs), 1) for lane, h in hout.items()},
                     len(cycles), cycles)


def level_dates(dates: list[date | None], levels: list[float]) -> list[date | None]:
    return [nearest_rank(dates, p) for p in levels]


def chance_by(dates: list[date | None], due: date) -> float:
    return round(sum(d is not None and d <= due for d in dates) / max(1, len(dates)), 3)
