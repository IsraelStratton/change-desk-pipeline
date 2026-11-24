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
-- decide list comes first. Waiting work only (Triaged or Planned).
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
    where r.lane = 'standard' and r.status in ('Triaged', 'Planned') and r.arrived_at::date <= as_of
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
create or replace function changedesk.decide_list_at(as_of date) returns table (
  request_id text, title text, lane text, status text, requester_role text, playbook text,
  arrived_on date, age_days integer, age_limit_days integer, days_over integer, score numeric)
language sql stable set search_path = changedesk, pg_temp as $$
  select r.request_id, r.title, r.lane, r.status, r.requester_role, r.playbook, r.arrived_at::date,
    (as_of - r.arrived_at::date), lim.days, (as_of - r.arrived_at::date) - lim.days, t.score
  from changedesk.requests r
  cross join lateral (
    select changedesk.setting_num(case r.lane when 'small' then 'age_limit_days_small' else 'age_limit_days_standard' end)::integer as days
  ) lim
  left join changedesk.score_totals t on t.request_id = r.request_id
  where r.lane in ('small', 'standard') and r.status in ('Triaged', 'Planned') and not r.do_next
    and (as_of - r.arrived_at::date) > lim.days
  order by (as_of - r.arrived_at::date) - lim.days desc, r.request_id
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

-- What the Notion board (stage 3) shows: one row per open item, grouped by lane, with its reason
-- and its flags. R7: an item with no business goal shows the no_goal flag.
create or replace view changedesk.tracker as
select r.request_id, r.title, r.lane, r.status, r.type, r.size_hours, r.requester_role, r.goal_id, g.title as goal,
  r.playbook, r.triage_reason, r.confidence, r.due_date, r.urgent_harm,
  (r.goal_id is null) as no_goal,
  concat_ws('|', nullif(r.flags, ''), case when r.goal_id is null then 'no_goal' end) as flags,
  (r.needs_confirmation and r.lane_confirmed_by is null) as awaiting_confirmation,
  r.lane_confirmed_by, t.score, r.do_next, r.arrived_at::date as arrived_on,
  (current_date - r.arrived_at::date) as age_days
from changedesk.requests r
left join changedesk.goals g on g.goal_id = r.goal_id
left join changedesk.score_totals t on t.request_id = r.request_id
where r.status in ('New', 'Triaged', 'Planned', 'In progress');

-- When each request ended (Done, Merged, Closed or Split), from its status history.
create or replace view changedesk.request_ends as
select r.request_id, r.lane, r.arrived_at, r.due_date,
  (select min(h.changed_at) from changedesk.status_history h
    where h.request_id = r.request_id and h.to_status in ('Done', 'Merged', 'Closed', 'Split')) as ended_at,
  (select min(h.changed_at) from changedesk.status_history h
    where h.request_id = r.request_id and h.to_status = 'Done') as done_at
from changedesk.requests r
where r.lane is not null;

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
  (select greatest(0, coalesce(sum(wl.hours), 0) - changedesk.setting_num('hours_per_week') * changedesk.setting_num('urgent_buffer_share'))
     from changedesk.work_log wl join changedesk.requests r on r.request_id = wl.request_id
    where g.lane = 'urgent' and r.lane = 'urgent' and wl.week_start = g.week_start) as urgent_hours_beyond_buffer
from grid g
order by g.week_start, array_position(array['urgent', 'fixed_date', 'standard', 'small'], g.lane);

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
