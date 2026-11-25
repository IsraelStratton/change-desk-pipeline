-- Change Desk: the run log, the hand-off record and the price table.
--
-- Copied from the GTM pipeline (db/run_log.sql and db/quote_desk.sql) and shaped for this build:
-- one row per AI call (the triage step and the message drafter), one row per hand-off (from the
-- AI step to a person, and from a person's decision to the drafter), and views that work out the
-- cost from the price table. Applied by scripts/setup_db.py as the database owner. Safe to run again.
-- The app's login writes these only through log_triage and log_drafts (db/app_functions.sql).

create schema if not exists changedesk;

create table if not exists changedesk.model_prices (
  model                   text primary key,
  input_per_mtok          numeric(10, 4) not null check (input_per_mtok >= 0),
  output_per_mtok         numeric(10, 4) not null check (output_per_mtok >= 0),
  long_prompt_over_tokens integer,
  long_input_per_mtok     numeric(10, 4),
  long_output_per_mtok    numeric(10, 4),
  read_on                 date not null,
  source                  text not null
);

create table if not exists changedesk.run_log (
  call_id           text primary key,
  run_id            text not null,
  step              text not null check (step in ('triage', 'drafter')),
  source            text not null check (source in ('n8n', 'python', 'eval')),
  request_id        text,
  case_id           text,
  model             text not null,
  model_served      text,
  playbook_name     text not null,
  playbook_version  text not null,
  playbook_sha256   text not null check (playbook_sha256 ~ '^[0-9a-f]{64}$'),
  engine_version    text not null,
  output_valid      boolean not null,
  stop_reason       text,
  error             text,
  input_tokens      integer not null default 0 check (input_tokens >= 0),
  output_tokens     integer not null default 0 check (output_tokens >= 0),
  latency_ms        integer check (latency_ms >= 0),
  api_request_id    text,
  called_at         timestamptz not null,
  logged_at         timestamptz not null default now(),
  check (source = 'eval' or request_id is not null),
  check (output_valid or error is not null or stop_reason is not null)
);
create index if not exists run_log_run_idx on changedesk.run_log (run_id);

-- Stage 5 (25/11/2026): the update drafter's calls. Its calls name the update they drafted (update_id); an update
-- for the manager or the executive covers no single request, so its call and its hand-off carry no request_id.
alter table changedesk.run_log add column if not exists update_id text;
alter table changedesk.run_log drop constraint if exists run_log_step_check;
alter table changedesk.run_log add constraint run_log_step_check check (step in ('triage', 'drafter', 'updater'));
alter table changedesk.run_log drop constraint if exists run_log_check;
alter table changedesk.run_log add constraint run_log_check check (source = 'eval' or request_id is not null or (step = 'updater' and update_id is not null));
-- call_cost reads l.*, so it is made again once with the new column (with the views that read it).
do $$
begin
  if exists (select 1 from information_schema.views where table_schema = 'changedesk' and table_name = 'call_cost')
     and not exists (select 1 from information_schema.columns where table_schema = 'changedesk' and table_name = 'call_cost' and column_name = 'update_id') then
    drop view changedesk.call_cost cascade;
  end if;
end $$;
create index if not exists run_log_request_idx on changedesk.run_log (request_id);

-- KB-137 B3: each hand-off is a record. Here the AI step hands an item to a person when the lane
-- needs a confirmation, and a person's close hands the item to the message drafter.
create table if not exists changedesk.agent_handoffs (
  handoff_id   text primary key,
  run_id       text not null,
  request_id   text not null,
  from_agent   text not null,
  to_agent     text not null,
  asked        text not null,
  why          text not null,
  evidence     text not null,
  confidence   numeric(4, 3) check (confidence between 0 and 1),
  call_id      text references changedesk.run_log (call_id),
  logged_at    timestamptz not null default now(),
  check (from_agent <> to_agent)
);
create index if not exists agent_handoffs_run_idx on changedesk.agent_handoffs (run_id);
alter table changedesk.agent_handoffs alter column request_id drop not null;
alter table changedesk.agent_handoffs drop constraint if exists agent_handoffs_request_needed;
alter table changedesk.agent_handoffs add constraint agent_handoffs_request_needed check (request_id is not null or from_agent = 'update_drafter');

-- One row per AI call, with its cost from the price table (the long-prompt price applies per call).
create or replace view changedesk.call_cost as
select l.*,
  round(case
    when mp.model is null then null
    when mp.long_prompt_over_tokens is not null and l.input_tokens > mp.long_prompt_over_tokens
      then (l.input_tokens * mp.long_input_per_mtok + l.output_tokens * mp.long_output_per_mtok) / 1000000.0
    else (l.input_tokens * mp.input_per_mtok + l.output_tokens * mp.output_per_mtok) / 1000000.0
  end, 8) as cost_usd
from changedesk.run_log l
left join changedesk.model_prices mp on mp.model = l.model;

-- One row per run: calls, failures, tokens, total cost and cost per call.
create or replace view changedesk.run_summary as
select run_id,
  min(source) as source,
  string_agg(distinct step, ', ') as steps,
  string_agg(distinct model, ', ') as models,
  string_agg(distinct playbook_name || '@' || playbook_version, ', ') as playbooks,
  count(*) as calls,
  count(*) filter (where not output_valid) as failed,
  sum(input_tokens) as input_tokens,
  sum(output_tokens) as output_tokens,
  round(sum(cost_usd), 6) as total_cost_usd,
  round(avg(cost_usd), 8) as cost_per_call_usd,
  round(avg(latency_ms)) as avg_latency_ms,
  min(called_at) as started_at,
  max(called_at) as last_call_at
from changedesk.call_cost
group by run_id;

-- R30 (stage 6 builds the cost sheet on this): cost per triage and per draft, by model and source.
create or replace view changedesk.cost_by_step as
select step, source, model, count(*) as calls,
  round(avg(cost_usd), 8) as cost_per_call_usd, round(sum(cost_usd), 6) as total_cost_usd,
  round(avg(input_tokens)) as avg_input_tokens, round(avg(output_tokens)) as avg_output_tokens
from changedesk.call_cost
group by step, source, model;

