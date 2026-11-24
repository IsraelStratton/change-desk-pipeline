-- Change Desk (INIT-163), stage 0: the store. KB-139 section 6.2.
--
-- Schema changedesk in the local Supabase Postgres. Applied by scripts/setup_db.py as the
-- database owner. Safe to run again: every object is created only if it is missing, and views
-- and functions are replaced.
--
-- Tables (6.2): requests, status_history, scores, settings, work_log, week_plan, forecasts,
-- updates, goals, plus decisions (every person's decision, with its stamp) and settings_history
-- (every value a setting has had). run_log, agent_handoffs and model_prices are in db/run_log.sql.
-- Views (6.2): lane_health and decide_list, plus the working views the forms and the tracker read.
--
-- The app's login (changedesk_app) may read this schema and nothing else. It writes only through
-- the functions in db/app_functions.sql. All data is made up.

create schema if not exists changedesk;
comment on schema changedesk is 'Change Desk (INIT-163): bug and enhancement pipeline on made-up tickets. Written only through checked functions.';

-- ---------------------------------------------------------------- goals

create table if not exists changedesk.goals (
  goal_id      text primary key check (goal_id ~ '^G[0-9]{1,2}$'),
  title        text not null,
  description  text not null,
  owner_role   text not null,
  active       boolean not null default true
);
comment on table changedesk.goals is 'A few made-up business goals. The goal link is on the item only: nobody is scored.';

-- ---------------------------------------------------------------- settings (KB-139 section 7)

create table if not exists changedesk.settings (
  key          text primary key check (key ~ '^[a-z][a-z0-9_]*$'),
  value        jsonb not null,
  description  text not null,
  source       text not null,
  changed_by   text not null check (length(trim(changed_by)) > 0),
  changed_at   timestamptz not null default now(),
  why          text not null check (length(trim(why)) > 0)
);
comment on table changedesk.settings is 'Every setting in one table, with who changed it, when and why (R14). Starting values from KB-139 section 7.';

create table if not exists changedesk.settings_history (
  id           bigserial primary key,
  key          text not null references changedesk.settings (key),
  value        jsonb not null,
  changed_by   text not null,
  changed_at   timestamptz not null,
  why          text not null
);

create or replace function changedesk.keep_setting_history() returns trigger
language plpgsql set search_path = changedesk, pg_temp as $$
begin
  insert into changedesk.settings_history (key, value, changed_by, changed_at, why)
  values (new.key, new.value, new.changed_by, new.changed_at, new.why);
  return new;
end $$;

drop trigger if exists settings_history_trg on changedesk.settings;
create trigger settings_history_trg after insert or update on changedesk.settings
  for each row execute function changedesk.keep_setting_history();

-- Read a setting. Raises if it is missing, so no code ever falls back to a typed-in value.
create or replace function changedesk.setting(k text) returns jsonb
language plpgsql stable set search_path = changedesk, pg_temp as $$
declare v jsonb;
begin
  select value into v from changedesk.settings where key = k;
  if v is null then
    raise exception 'setting % is missing', k;
  end if;
  return v;
end $$;

create or replace function changedesk.setting_num(k text) returns numeric
language sql stable set search_path = changedesk, pg_temp as $$
  select (changedesk.setting(k) #>> '{}')::numeric
$$;

-- ---------------------------------------------------------------- requests (one row per request)

create sequence if not exists changedesk.request_number start with 1001;

create table if not exists changedesk.requests (
  request_id              text primary key check (request_id ~ '^CD-[0-9]{4,}$'),
  source                  text not null check (source in ('history', 'form', 'split')),
  requester_role          text not null check (length(trim(requester_role)) between 2 and 80),
  title                   text not null check (length(trim(title)) between 3 and 140),
  body                    text not null check (length(body) between 1 and 4000),
  -- What the requester said on the form. Data only: triage applies the two tests itself.
  requester_due_date      date,
  requester_says_breaks   text,
  requester_says_harm     text,
  arrived_at              timestamptz not null,
  -- What triage returns (6.4), once triaged.
  type                    text check (type in ('bug', 'enhancement')),
  lane                    text check (lane in ('urgent', 'fixed_date', 'standard', 'small')),
  size_hours              numeric(6, 1) check (size_hours > 0 and size_hours <= 400),
  due_date                date,
  due_breaks              text,
  urgent                  boolean,
  urgent_harm             text,
  goal_id                 text references changedesk.goals (goal_id),
  playbook                text check (playbook ~ '^(none|crm-[a-z0-9-]+)$'),
  split_proposal          jsonb check (split_proposal is null or jsonb_typeof(split_proposal) = 'array'),
  split_decision          text check (split_decision in ('accepted', 'rejected')),
  parent_id               text references changedesk.requests (request_id),
  confidence              numeric(4, 3) check (confidence between 0 and 1),
  triage_reason           text,
  flags                   text not null default '',
  triaged_by              text,
  triage_stamp            text,
  triaged_at              timestamptz,
  -- R5: urgent, fixed-date, low-confidence and flagged items wait for a person.
  needs_confirmation      boolean not null default false,
  confirmation_reasons    text not null default '',
  lane_confirmed_by       text,
  lane_confirmed_at       timestamptz,
  lane_stamp              text,
  -- The decide list's "do it next".
  do_next                 boolean not null default false,
  status                  text not null default 'New'
                          check (status in ('New', 'Triaged', 'Planned', 'In progress', 'Done', 'Merged', 'Closed', 'Split')),
  close_reason            text,
  merged_into             text references changedesk.requests (request_id),
  updated_at              timestamptz not null default now(),
  -- R2: every triaged row has every field of the fixed shape.
  constraint triaged_rows_are_complete check (
    status = 'New' or (type is not null and lane is not null and size_hours is not null and urgent is not null
                       and playbook is not null and confidence is not null and triage_reason is not null
                       and triaged_by is not null and triaged_at is not null)),
  -- R4: the two tests are stored on the row, and the lane follows them.
  constraint fixed_date_lane_names_what_breaks check (lane is distinct from 'fixed_date' or (due_date is not null and length(trim(coalesce(due_breaks, ''))) > 0)),
  constraint urgent_lane_names_the_harm check (lane is distinct from 'urgent' or (coalesce(urgent, false) and length(trim(coalesce(urgent_harm, ''))) > 0)),
  -- R5: no such item is planned (or worked) without a person's confirmation.
  constraint confirmed_before_planned check (
    not (status in ('Planned', 'In progress', 'Done') and needs_confirmation and lane_confirmed_by is null)),
  constraint closed_has_reason check (status <> 'Closed' or length(trim(coalesce(close_reason, ''))) > 0),
  constraint merged_names_target check (status <> 'Merged' or (merged_into is not null and merged_into <> request_id)),
  constraint split_parent_accepted check (status <> 'Split' or split_decision = 'accepted')
);
create index if not exists requests_status_idx on changedesk.requests (status);
create index if not exists requests_lane_idx on changedesk.requests (lane);

-- ---------------------------------------------------------------- status history

create table if not exists changedesk.status_history (
  id           bigserial primary key,
  request_id   text not null references changedesk.requests (request_id),
  from_status  text,
  to_status    text not null check (to_status in ('New', 'Triaged', 'Planned', 'In progress', 'Done', 'Merged', 'Closed', 'Split')),
  changed_at   timestamptz not null,
  changed_by   text not null check (length(trim(changed_by)) > 0),
  note         text not null default '',
  stamp        text,
  check (from_status is distinct from to_status)
);
create index if not exists status_history_request_idx on changedesk.status_history (request_id, changed_at);

-- R1: every request has a status history from the start, and its status is always the last
-- one in its history. Checked when the transaction commits, so a row and its history can be
-- written in either order.
create or replace function changedesk.check_status_history() returns trigger
language plpgsql set search_path = changedesk, pg_temp as $$
declare
  last_status text;
  now_status text;
begin
  -- The row as it is at commit, not as it was when this event was queued: a request may be
  -- added and moved on in the same transaction (a split, for one).
  select status into now_status from changedesk.requests where request_id = new.request_id;
  if now_status is null then
    return null;
  end if;
  select to_status into last_status from changedesk.status_history
   where request_id = new.request_id order by changed_at desc, id desc limit 1;
  if last_status is null then
    raise exception 'request % has no status history', new.request_id;
  end if;
  if last_status <> now_status then
    raise exception 'request % is % but its history ends at %', new.request_id, now_status, last_status;
  end if;
  return null;
end $$;

drop trigger if exists requests_status_history_trg on changedesk.requests;
create constraint trigger requests_status_history_trg after insert or update of status on changedesk.requests
  deferrable initially deferred for each row execute function changedesk.check_status_history();

-- ---------------------------------------------------------------- scores (each part, add-only)

create table if not exists changedesk.scores (
  score_id         bigserial primary key,
  request_id       text not null references changedesk.requests (request_id),
  part             text not null check (part in ('value', 'effort', 'risk', 'goal_fit', 'readiness')),
  points           integer not null check (points between 1 and 10),
  reason           text not null check (length(trim(reason)) > 0),
  set_by           text not null check (length(trim(set_by)) > 0),
  set_at           timestamptz not null,
  previous_points  integer check (previous_points between 1 and 10),
  is_change        boolean not null default false,
  run_id           text,
  stamp            text not null,
  check (not is_change or previous_points is not null)
);
create index if not exists scores_request_idx on changedesk.scores (request_id, part, set_at);
comment on table changedesk.scores is 'Each part of a score: value, reason, who set it and when. Add-only: a change is a new row that keeps the old value (R10).';

-- ---------------------------------------------------------------- the person's decisions

create table if not exists changedesk.decisions (
  decision_id  text primary key,
  run_id       text not null,
  request_id   text not null references changedesk.requests (request_id),
  kind         text not null check (kind in ('lane', 'split', 'score', 'decide')),
  action       text not null,
  detail       jsonb not null default '{}'::jsonb,
  decided_by   text not null check (length(trim(decided_by)) > 0),
  decided_at   timestamptz not null,
  note         text not null default '',
  stamp        text not null
);
create index if not exists decisions_request_idx on changedesk.decisions (request_id);

-- ---------------------------------------------------------------- work, plan, forecast, updates

create table if not exists changedesk.work_log (
  request_id   text not null references changedesk.requests (request_id),
  week_start   date not null check (extract(isodow from week_start) = 1),
  hours        numeric(5, 1) not null check (hours > 0),
  logged_by    text not null,
  primary key (request_id, week_start)
);
comment on table changedesk.work_log is 'Hours worked on each item, by week (weeks start on Monday).';

create table if not exists changedesk.week_plan (
  plan_id      text not null,
  week_start   date not null check (extract(isodow from week_start) = 1),
  lane         text not null check (lane in ('urgent', 'fixed_date', 'standard', 'small')),
  request_id   text not null references changedesk.requests (request_id),
  hours        numeric(5, 1) not null check (hours > 0),
  position     integer not null check (position > 0),
  made_at      timestamptz not null default now(),
  made_by      text not null,
  primary key (plan_id, request_id)
);
comment on table changedesk.week_plan is 'The plan for each week: lane, item, hours and order. Filled from stage 3 by a plain script.';

-- R5 again, at the plan: an item that waits for a person cannot be put in a week's plan.
create or replace function changedesk.check_plan_confirmed() returns trigger
language plpgsql set search_path = changedesk, pg_temp as $$
begin
  if exists (select 1 from changedesk.requests r where r.request_id = new.request_id
             and r.needs_confirmation and r.lane_confirmed_by is null) then
    raise exception 'request % waits for a lane confirmation and cannot be planned', new.request_id;
  end if;
  return new;
end $$;

drop trigger if exists week_plan_confirmed_trg on changedesk.week_plan;
create trigger week_plan_confirmed_trg before insert or update on changedesk.week_plan
  for each row execute function changedesk.check_plan_confirmed();

create table if not exists changedesk.forecasts (
  run_id              text not null,
  request_id          text references changedesk.requests (request_id),
  lane                text not null check (lane in ('urgent', 'fixed_date', 'standard', 'small')),
  kind                text not null check (kind in ('date_range', 'service_level', 'chance_of_date')),
  p50                 date,
  p85                 date,
  p95                 date,
  service_level_days  numeric(6, 1),
  chance              numeric(4, 3) check (chance between 0 and 1),
  latest_safe_start   date,
  note                text not null default '',
  made_at             timestamptz not null default now()
);
comment on table changedesk.forecasts is 'Each forecast run (stage 4). Per item: the 50, 85 and 95% dates, or the chance of its date and the latest safe start. Per lane: the service level.';

create table if not exists changedesk.updates (
  update_id        text primary key,
  run_id           text not null,
  audience         text not null check (audience in ('requester', 'manager', 'executive')),
  kind             text not null check (kind in ('close', 'status')),
  request_id       text references changedesk.requests (request_id),
  subject          text not null,
  body             text not null,
  forecast_run_id  text,
  call_id          text,
  drafted_by       text not null,
  drafted_at       timestamptz not null,
  draft_problems   text not null default '',
  status           text not null default 'draft' check (status in ('draft', 'approved', 'rejected')),
  approved_by      text,
  approved_at      timestamptz,
  stamp            text not null,
  check ((status = 'draft') = (approved_by is null)),
  check (status <> 'approved' or draft_problems = '')
);
comment on table changedesk.updates is 'Each draft: audience, text, the forecast run it used, who approved it and when. Nothing here is sent: an approved update goes to the outbox in stage 5.';

-- ---------------------------------------------------------------- stages 3 and 4 (25/11/2026)

-- The week's plan (R12): each row also says which step of the lanes rule put it there, and carries the stamp.
alter table changedesk.week_plan add column if not exists why text not null default '';
alter table changedesk.week_plan add column if not exists stamp text not null default '';
comment on table changedesk.week_plan is 'The plan for each week: lane, item, hours and order, made by the plain-script planner (scripts/planner.py). The latest plan is the plan.';

-- One row per forecast run (R18 to R21): what it ran on, so every figure it gives can be traced to its inputs.
create table if not exists changedesk.forecast_runs (
  run_id           text primary key,
  purpose          text not null check (purpose in ('forecast', 'what-if')),
  start_week       date not null check (extract(isodow from start_week) = 1),
  rule             text not null check (rule in ('lanes', 'highest score first', 'value per hour first')),
  runs             integer not null check (runs between 10 and 100000),
  horizon_weeks    integer not null check (horizon_weeks between 1 and 104),
  seed             integer not null,
  load             numeric(4, 2) not null check (load > 0),
  safe_start_days  integer not null check (safe_start_days >= 0),
  settings         jsonb not null,
  summary          jsonb not null default '{}'::jsonb,
  made_by          text not null check (length(trim(made_by)) > 0),
  made_at          timestamptz not null,
  stamp            text not null check (stamp like 'changedesk %')
);
comment on table changedesk.forecast_runs is 'Each forecast run: the start week, the rule, the number of runs, the horizon, the seed, the load and the settings it used. A what-if run (another load or setting) never triggers an update.';

-- Lane rows (request_id null) carry the lane's own figures: hours in and out a week in the run, and whether it grows.
alter table changedesk.forecasts add column if not exists hours_in_per_week numeric(6, 1);
alter table changedesk.forecasts add column if not exists hours_out_per_week numeric(6, 1);
alter table changedesk.forecasts add column if not exists growing boolean;
alter table changedesk.forecasts add column if not exists finished_share numeric(4, 3) check (finished_share between 0 and 1);
create index if not exists forecasts_run_idx on changedesk.forecasts (run_id, request_id);
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'forecasts_run_fk') then
    alter table changedesk.forecasts add constraint forecasts_run_fk foreign key (run_id) references changedesk.forecast_runs (run_id);
  end if;
end $$;
