-- Change Desk, stages 0 to 2: the views people and the forms read. Applied after db/changedesk.sql
-- and db/run_log.sql by scripts/setup_db.py. Safe to run again.
--
-- Every number a view shows comes from a row or a setting, so it can be traced (R23 later).
-- Ages use the date the request arrived. "As of" functions take the date; the views use today.

-- ---------------------------------------------------------------- scoring (R9, R10, R11)

-- Effort points from the size in hours, by the bands in the setting effort_points_by_size.
-- The same rule is in engine/scoring.js (effortPoints); tests/test_scoring.py checks they agree.
create or replace function changedesk.effort_points(hours numeric) returns integer
language sql stable set search_path = changedesk, pg_temp as $$
  select (b ->> 'points')::integer
  from jsonb_array_elements(changedesk.setting('effort_points_by_size')) with ordinality as t(b, n)
  where b ->> 'max_hours' is null or hours <= (b ->> 'max_hours')::numeric
  order by n limit 1
$$;

-- The current value of each part: the latest row for that part.
create or replace view changedesk.current_scores as
select distinct on (s.request_id, s.part)
  s.request_id, s.part, s.points, s.reason, s.set_by, s.set_at, s.previous_points, s.is_change, s.stamp, s.score_id
from changedesk.scores s
order by s.request_id, s.part, s.set_at desc, s.score_id desc;

-- R9: each part with its weight, its points in the score, and its reason. R10: a changed part
-- shows both values (previous_points and points) and who changed it.
create or replace view changedesk.score_working as
with w as (
  select key as part, (value #>> '{}')::numeric as weight
  from jsonb_each(changedesk.setting('score_weights'))
)
select r.request_id, r.title, r.lane, r.status, c.part, w.weight, c.points,
  round(c.points * w.weight, 2) as weighted_points,
  c.reason, c.set_by, c.set_at, c.is_change, c.previous_points, c.stamp
from changedesk.requests r
join changedesk.current_scores c on c.request_id = r.request_id
join w on w.part = c.part;

-- One row per scored item: the score, the working in one line, and whether a person changed a part.
create or replace view changedesk.score_totals as
select request_id, title, lane, status,
  round(sum(weighted_points), 2) as score,
  count(*) as parts,
  string_agg(format('%s %s x %s = %s', part, points, weight, weighted_points), ' + '
             order by array_position(array['value', 'effort', 'risk', 'goal_fit', 'readiness'], part)) as working,
  bool_or(is_change) as changed_by_a_person
from changedesk.score_working
group by request_id, title, lane, status;

-- R11 and "score alone never sets the order": the standard lane ranked by score plus points for
-- each whole week waited, at the rate in the setting age_points_per_week. "Do it next" from the
-- decide list comes first. Open work: Triaged, Planned, and (from stage 3) In progress, so the
-- planner can place work already started by the same rule. scripts/planner.py (standard_order)
-- ranks the same way for the forecast and the rule test; tests/test_planner_db.py checks they agree.
create or replace function changedesk.ranked_standard(as_of date) returns table (
  rank integer, request_id text, title text, status text, score numeric, weeks_waited integer,
  age_points numeric, rank_points numeric, do_next boolean, awaiting_confirmation boolean,
  arrived_on date, working text)
language sql stable set search_path = changedesk, pg_temp as $$
  with s as (
    select r.request_id, r.title, r.status, t.score, r.do_next, r.arrived_at,
      (r.needs_confirmation and r.lane_confirmed_by is null) as awaiting_confirmation,
      greatest(0, floor((as_of - r.arrived_at::date) / 7.0))::integer as weeks_waited, t.working
    from changedesk.requests r
    join changedesk.score_totals t on t.request_id = r.request_id and t.parts = 5
    where r.lane = 'standard' and r.status in ('Triaged', 'Planned', 'In progress') and r.arrived_at::date <= as_of
  )
  select (row_number() over (order by s.do_next desc, s.score + s.weeks_waited * changedesk.setting_num('age_points_per_week') desc, s.arrived_at, s.request_id))::integer,
    s.request_id, s.title, s.status, s.score, s.weeks_waited,
    round(s.weeks_waited * changedesk.setting_num('age_points_per_week'), 2),
    round(s.score + s.weeks_waited * changedesk.setting_num('age_points_per_week'), 2),
    s.do_next, s.awaiting_confirmation, s.arrived_at::date,
    s.working || format(' = %s; + %s weeks x %s = %s', s.score, s.weeks_waited,
      changedesk.setting_num('age_points_per_week'), round(s.weeks_waited * changedesk.setting_num('age_points_per_week'), 2))
  from s
  order by 1
$$;

create or replace view changedesk.standard_ranked as
select * from changedesk.ranked_standard(current_date);

-- ---------------------------------------------------------------- the decide list (R16)

-- Open items past their lane's age limit (settings age_limit_days_small and _standard). Each is
-- decided: do it next, merge it, or close it with a reason. An item with a standing "do it next"
-- has been decided and leaves the list.
--
-- Build addition to R16 (Israel's decision, 25/11/2026): a fixed-date item whose date has passed goes
-- on the list at once, whatever its age, and first: the date was the reason for its lane, so a person
-- says whether it is still needed. Work already started counts too (In progress), because the reason
-- for doing it may have gone. For these rows age_limit_days is null, days_over is the days since the
-- date, and why says which rule put the item there.
do $$
begin
  -- The result gained two columns in stage 5 (due_date, why). A function's result cannot be changed in
  -- place, so the old one is dropped once, with the two views that read it (both are made again below).
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'changedesk' and p.proname = 'decide_list_at' and not ('why' = any (coalesce(p.proargnames, '{}')))) then
    drop function changedesk.decide_list_at(date) cascade;
  end if;
end $$;

create or replace function changedesk.decide_list_at(as_of date) returns table (
  request_id text, title text, lane text, status text, requester_role text, playbook text,
  arrived_on date, age_days integer, age_limit_days integer, days_over integer, score numeric,
  due_date date, why text)
language sql stable set search_path = changedesk, pg_temp as $$
  select * from (
    select r.request_id, r.title, r.lane, r.status, r.requester_role, r.playbook, r.arrived_at::date,
      (as_of - r.arrived_at::date), lim.days, (as_of - r.arrived_at::date) - lim.days, t.score,
      null::date, 'past the age limit'::text
    from changedesk.requests r
    cross join lateral (
      select changedesk.setting_num(case r.lane when 'small' then 'age_limit_days_small' else 'age_limit_days_standard' end)::integer as days
    ) lim
    left join changedesk.score_totals t on t.request_id = r.request_id
    where r.lane in ('small', 'standard') and r.status in ('Triaged', 'Planned') and not r.do_next
      and (as_of - r.arrived_at::date) > lim.days
    union all
    select r.request_id, r.title, r.lane, r.status, r.requester_role, r.playbook, r.arrived_at::date,
      (as_of - r.arrived_at::date), null::integer, (as_of - r.due_date), t.score, r.due_date, 'its fixed date has passed'
    from changedesk.requests r
    left join changedesk.score_totals t on t.request_id = r.request_id
    where r.lane = 'fixed_date' and r.status in ('Triaged', 'Planned', 'In progress') and not r.do_next
      and r.due_date < as_of
  ) l
  order by (l.lane = 'fixed_date') desc, 10 desc, 1
$$;

create or replace view changedesk.decide_list as
select * from changedesk.decide_list_at(current_date);

-- ---------------------------------------------------------------- lane confirmation (R5, R8)

create or replace view changedesk.awaiting_confirmation as
select r.request_id, r.requester_role, r.title, r.body, r.lane, r.type, r.size_hours, r.due_date, r.due_breaks,
  r.urgent, r.urgent_harm, r.goal_id, r.playbook, r.split_proposal, r.confidence, r.triage_reason, r.flags,
  r.confirmation_reasons, r.triage_stamp, r.arrived_at,
  (r.needs_confirmation and r.lane_confirmed_by is null) as lane_waits,
  (r.split_proposal is not null and jsonb_array_length(r.split_proposal) > 0 and r.split_decision is null) as split_waits
from changedesk.requests r
where r.status = 'Triaged'
  and ((r.needs_confirmation and r.lane_confirmed_by is null)
       or (r.split_proposal is not null and jsonb_array_length(r.split_proposal) > 0 and r.split_decision is null));

-- The requests triage has not seen yet. The text is data: the AI step reads it inside a data block.
create or replace view changedesk.inbox as
select request_id, source, requester_role, title, body, requester_due_date, requester_says_breaks,
  requester_says_harm, arrived_at
from changedesk.requests where status = 'New';

-- ---------------------------------------------------------------- the tracker and lane health

-- When each request ended (Done, Merged, Closed or Split), from its status history.
create or replace view changedesk.request_ends as
select r.request_id, r.lane, r.arrived_at, r.due_date,
  (select min(h.changed_at) from changedesk.status_history h
    where h.request_id = r.request_id and h.to_status in ('Done', 'Merged', 'Closed', 'Split')) as ended_at,
  (select min(h.changed_at) from changedesk.status_history h
    where h.request_id = r.request_id and h.to_status = 'Done') as done_at
from changedesk.requests r
where r.lane is not null;

-- A setting's value as it stood on a day: the last value set on or before it, from settings_history (stage 5). Before the
-- first change it is the starting value, which held from the start of the history. Used where a past week must be read
-- with the setting of that week (the urgent buffer was 4 hours at 40 hours a week; 3.6 from 25/11/2026 at 36).
create or replace function changedesk.setting_num_at(k text, on_day date) returns numeric
language sql stable set search_path = changedesk, pg_temp as $$
  select coalesce(
    (select (h.value #>> '{}')::numeric from changedesk.settings_history h
      where h.key = k and h.changed_at::date <= on_day order by h.changed_at desc, h.id desc limit 1),
    (select (h.value #>> '{}')::numeric from changedesk.settings_history h where h.key = k order by h.changed_at, h.id limit 1),
    changedesk.setting_num(k))
$$;

-- R15 is built and checked in stage 3; this view gives it the figures. For each lane and each
-- week since work was first logged: in, out, open at the end of the week, the oldest open age,
-- items past the age limit, fixed dates due that week and met, and urgent hours beyond the buffer.
create or replace view changedesk.lane_health as
with weeks as (
  select generate_series((select min(week_start) from changedesk.work_log),
                         date_trunc('week', current_date)::date, interval '7 days')::date as week_start
), lanes as (
  select unnest(array['urgent', 'fixed_date', 'standard', 'small']) as lane
), grid as (
  select w.week_start, (w.week_start + 7) as week_end, l.lane from weeks w cross join lanes l
)
select g.lane, g.week_start,
  (select count(*) from changedesk.request_ends e where e.lane = g.lane
     and e.arrived_at >= g.week_start and e.arrived_at < g.week_end) as arrived,
  (select count(*) from changedesk.request_ends e where e.lane = g.lane
     and e.ended_at >= g.week_start and e.ended_at < g.week_end) as finished,
  (select count(*) from changedesk.request_ends e where e.lane = g.lane
     and e.arrived_at < g.week_end and (e.ended_at is null or e.ended_at >= g.week_end)) as open_at_end,
  (select max((g.week_end - 1) - e.arrived_at::date) from changedesk.request_ends e where e.lane = g.lane
     and e.arrived_at < g.week_end and (e.ended_at is null or e.ended_at >= g.week_end)) as oldest_open_days,
  (select count(*) from changedesk.request_ends e where e.lane = g.lane and g.lane in ('small', 'standard')
     and e.arrived_at < g.week_end and (e.ended_at is null or e.ended_at >= g.week_end)
     and ((g.week_end - 1) - e.arrived_at::date) > changedesk.setting_num(case g.lane when 'small' then 'age_limit_days_small' else 'age_limit_days_standard' end)) as past_age_limit,
  (select count(*) from changedesk.request_ends e where g.lane = 'fixed_date' and e.lane = 'fixed_date'
     and e.due_date >= g.week_start and e.due_date < g.week_end) as fixed_dates_due,
  (select count(*) from changedesk.request_ends e where g.lane = 'fixed_date' and e.lane = 'fixed_date'
     and e.due_date >= g.week_start and e.due_date < g.week_end and e.done_at::date <= e.due_date) as fixed_dates_met,
  (select greatest(0, coalesce(sum(wl.hours), 0) - changedesk.setting_num_at('hours_per_week', g.week_end) * changedesk.setting_num_at('urgent_buffer_share', g.week_end))
     from changedesk.work_log wl join changedesk.requests r on r.request_id = wl.request_id
    where g.lane = 'urgent' and r.lane = 'urgent' and wl.week_start = g.week_start) as urgent_hours_beyond_buffer
from grid g
order by g.week_start, array_position(array['urgent', 'fixed_date', 'standard', 'small'], g.lane);

-- What the Notion board shows (stage 3, scripts/sync_tracker.py): one row for every request, open
-- or ended, with what triage found, its rank points, its age, its planned week and its latest
-- forecast. R7: an item with no business goal shows the no_goal flag. For an ended item the age and
-- the waiting points stop on the day it ended. The board shows roles only: the sync script maps
-- lane_confirmed_by to a role and never copies a reviewer's label.
drop view if exists changedesk.tracker;
create view changedesk.tracker as
with latest_forecast as (
  select run_id from changedesk.forecast_runs where purpose = 'forecast' order by made_at desc, run_id desc limit 1
), latest_plan as (
  select distinct on (p.request_id) p.request_id, p.week_start, p.plan_id
  from changedesk.week_plan p order by p.request_id, p.made_at desc, p.plan_id desc
)
select r.request_id, r.title, r.lane, r.status, r.type, r.size_hours, r.requester_role, r.goal_id, g.title as goal,
  r.playbook, r.triage_reason, r.close_reason, r.merged_into, r.confidence, r.due_date, r.due_breaks, r.urgent_harm,
  (r.goal_id is null and r.status <> 'New') as no_goal,
  concat_ws('|', nullif(r.flags, ''), case when r.goal_id is null and r.status <> 'New' then 'no_goal' end) as flags,
  (r.needs_confirmation and r.lane_confirmed_by is null) as awaiting_confirmation,
  r.lane_confirmed_by, t.score, r.do_next, r.arrived_at::date as arrived_on, e.ended_at::date as ended_on,
  (coalesce(e.ended_at::date, current_date) - r.arrived_at::date) as age_days,
  case when r.lane = 'standard' and t.score is not null then
    round(t.score + greatest(0, floor((coalesce(e.ended_at::date, current_date) - r.arrived_at::date) / 7.0))
                    * changedesk.setting_num('age_points_per_week'), 2) end as rank_points,
  exists (select 1 from changedesk.decide_list d where d.request_id = r.request_id) as past_age_limit,
  lp.week_start as planned_week, lp.plan_id,
  f.run_id as forecast_run_id, f.kind as forecast_kind, f.p50, f.p85, f.p95, f.service_level_days, f.chance,
  f.latest_safe_start, f.note as forecast_note
from changedesk.requests r
left join changedesk.goals g on g.goal_id = r.goal_id
left join changedesk.score_totals t on t.request_id = r.request_id
left join changedesk.request_ends e on e.request_id = r.request_id
left join latest_plan lp on lp.request_id = r.request_id
left join changedesk.forecasts f on f.request_id = r.request_id and f.run_id = (select run_id from latest_forecast);

-- One query from a stamp to the whole triage record: the request, what the AI proposed and what
-- it cost, and who confirmed the lane.
create or replace view changedesk.triage_record as
select c.call_id, c.run_id, c.source, c.request_id, c.model, c.model_served, c.playbook_name, c.playbook_version,
  c.engine_version, c.output_valid, c.stop_reason, c.error, c.input_tokens, c.output_tokens, c.latency_ms,
  c.cost_usd, c.called_at, r.lane, r.type, r.size_hours, r.confidence, r.triage_reason, r.flags,
  r.needs_confirmation, r.confirmation_reasons, r.triage_stamp, r.lane_confirmed_by, r.lane_confirmed_at, r.lane_stamp
from changedesk.call_cost c
left join changedesk.requests r on r.request_id = c.request_id
where c.step = 'triage';

-- ---------------------------------------------------------------- stage 5: where each figure in an update comes from (R23)

-- One fact's value, read again from its source row. A source names a table or view, a filter and a column, and
-- may count or add up the rows it filters: {"table": "forecasts", "where": {"run_id": "fc-...", "request_id":
-- "CD-0016"}, "column": "p85"}, {"table": "week_plan", "where": {"plan_id": "...", "lane": "small"}, "agg": "sum",
-- "column": "hours"}, {"table": "decide_list_at", "as_of": "2026-11-25", "where": {"why": "..."}, "agg": "count"}.
-- Only the tables and columns listed here can be read, every name is quoted as a name and every value as a value,
-- so a source cannot be made into other SQL. A plain value must come from exactly one row. The value comes back as
-- text in one form: dates as YYYY-MM-DD, numbers without trailing zeros, true or false. The update drafter's
-- facts are filled from this function, log_updates refuses a fact that does not match it, approve_updates refuses
-- an update whose facts no longer match it, and scripts/check_updates.py prints it for every figure.
create or replace function changedesk.fact_value(src jsonb) returns text
language plpgsql stable set search_path = changedesk, pg_temp as $$
declare
  readable constant jsonb := '{
    "requests": ["request_id", "title", "lane", "status", "requester_role", "due_date", "size_hours", "goal_id", "do_next", "arrived_at"],
    "forecasts": ["run_id", "request_id", "lane", "kind", "p50", "p85", "p95", "service_level_days", "chance", "latest_safe_start",
                  "hours_in_per_week", "hours_out_per_week", "growing", "finished_share"],
    "forecast_runs": ["run_id", "purpose", "start_week", "runs", "horizon_weeks", "seed", "made_at"],
    "settings": ["key", "value", "changed_by", "changed_at"],
    "settings_history": ["id", "key", "value", "changed_by", "changed_at"],
    "week_plan": ["plan_id", "week_start", "lane", "request_id", "hours"],
    "update_triggers": ["run_id", "previous_run_id", "request_id", "old_p85", "new_p85", "moved_days", "why"],
    "lane_health": ["lane", "week_start", "arrived", "finished", "open_at_end", "oldest_open_days", "past_age_limit",
                    "fixed_dates_due", "fixed_dates_met", "urgent_hours_beyond_buffer"],
    "decide_list_at": ["request_id", "lane", "status", "why", "age_days", "days_over", "due_date"],
    "awaiting_confirmation": ["request_id", "lane"],
    "goals": ["goal_id", "title"]
  }'::jsonb;
  t text := src ->> 'table';
  col text := src ->> 'column';
  agg text := coalesce(src ->> 'agg', 'value');
  from_sql text;
  where_sql text := '';
  expr text;
  k text;
  v jsonb;
  n bigint;
  out text;
begin
  if jsonb_typeof(src) is distinct from 'object' or t is null or not (readable ? t) then
    raise exception 'fact source: % is not a table a fact may read', coalesce(t, 'nothing');
  end if;
  if agg not in ('value', 'count', 'sum', 'min', 'max') then
    raise exception 'fact source: % is not a way to read rows', agg;
  end if;
  if agg <> 'count' and (col is null or not (readable -> t ? col)) then
    raise exception 'fact source: % has no column % a fact may read', t, coalesce(col, '(none)');
  end if;
  for k, v in select * from jsonb_each(coalesce(src -> 'where', '{}'::jsonb)) loop
    if not (readable -> t ? k) then
      raise exception 'fact source: % cannot be filtered on %', t, k;
    end if;
    where_sql := where_sql || ' and ' || case
      when jsonb_typeof(v) = 'null' then format('%I is null', k)
      when jsonb_typeof(v) = 'array' then format('%I::text = any (%L::text[])', k, (select array_agg(x) from jsonb_array_elements_text(v) x))
      else format('%I::text = %L', k, v #>> '{}') end;
  end loop;
  from_sql := case when t = 'decide_list_at' then format('changedesk.decide_list_at(%L::date)', src ->> 'as_of')
                   else format('changedesk.%I', t) end;
  if t = 'decide_list_at' and (src ->> 'as_of') is null then
    raise exception 'fact source: decide_list_at needs the date it was read as of';
  end if;
  if agg <> 'count' then
    expr := case
      when col = 'value' and t in ('settings', 'settings_history') and src ? 'index' then format('(value #>> %L)', '{' || (src ->> 'index')::integer || '}')
      when col = 'value' and t in ('settings', 'settings_history') then '(value #>> ''{}'')'
      when src ->> 'cast' = 'date' then format('((%I) at time zone ''UTC'')::date::text', col)
      else format('(%I)::text', col) end;
  end if;
  if agg = 'value' then
    execute format('select count(*) from %s where true%s', from_sql, where_sql) into n;
    if n <> 1 then
      raise exception 'fact source: % rows in % match, not one', n, t;
    end if;
    execute format('select %s from %s where true%s', expr, from_sql, where_sql) into out;
  elsif agg = 'count' then
    execute format('select count(*)::text from %s where true%s', from_sql, where_sql) into out;
  else
    execute format('select %s(%I)::text from %s where true%s', agg, col, from_sql, where_sql) into out;
  end if;
  if out ~ '^-?[0-9]+\.[0-9]+$' then
    out := regexp_replace(regexp_replace(out, '0+$', ''), '\.$', '');
  end if;
  return out;
end $$;

-- The facts of one update whose value no longer matches its row (the pipe has changed since the draft), or whose
-- row cannot be read. An update with any is refused at approval: it must be drafted again.
create or replace function changedesk.stale_facts(uid text) returns table (fact_id text, says text, drafted text, now text)
language plpgsql stable set search_path = changedesk, pg_temp as $$
declare
  f jsonb;
  cur text;
begin
  for f in select x from changedesk.updates u, jsonb_array_elements(u.facts) x where u.update_id = uid loop
    begin
      cur := changedesk.fact_value(f -> 'source');
    exception when others then
      cur := 'cannot be read: ' || sqlerrm;
    end;
    if cur is distinct from f ->> 'value' then
      fact_id := f ->> 'id'; says := f ->> 'says'; drafted := f ->> 'value'; now := cur;
      return next;
    end if;
  end loop;
end $$;
