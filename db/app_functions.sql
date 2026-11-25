-- Change Desk, stages 0 to 2: the only way the app's login (changedesk_app) can write.
--
-- Each function checks its input, writes the row and its status history in one go, and stamps
-- every write with who decided it. The login has no insert, update or delete right on any table
-- (scripts/setup_db.py grants it these functions and read access to the schema, nothing else).
-- The pattern is the GTM pipeline's add-only run log (db/run_log.sql there), widened to the
-- desk's few, checked changes. Applied after db/views.sql. Safe to run again.

-- ---------------------------------------------------------------- intake (R1)

-- One request from the intake form. It gets an id and its first status history row at once.
create or replace function changedesk.add_request(r jsonb) returns text
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  new_id text;
  role_text text := nullif(regexp_replace(trim(coalesce(r ->> 'requester_role', '')), '\s+', ' ', 'g'), '');
  title_text text := nullif(regexp_replace(trim(coalesce(r ->> 'title', '')), '\s+', ' ', 'g'), '');
  body_text text := nullif(trim(coalesce(r ->> 'body', '')), '');
begin
  if jsonb_typeof(r) <> 'object' then
    raise exception 'add_request expects a JSON object';
  end if;
  if role_text is null or title_text is null or body_text is null then
    raise exception 'a request needs the requester''s role, a title and a description';
  end if;
  new_id := 'CD-' || lpad(nextval('changedesk.request_number')::text, 4, '0');
  insert into changedesk.requests (request_id, source, requester_role, title, body, requester_due_date,
    requester_says_breaks, requester_says_harm, arrived_at, status)
  values (new_id, 'form', left(role_text, 80), left(title_text, 140), left(body_text, 4000),
    nullif(r ->> 'requester_due_date', '')::date, nullif(trim(coalesce(r ->> 'requester_says_breaks', '')), ''),
    nullif(trim(coalesce(r ->> 'requester_says_harm', '')), ''), now(), 'New');
  insert into changedesk.status_history (request_id, from_status, to_status, changed_at, changed_by, note)
  values (new_id, null, 'New', now(), 'intake form', coalesce(nullif(r ->> 'via', ''), 'n8n intake form'));
  return new_id;
end $$;

-- ---------------------------------------------------------------- the triage step (R2, R4 to R8)

-- calls: one run_log row per AI call. proposals: the checked proposals from engine/triage.js
-- (checkTriage). handoffs: one row for each item handed to a person. A proposal with no usable
-- answer is logged as a call only: the request stays New for the next run.
create or replace function changedesk.log_triage(calls jsonb, proposals jsonb, handoffs jsonb) returns integer
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  p jsonb;
  s jsonb;
  n integer := 0;
  current_status text;
begin
  if jsonb_typeof(calls) <> 'array' or jsonb_typeof(proposals) <> 'array' or jsonb_typeof(handoffs) <> 'array' then
    raise exception 'log_triage expects three JSON arrays';
  end if;
  insert into changedesk.run_log (call_id, run_id, step, source, request_id, case_id, model, model_served,
    playbook_name, playbook_version, playbook_sha256, engine_version, output_valid, stop_reason, error,
    input_tokens, output_tokens, latency_ms, api_request_id, called_at)
  select c.call_id, c.run_id, 'triage', c.source, c.request_id, c.case_id, c.model, c.model_served,
    c.playbook_name, c.playbook_version, c.playbook_sha256, c.engine_version, c.output_valid, c.stop_reason, c.error,
    coalesce(c.input_tokens, 0), coalesce(c.output_tokens, 0), c.latency_ms, c.api_request_id, c.called_at
  from jsonb_to_recordset(calls) as c(call_id text, run_id text, source text, request_id text, case_id text,
    model text, model_served text, playbook_name text, playbook_version text, playbook_sha256 text,
    engine_version text, output_valid boolean, stop_reason text, error text, input_tokens integer,
    output_tokens integer, latency_ms integer, api_request_id text, called_at timestamptz);

  for p in select * from jsonb_array_elements(proposals) loop
    if not coalesce((p ->> 'output_valid')::boolean, false) then
      continue;
    end if;
    select status into current_status from changedesk.requests where request_id = p ->> 'request_id' for update;
    if current_status is null then
      raise exception 'no request %', p ->> 'request_id';
    end if;
    if current_status <> 'New' then
      raise exception 'request % is % and has been triaged already', p ->> 'request_id', current_status;
    end if;
    if p ->> 'stamp' is null or p ->> 'stamp' not like 'changedesk %' then
      raise exception 'proposal for % carries no who-decided stamp', p ->> 'request_id';
    end if;
    update changedesk.requests set
      type = p ->> 'type', lane = p ->> 'lane', size_hours = (p ->> 'size_hours')::numeric,
      due_date = nullif(p ->> 'due_date', '')::date, due_breaks = p ->> 'what_breaks',
      urgent = (p ->> 'is_urgent')::boolean, urgent_harm = p ->> 'harm_growing',
      goal_id = p ->> 'goal_id', playbook = p ->> 'playbook',
      split_proposal = case when jsonb_array_length(coalesce(p -> 'split', '[]'::jsonb)) > 0 then p -> 'split' end,
      confidence = (p ->> 'confidence')::numeric, triage_reason = p ->> 'reason',
      flags = coalesce((select string_agg(value, '|') from jsonb_array_elements_text(coalesce(p -> 'flags', '[]'::jsonb))), ''),
      triaged_by = 'triage_agent', triage_stamp = p ->> 'stamp', triaged_at = (p ->> 'triaged_at')::timestamptz,
      needs_confirmation = (p ->> 'needs_confirmation')::boolean,
      confirmation_reasons = coalesce((select string_agg(value, '|') from jsonb_array_elements_text(coalesce(p -> 'confirmation_reasons', '[]'::jsonb))), ''),
      status = 'Triaged', updated_at = now()
    where request_id = p ->> 'request_id';
    insert into changedesk.status_history (request_id, from_status, to_status, changed_at, changed_by, note, stamp)
    values (p ->> 'request_id', 'New', 'Triaged', (p ->> 'triaged_at')::timestamptz, 'triage_agent',
      case when (p ->> 'needs_confirmation')::boolean then 'lane proposed; waits for a person' else 'lane set by the triage step' end,
      p ->> 'stamp');
    for s in select * from jsonb_array_elements(coalesce(p -> 'scores', '[]'::jsonb)) loop
      insert into changedesk.scores (request_id, part, points, reason, set_by, set_at, run_id, stamp)
      values (p ->> 'request_id', s ->> 'part', (s ->> 'points')::integer, s ->> 'reason',
        coalesce(s ->> 'set_by', 'triage_agent'), (p ->> 'triaged_at')::timestamptz, p ->> 'run_id', p ->> 'stamp');
    end loop;
    n := n + 1;
  end loop;

  insert into changedesk.agent_handoffs (handoff_id, run_id, request_id, from_agent, to_agent, asked, why, evidence, confidence, call_id)
  select h.handoff_id, h.run_id, h.request_id, h.from_agent, h.to_agent, h.asked, h.why, h.evidence, h.confidence, h.call_id
  from jsonb_to_recordset(handoffs) as h(handoff_id text, run_id text, request_id text, from_agent text, to_agent text,
    asked text, why text, evidence text, confidence numeric, call_id text);
  return n;
end $$;

-- ---------------------------------------------------------------- the lane confirmation form (R5, R8)

create or replace function changedesk.confirm_lanes(rows jsonb) returns integer
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  d jsonb;
  req changedesk.requests%rowtype;
  piece jsonb;
  k integer;
  pieces integer;
  child_id text;
  child_lane text;
  n integer := 0;
  who text;
  at timestamptz;
begin
  if jsonb_typeof(rows) <> 'array' then
    raise exception 'confirm_lanes expects a JSON array';
  end if;
  for d in select * from jsonb_array_elements(rows) order by (value ->> 'kind') = 'split', value ->> 'request_id' loop
    who := nullif(trim(coalesce(d ->> 'decided_by', '')), '');
    at := (d ->> 'decided_at')::timestamptz;
    if who is null or at is null or coalesce(d ->> 'stamp', '') not like 'changedesk %' then
      raise exception 'a confirmation needs who decided, when, and a stamp';
    end if;
    select * into req from changedesk.requests where request_id = d ->> 'request_id' for update;
    if req.request_id is null then
      raise exception 'no request %', d ->> 'request_id';
    end if;
    if req.status <> 'Triaged' then
      raise exception 'request % is %, not waiting for a confirmation', req.request_id, req.status;
    end if;

    if d ->> 'kind' = 'lane' then
      if not req.needs_confirmation or req.lane_confirmed_by is not null then
        raise exception 'request % does not wait for a lane confirmation', req.request_id;
      end if;
      if d ->> 'action' = 'confirmed' then
        if d ->> 'lane' is distinct from req.lane then
          raise exception 'the confirmation for % names lane % but the proposal is %', req.request_id, d ->> 'lane', req.lane;
        end if;
      elsif d ->> 'action' = 'changed' then
        if d ->> 'lane' not in ('urgent', 'fixed_date', 'standard', 'small') or d ->> 'lane' = req.lane then
          raise exception 'the change for % must name a different lane', req.request_id;
        end if;
        if length(trim(coalesce(d ->> 'note', ''))) = 0 then
          raise exception 'a lane change for % needs a reason in the note', req.request_id;
        end if;
        update changedesk.requests set
          lane = d ->> 'lane',
          urgent = case when d ->> 'lane' = 'urgent' then true when req.lane = 'urgent' then false else req.urgent end,
          urgent_harm = case when d ->> 'lane' = 'urgent' then coalesce(nullif(req.urgent_harm, ''), d ->> 'note') else req.urgent_harm end
        where request_id = req.request_id;
      else
        raise exception 'unknown lane action %', d ->> 'action';
      end if;
      update changedesk.requests set lane_confirmed_by = who, lane_confirmed_at = at, lane_stamp = d ->> 'stamp', updated_at = now()
      where request_id = req.request_id;

    elsif d ->> 'kind' = 'split' then
      if req.split_proposal is null or jsonb_array_length(req.split_proposal) = 0 or req.split_decision is not null then
        raise exception 'request % has no split waiting for a decision', req.request_id;
      end if;
      if req.needs_confirmation and req.lane_confirmed_by is null then
        raise exception 'confirm the lane of % before its split', req.request_id;
      end if;
      if d ->> 'action' = 'rejected' then
        update changedesk.requests set split_decision = 'rejected', updated_at = now() where request_id = req.request_id;
      elsif d ->> 'action' = 'accepted' then
        select * into req from changedesk.requests where request_id = req.request_id;
        pieces := jsonb_array_length(req.split_proposal);
        k := 0;
        for piece in select * from jsonb_array_elements(req.split_proposal) loop
          k := k + 1;
          child_id := 'CD-' || lpad(nextval('changedesk.request_number')::text, 4, '0');
          child_lane := case when req.lane in ('urgent', 'fixed_date') then req.lane
                             when (piece ->> 'hours')::numeric <= changedesk.setting_num('small_lane_max_hours') then 'small'
                             else 'standard' end;
          insert into changedesk.requests (request_id, source, requester_role, title, body, arrived_at, type, lane,
            size_hours, due_date, due_breaks, urgent, urgent_harm, goal_id, playbook, parent_id, confidence,
            triage_reason, flags, triaged_by, triage_stamp, triaged_at, needs_confirmation, lane_confirmed_by,
            lane_confirmed_at, lane_stamp, status)
          values (child_id, 'split', req.requester_role, left(piece ->> 'title', 140),
            format('Piece %s of %s, split from %s on a person''s yes. The full request is on %s.', k, pieces, req.request_id, req.request_id),
            req.arrived_at, req.type, child_lane, (piece ->> 'hours')::numeric,
            case when child_lane = 'fixed_date' then req.due_date end, case when child_lane = 'fixed_date' then req.due_breaks end,
            child_lane = 'urgent', case when child_lane = 'urgent' then req.urgent_harm end,
            req.goal_id, req.playbook, req.request_id, req.confidence,
            format('Split from %s: piece %s of %s, about %s hours (%s lane).', req.request_id, k, pieces, piece ->> 'hours', child_lane),
            req.flags, who, d ->> 'stamp', at, false, null, null, null, 'Triaged');
          insert into changedesk.status_history (request_id, from_status, to_status, changed_at, changed_by, note, stamp)
          values (child_id, null, 'Triaged', at, who, format('split from %s', req.request_id), d ->> 'stamp');
          insert into changedesk.scores (request_id, part, points, reason, set_by, set_at, run_id, stamp)
          select child_id, c.part, c.points, format('From %s: %s', req.request_id, c.reason), who, at, d ->> 'run_id', d ->> 'stamp'
          from changedesk.current_scores c where c.request_id = req.request_id and c.part <> 'effort';
          insert into changedesk.scores (request_id, part, points, reason, set_by, set_at, run_id, stamp)
          values (child_id, 'effort', changedesk.effort_points((piece ->> 'hours')::numeric),
            format('%s hours: effort points from the size bands in the settings.', piece ->> 'hours'), who, at, d ->> 'run_id', d ->> 'stamp');
        end loop;
        update changedesk.requests set split_decision = 'accepted', status = 'Split', updated_at = now() where request_id = req.request_id;
        insert into changedesk.status_history (request_id, from_status, to_status, changed_at, changed_by, note, stamp)
        values (req.request_id, 'Triaged', 'Split', at, who, format('split into %s pieces', pieces), d ->> 'stamp');
      else
        raise exception 'unknown split action %', d ->> 'action';
      end if;
    else
      raise exception 'unknown confirmation kind %', d ->> 'kind';
    end if;

    insert into changedesk.decisions (decision_id, run_id, request_id, kind, action, detail, decided_by, decided_at, note, stamp)
    values (d ->> 'decision_id', d ->> 'run_id', req.request_id, d ->> 'kind', d ->> 'action',
      jsonb_strip_nulls(jsonb_build_object('lane', d ->> 'lane', 'proposed_lane', req.lane)), who, at,
      coalesce(d ->> 'note', ''), d ->> 'stamp');
    n := n + 1;
  end loop;
  return n;
end $$;

-- ---------------------------------------------------------------- the score change form (R10)

create or replace function changedesk.change_score(rows jsonb) returns integer
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  d jsonb;
  cur changedesk.current_scores%rowtype;
  n integer := 0;
begin
  if jsonb_typeof(rows) <> 'array' then
    raise exception 'change_score expects a JSON array';
  end if;
  for d in select * from jsonb_array_elements(rows) loop
    if length(trim(coalesce(d ->> 'decided_by', ''))) = 0 or length(trim(coalesce(d ->> 'reason', ''))) = 0
       or coalesce(d ->> 'stamp', '') not like 'changedesk %' then
      raise exception 'a score change needs who made it, why, and a stamp';
    end if;
    select * into cur from changedesk.current_scores where request_id = d ->> 'request_id' and part = d ->> 'part';
    if cur.request_id is null then
      raise exception 'request % has no % part to change', d ->> 'request_id', d ->> 'part';
    end if;
    if cur.points = (d ->> 'points')::integer then
      raise exception 'the % part of % is already %', d ->> 'part', d ->> 'request_id', cur.points;
    end if;
    insert into changedesk.scores (request_id, part, points, reason, set_by, set_at, previous_points, is_change, run_id, stamp)
    values (d ->> 'request_id', d ->> 'part', (d ->> 'points')::integer, trim(d ->> 'reason'), trim(d ->> 'decided_by'),
      (d ->> 'decided_at')::timestamptz, cur.points, true, d ->> 'run_id', d ->> 'stamp');
    insert into changedesk.decisions (decision_id, run_id, request_id, kind, action, detail, decided_by, decided_at, note, stamp)
    values (d ->> 'decision_id', d ->> 'run_id', d ->> 'request_id', 'score', 'changed',
      jsonb_build_object('part', d ->> 'part', 'from', cur.points, 'to', (d ->> 'points')::integer),
      trim(d ->> 'decided_by'), (d ->> 'decided_at')::timestamptz, trim(d ->> 'reason'), d ->> 'stamp');
    n := n + 1;
  end loop;
  return n;
end $$;

-- ---------------------------------------------------------------- the decide list (R16)

-- Each row: do it next, merge it into another open item, or close it with a reason. Only an item
-- on the decide list on the day of the decision can be decided here. Returns the closed items, for
-- the message drafter.
--
-- Two texts, kept apart (fixed 25/11/2026 after test run n8n-8909): "reason" is the item's own
-- reason, from the choice made for that item; it becomes the close reason and the history note, and
-- it is all the drafter reads. "note" is the reviewer's note for the whole form, which may name other
-- items or people; it is kept on the decision row only.
create or replace function changedesk.decide(rows jsonb) returns jsonb
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  d jsonb;
  req changedesk.requests%rowtype;
  target changedesk.requests%rowtype;
  who text;
  at timestamptz;
  closed jsonb := '[]'::jsonb;
begin
  if jsonb_typeof(rows) <> 'array' then
    raise exception 'decide expects a JSON array';
  end if;
  for d in select * from jsonb_array_elements(rows) loop
    who := nullif(trim(coalesce(d ->> 'decided_by', '')), '');
    at := (d ->> 'decided_at')::timestamptz;
    if who is null or at is null or coalesce(d ->> 'stamp', '') not like 'changedesk %' then
      raise exception 'a decision needs who decided, when, and a stamp';
    end if;
    if not exists (select 1 from changedesk.decide_list_at(at::date) l where l.request_id = d ->> 'request_id') then
      raise exception 'request % is not on the decide list', d ->> 'request_id';
    end if;
    select * into req from changedesk.requests where request_id = d ->> 'request_id' for update;
    if d ->> 'action' = 'do_next' then
      update changedesk.requests set do_next = true, updated_at = now() where request_id = req.request_id;
    elsif d ->> 'action' = 'merge' then
      select * into target from changedesk.requests where request_id = d ->> 'merge_into';
      if target.request_id is null or target.request_id = req.request_id
         or target.status not in ('Triaged', 'Planned', 'In progress') then
        raise exception 'request % can only be merged into another open request', req.request_id;
      end if;
      if length(trim(coalesce(d ->> 'reason', ''))) = 0 then
        raise exception 'a merge of % needs a reason', req.request_id;
      end if;
      update changedesk.requests set status = 'Merged', merged_into = target.request_id, updated_at = now()
      where request_id = req.request_id;
      insert into changedesk.status_history (request_id, from_status, to_status, changed_at, changed_by, note, stamp)
      values (req.request_id, req.status, 'Merged', at, who, format('merged into %s: %s', target.request_id, d ->> 'reason'), d ->> 'stamp');
    elsif d ->> 'action' = 'close' then
      if length(trim(coalesce(d ->> 'reason', ''))) = 0 then
        raise exception 'a close of % needs a reason', req.request_id;
      end if;
      update changedesk.requests set status = 'Closed', close_reason = trim(d ->> 'reason'), updated_at = now()
      where request_id = req.request_id;
      insert into changedesk.status_history (request_id, from_status, to_status, changed_at, changed_by, note, stamp)
      values (req.request_id, req.status, 'Closed', at, who, trim(d ->> 'reason'), d ->> 'stamp');
      closed := closed || jsonb_build_object('request_id', req.request_id, 'title', req.title,
        'requester_role', req.requester_role, 'lane', req.lane, 'arrived_on', req.arrived_at::date, 'due_date', req.due_date,
        'age_days', at::date - req.arrived_at::date, 'reason', trim(d ->> 'reason'), 'decision_id', d ->> 'decision_id',
        'decided_by', who);
    else
      raise exception 'unknown decision %', d ->> 'action';
    end if;
    insert into changedesk.decisions (decision_id, run_id, request_id, kind, action, detail, decided_by, decided_at, note, stamp)
    values (d ->> 'decision_id', d ->> 'run_id', req.request_id, 'decide', d ->> 'action',
      jsonb_strip_nulls(jsonb_build_object('merge_into', d ->> 'merge_into', 'age_days', at::date - req.arrived_at::date,
        'reason', nullif(trim(coalesce(d ->> 'reason', '')), ''))),
      who, at, trim(coalesce(d ->> 'note', '')), d ->> 'stamp');
  end loop;
  return closed;
end $$;

-- ---------------------------------------------------------------- the message drafter's output

create or replace function changedesk.log_drafts(calls jsonb, drafts jsonb, handoffs jsonb) returns integer
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare n integer;
begin
  if jsonb_typeof(calls) <> 'array' or jsonb_typeof(drafts) <> 'array' or jsonb_typeof(handoffs) <> 'array' then
    raise exception 'log_drafts expects three JSON arrays';
  end if;
  insert into changedesk.run_log (call_id, run_id, step, source, request_id, case_id, model, model_served,
    playbook_name, playbook_version, playbook_sha256, engine_version, output_valid, stop_reason, error,
    input_tokens, output_tokens, latency_ms, api_request_id, called_at)
  select c.call_id, c.run_id, 'drafter', c.source, c.request_id, c.case_id, c.model, c.model_served,
    c.playbook_name, c.playbook_version, c.playbook_sha256, c.engine_version, c.output_valid, c.stop_reason, c.error,
    coalesce(c.input_tokens, 0), coalesce(c.output_tokens, 0), c.latency_ms, c.api_request_id, c.called_at
  from jsonb_to_recordset(calls) as c(call_id text, run_id text, source text, request_id text, case_id text,
    model text, model_served text, playbook_name text, playbook_version text, playbook_sha256 text,
    engine_version text, output_valid boolean, stop_reason text, error text, input_tokens integer,
    output_tokens integer, latency_ms integer, api_request_id text, called_at timestamptz);
  insert into changedesk.agent_handoffs (handoff_id, run_id, request_id, from_agent, to_agent, asked, why, evidence, confidence, call_id)
  select h.handoff_id, h.run_id, h.request_id, h.from_agent, h.to_agent, h.asked, h.why, h.evidence, h.confidence, h.call_id
  from jsonb_to_recordset(handoffs) as h(handoff_id text, run_id text, request_id text, from_agent text, to_agent text,
    asked text, why text, evidence text, confidence numeric, call_id text);
  -- From stage 5 a close draft also carries its facts (the request's id, title and the day it was asked, each with
  -- its source row) and the figures found in its text, so its figures can be traced like an update's (R23).
  insert into changedesk.updates (update_id, run_id, audience, kind, request_id, to_role, items, subject, body, call_id,
    drafted_by, drafted_at, draft_problems, facts, figures, status, stamp)
  select u.update_id, u.run_id, u.audience, u.kind, u.request_id, u.to_role, coalesce(u.items, '[]'::jsonb), u.subject, u.body, u.call_id,
    u.drafted_by, u.drafted_at, coalesce(u.draft_problems, ''), coalesce(u.facts, '[]'::jsonb), coalesce(u.figures, '[]'::jsonb), 'draft', u.stamp
  from jsonb_to_recordset(drafts) as u(update_id text, run_id text, audience text, kind text, request_id text, to_role text, items jsonb,
    subject text, body text, call_id text, drafted_by text, drafted_at timestamptz, draft_problems text, facts jsonb, figures jsonb, stamp text);
  get diagnostics n = row_count;
  if exists (select 1 from jsonb_to_recordset(drafts) as u(update_id text), changedesk.stale_facts(u.update_id) s) then
    raise exception 'a close draft holds a fact that is not its row''s value';
  end if;
  return n;
end $$;

-- ---------------------------------------------------------------- settings (R14, used from stage 3)

create or replace function changedesk.set_setting(k text, v jsonb, who text, why text) returns jsonb
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare old jsonb;
begin
  if length(trim(coalesce(who, ''))) = 0 or length(trim(coalesce(why, ''))) = 0 then
    raise exception 'a setting change needs who made it and why';
  end if;
  select value into old from changedesk.settings where key = k for update;
  if old is null then
    raise exception 'there is no setting %', k;
  end if;
  if jsonb_typeof(old) <> jsonb_typeof(v) then
    raise exception 'setting % holds a %, not a %', k, jsonb_typeof(old), jsonb_typeof(v);
  end if;
  -- The parameter is named in full: the table has a column called why too (found 25/11/2026, stage 3).
  update changedesk.settings set value = v, changed_by = trim(who), changed_at = now(), why = trim(set_setting.why) where key = k;
  return jsonb_build_object('key', k, 'from', old, 'to', v);
end $$;

-- ---------------------------------------------------------------- the week's plan (stage 3, R12 to R14)

-- One plan from scripts/planner.py: {plan_id, week_start, made_by, made_at, stamp, rows: [{request_id,
-- lane, hours, position, why}]}. The latest plan is the plan: its items move to Planned (In progress
-- stays as it is), and an item Planned by an earlier plan but left out of this one goes back to
-- Triaged. Every row is checked here as well as in the planner: the item is open, in that lane, not
-- waiting for a person (the week_plan trigger, R5) or a split decision, and given no more hours than it
-- has left; the plan holds no more hours than the week (setting hours_per_week).
create or replace function changedesk.save_plan(p jsonb) returns integer
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  r jsonb;
  req changedesk.requests%rowtype;
  pid text := nullif(trim(coalesce(p ->> 'plan_id', '')), '');
  who text := nullif(trim(coalesce(p ->> 'made_by', '')), '');
  wk date := (p ->> 'week_start')::date;
  at timestamptz := (p ->> 'made_at')::timestamptz;
  st text := coalesce(p ->> 'stamp', '');
  hrs numeric;
  logged numeric;
  total numeric := 0;
  n integer := 0;
  ids text[] := '{}';
begin
  if jsonb_typeof(p) <> 'object' or jsonb_typeof(p -> 'rows') <> 'array' then
    raise exception 'save_plan expects {plan_id, week_start, made_by, made_at, stamp, rows: [...]}';
  end if;
  if pid is null or who is null or at is null or st not like 'changedesk %' then
    raise exception 'a plan needs an id, who made it, when, and a stamp';
  end if;
  if extract(isodow from wk) <> 1 then
    raise exception 'a plan starts on a Monday, not %', wk;
  end if;
  if exists (select 1 from changedesk.week_plan where plan_id = pid) then
    raise exception 'plan % is saved already', pid;
  end if;
  for r in select * from jsonb_array_elements(p -> 'rows') loop
    select * into req from changedesk.requests where request_id = r ->> 'request_id' for update;
    if req.request_id is null then
      raise exception 'no request %', r ->> 'request_id';
    end if;
    if req.status not in ('Triaged', 'Planned', 'In progress') then
      raise exception 'request % is %, not open work', req.request_id, req.status;
    end if;
    if r ->> 'lane' is distinct from req.lane then
      raise exception 'request % is in lane %, not %', req.request_id, req.lane, r ->> 'lane';
    end if;
    if req.split_proposal is not null and jsonb_array_length(req.split_proposal) > 0 and req.split_decision is null then
      raise exception 'request % waits for a person to accept or reject its split', req.request_id;
    end if;
    hrs := (r ->> 'hours')::numeric;
    logged := coalesce((select sum(w.hours) from changedesk.work_log w where w.request_id = req.request_id), 0);
    if hrs is null or hrs <= 0 or hrs > req.size_hours - logged + 0.05 then
      raise exception 'request % has % hours left, not %', req.request_id, req.size_hours - logged, hrs;
    end if;
    insert into changedesk.week_plan (plan_id, week_start, lane, request_id, hours, position, made_at, made_by, why, stamp)
    values (pid, wk, req.lane, req.request_id, round(hrs, 1), (r ->> 'position')::integer, at, who, coalesce(r ->> 'why', ''), st);
    total := total + hrs;
    n := n + 1;
    ids := ids || req.request_id;
  end loop;
  if n = 0 then
    raise exception 'a plan with no rows plans nothing';
  end if;
  if total > changedesk.setting_num('hours_per_week') + 0.05 then
    raise exception 'the plan holds % hours, more than the week''s %', total, changedesk.setting_num('hours_per_week');
  end if;
  if (select count(distinct position) from changedesk.week_plan where plan_id = pid) <> n
     or (select max(position) from changedesk.week_plan where plan_id = pid) <> n then
    raise exception 'the plan''s positions must run 1 to %', n;
  end if;
  for req in select * from changedesk.requests where request_id = any (ids) and status = 'Triaged' loop
    update changedesk.requests set status = 'Planned', updated_at = now() where request_id = req.request_id;
    insert into changedesk.status_history (request_id, from_status, to_status, changed_at, changed_by, note, stamp)
    values (req.request_id, 'Triaged', 'Planned', at, who, format('in the plan for the week of %s (%s)', to_char(wk, 'DD/MM/YYYY'), pid), st);
  end loop;
  for req in select * from changedesk.requests where status = 'Planned' and not (request_id = any (ids)) loop
    update changedesk.requests set status = 'Triaged', updated_at = now() where request_id = req.request_id;
    insert into changedesk.status_history (request_id, from_status, to_status, changed_at, changed_by, note, stamp)
    values (req.request_id, 'Planned', 'Triaged', at, who, format('not in the plan for the week of %s (%s)', to_char(wk, 'DD/MM/YYYY'), pid), st);
  end loop;
  return n;
end $$;

-- ---------------------------------------------------------------- the forecast (stage 4, R18 to R20)

-- One run from scripts/forecast.py: the run (what it ran on), its rows (one per open item, plus one
-- per lane with request_id null), and the update drafts the trigger made. A 'forecast' run must give
-- every open item a row (R18: a date range, a service level or the chance of its date). A 'what-if'
-- run (another load or setting) may draft nothing. Drafts are drafts: nothing here can send one.
create or replace function changedesk.log_forecast(run jsonb, rows jsonb, drafts jsonb) returns integer
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  rid text := nullif(trim(coalesce(run ->> 'run_id', '')), '');
  missing text;
  n integer;
begin
  if jsonb_typeof(run) <> 'object' or jsonb_typeof(rows) <> 'array' or jsonb_typeof(drafts) <> 'array' then
    raise exception 'log_forecast expects a run object and two arrays';
  end if;
  if rid is null or coalesce(run ->> 'stamp', '') not like 'changedesk %' or length(trim(coalesce(run ->> 'made_by', ''))) = 0 then
    raise exception 'a forecast run needs an id, who made it, and a stamp';
  end if;
  insert into changedesk.forecast_runs (run_id, purpose, start_week, rule, runs, horizon_weeks, seed, load, safe_start_days,
    settings, summary, made_by, made_at, stamp)
  values (rid, run ->> 'purpose', (run ->> 'start_week')::date, run ->> 'rule', (run ->> 'runs')::integer,
    (run ->> 'horizon_weeks')::integer, (run ->> 'seed')::integer, (run ->> 'load')::numeric, (run ->> 'safe_start_days')::integer,
    coalesce(run -> 'settings', '{}'::jsonb), coalesce(run -> 'summary', '{}'::jsonb), trim(run ->> 'made_by'),
    (run ->> 'made_at')::timestamptz, run ->> 'stamp');
  insert into changedesk.forecasts (run_id, request_id, lane, kind, p50, p85, p95, service_level_days, chance, latest_safe_start,
    note, hours_in_per_week, hours_out_per_week, growing, finished_share, made_at)
  select rid, f.request_id, f.lane, f.kind, f.p50, f.p85, f.p95, f.service_level_days, f.chance, f.latest_safe_start,
    coalesce(f.note, ''), f.hours_in_per_week, f.hours_out_per_week, f.growing, f.finished_share, (run ->> 'made_at')::timestamptz
  from jsonb_to_recordset(rows) as f(request_id text, lane text, kind text, p50 date, p85 date, p95 date, service_level_days numeric,
    chance numeric, latest_safe_start date, note text, hours_in_per_week numeric, hours_out_per_week numeric, growing boolean,
    finished_share numeric);
  get diagnostics n = row_count;
  if run ->> 'purpose' = 'forecast' then
    select string_agg(r.request_id, ', ' order by r.request_id) into missing
    from changedesk.requests r
    where r.status in ('Triaged', 'Planned', 'In progress') and r.lane is not null
      and not exists (select 1 from changedesk.forecasts f where f.run_id = rid and f.request_id = r.request_id);
    if missing is not null then
      raise exception 'forecast % gives no forecast for %', rid, missing;
    end if;
  elsif jsonb_array_length(drafts) > 0 then
    raise exception 'a what-if run drafts no updates';
  end if;
  insert into changedesk.updates (update_id, run_id, audience, kind, request_id, subject, body, forecast_run_id, drafted_by,
    drafted_at, draft_problems, status, stamp)
  select u.update_id, rid, 'requester', 'status', u.request_id, u.subject, u.body, rid, u.drafted_by, u.drafted_at,
    coalesce(u.draft_problems, ''), 'draft', u.stamp
  from jsonb_to_recordset(drafts) as u(update_id text, request_id text, subject text, body text, drafted_by text,
    drafted_at timestamptz, draft_problems text, stamp text);
  return n;
end $$;

-- ---------------------------------------------------------------- stage 5: the update drafter's output (R20, R22, R23)

-- One run of scripts/draft_updates.py: its AI calls, the triggers it found, its drafts and its hand-offs to a
-- person. Each trigger is worked out again here from the two runs' forecasts rows, so only a real one (the 85%
-- date moved by more than update_trigger_days, or was gained or lost) is written. Each draft must sit behind a
-- trigger of its forecast run; a requester's update must cover that requester's items only, at least one of them
-- triggered; and every fact in a draft must be its source row's value now (stale_facts), so the drafter cannot
-- bring in a figure the pipe does not hold. Drafts are drafts: nothing here approves or sends one.
create or replace function changedesk.log_updates(calls jsonb, triggers jsonb, drafts jsonb, handoffs jsonb) returns integer
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  t jsonb;
  u jsonb;
  new_run changedesk.forecast_runs%rowtype;
  old_run changedesk.forecast_runs%rowtype;
  o date;
  nw date;
  days integer := changedesk.setting_num('update_trigger_days')::integer;
  bad text;
  n integer := 0;
begin
  if jsonb_typeof(calls) <> 'array' or jsonb_typeof(triggers) <> 'array' or jsonb_typeof(drafts) <> 'array' or jsonb_typeof(handoffs) <> 'array' then
    raise exception 'log_updates expects four JSON arrays';
  end if;
  insert into changedesk.run_log (call_id, run_id, step, source, request_id, case_id, update_id, model, model_served,
    playbook_name, playbook_version, playbook_sha256, engine_version, output_valid, stop_reason, error,
    input_tokens, output_tokens, latency_ms, api_request_id, called_at)
  select c.call_id, c.run_id, 'updater', c.source, c.request_id, null, c.update_id, c.model, c.model_served,
    c.playbook_name, c.playbook_version, c.playbook_sha256, c.engine_version, c.output_valid, c.stop_reason, c.error,
    coalesce(c.input_tokens, 0), coalesce(c.output_tokens, 0), c.latency_ms, c.api_request_id, c.called_at
  from jsonb_to_recordset(calls) as c(call_id text, run_id text, source text, request_id text, update_id text,
    model text, model_served text, playbook_name text, playbook_version text, playbook_sha256 text,
    engine_version text, output_valid boolean, stop_reason text, error text, input_tokens integer,
    output_tokens integer, latency_ms integer, api_request_id text, called_at timestamptz);

  for t in select * from jsonb_array_elements(triggers) loop
    select * into new_run from changedesk.forecast_runs where run_id = t ->> 'run_id';
    select * into old_run from changedesk.forecast_runs where run_id = t ->> 'previous_run_id';
    if new_run.run_id is null or old_run.run_id is null or new_run.purpose <> 'forecast' or old_run.purpose <> 'forecast'
       or old_run.made_at >= new_run.made_at then
      raise exception 'a trigger compares a forecast run with an earlier forecast run';
    end if;
    if not exists (select 1 from changedesk.forecasts where run_id = new_run.run_id and request_id = t ->> 'request_id')
       or not exists (select 1 from changedesk.forecasts where run_id = old_run.run_id and request_id = t ->> 'request_id') then
      raise exception 'request % is not in both forecast runs', t ->> 'request_id';
    end if;
    select p85 into o from changedesk.forecasts where run_id = old_run.run_id and request_id = t ->> 'request_id';
    select p85 into nw from changedesk.forecasts where run_id = new_run.run_id and request_id = t ->> 'request_id';
    if not ((o is null) <> (nw is null) or (o is not null and abs(nw - o) > days)) then
      raise exception 'request %: its 85%% date did not move by more than % days (% to %), so it triggers nothing', t ->> 'request_id', days, o, nw;
    end if;
    insert into changedesk.update_triggers (run_id, previous_run_id, request_id, old_p85, new_p85, moved_days, why)
    values (new_run.run_id, old_run.run_id, t ->> 'request_id', o, nw, case when o is not null and nw is not null then nw - o end,
      case when o is null then 'gained a date' when nw is null then 'lost its date' else 'moved' end)
    on conflict (run_id, request_id) do nothing;
  end loop;

  for u in select * from jsonb_array_elements(drafts) loop
    if coalesce(u ->> 'stamp', '') not like 'changedesk %' or length(trim(coalesce(u ->> 'drafted_by', ''))) = 0 then
      raise exception 'draft % carries no who-decided stamp', u ->> 'update_id';
    end if;
    if not exists (select 1 from changedesk.update_triggers where run_id = u ->> 'forecast_run_id') then
      raise exception 'draft % is not behind a trigger of forecast run %', u ->> 'update_id', u ->> 'forecast_run_id';
    end if;
    if u ->> 'audience' = 'requester' then
      if jsonb_array_length(coalesce(u -> 'items', '[]'::jsonb)) = 0 then
        raise exception 'requester update % covers no items', u ->> 'update_id';
      end if;
      select string_agg(x, ', ') into bad from jsonb_array_elements_text(u -> 'items') x
      where not exists (select 1 from changedesk.requests r where r.request_id = x and r.requester_role = u ->> 'to_role');
      if bad is not null then
        raise exception 'requester update % names items that are not %''s: %', u ->> 'update_id', u ->> 'to_role', bad;
      end if;
      if not exists (select 1 from jsonb_array_elements_text(u -> 'items') x
                     join changedesk.update_triggers g on g.request_id = x and g.run_id = u ->> 'forecast_run_id') then
        raise exception 'requester update % covers no item the trigger named', u ->> 'update_id';
      end if;
    end if;
    insert into changedesk.updates (update_id, run_id, audience, kind, request_id, to_role, items, subject, body, forecast_run_id,
      call_id, drafted_by, drafted_at, draft_problems, facts, figures, coverage, status, stamp)
    values (u ->> 'update_id', u ->> 'run_id', u ->> 'audience', 'status', nullif(u ->> 'request_id', ''), u ->> 'to_role',
      coalesce(u -> 'items', '[]'::jsonb), u ->> 'subject', u ->> 'body', u ->> 'forecast_run_id', u ->> 'call_id', u ->> 'drafted_by',
      (u ->> 'drafted_at')::timestamptz, coalesce(u ->> 'draft_problems', ''), coalesce(u -> 'facts', '[]'::jsonb),
      coalesce(u -> 'figures', '[]'::jsonb), coalesce(u -> 'coverage', '[]'::jsonb), 'draft', u ->> 'stamp');
    select string_agg(s.fact_id || ' (' || s.says || ')', '; ') into bad from changedesk.stale_facts(u ->> 'update_id') s;
    if bad is not null then
      raise exception 'draft % holds facts that are not their rows'' values: %', u ->> 'update_id', bad;
    end if;
    n := n + 1;
  end loop;

  insert into changedesk.agent_handoffs (handoff_id, run_id, request_id, from_agent, to_agent, asked, why, evidence, confidence, call_id)
  select h.handoff_id, h.run_id, h.request_id, h.from_agent, h.to_agent, h.asked, h.why, h.evidence, h.confidence, h.call_id
  from jsonb_to_recordset(handoffs) as h(handoff_id text, run_id text, request_id text, from_agent text, to_agent text,
    asked text, why text, evidence text, confidence numeric, call_id text);
  return n;
end $$;

-- ---------------------------------------------------------------- stage 5: a person approves each update (R24)

-- From the approval form (n8n "Change Desk: approve updates"): each row approves or rejects one draft, with the
-- person's name, a reason for a rejection, and a stamp. Approval is refused for a draft with problems (the code
-- checks found some), or whose facts no longer match their rows (the pipe changed: draft it again), and for a
-- decider that is one of the build's agents. An approved update is placed in the outbox with its approval
-- decision; nothing is sent. Close messages from the decide list (stage 2) are approved here too.
create or replace function changedesk.approve_updates(rows jsonb) returns jsonb
language plpgsql security definer set search_path = changedesk, pg_temp as $$
declare
  d jsonb;
  upd changedesk.updates%rowtype;
  who text;
  at timestamptz;
  stale text;
  role_to text;
  approved jsonb := '[]'::jsonb;
  rejected jsonb := '[]'::jsonb;
begin
  if jsonb_typeof(rows) <> 'array' then
    raise exception 'approve_updates expects a JSON array';
  end if;
  for d in select * from jsonb_array_elements(rows) loop
    who := nullif(regexp_replace(trim(coalesce(d ->> 'decided_by', '')), '\s+', ' ', 'g'), '');
    at := (d ->> 'decided_at')::timestamptz;
    if who is null or at is null or coalesce(d ->> 'stamp', '') not like 'changedesk %' then
      raise exception 'an approval needs who decided, when, and a stamp';
    end if;
    if lower(who) in ('triage_agent', 'message_drafter', 'update_drafter', 'update trigger (template, no ai)',
                      'forecast (plain script)', 'planner (plain script)') then
      raise exception '% is one of the build''s agents: a person approves', who;
    end if;
    select * into upd from changedesk.updates where update_id = d ->> 'update_id' for update;
    if upd.update_id is null then
      raise exception 'no update %', d ->> 'update_id';
    end if;
    if upd.status <> 'draft' then
      raise exception 'update % is % already', upd.update_id, upd.status;
    end if;
    if d ->> 'action' = 'approved' then
      if upd.draft_problems <> '' then
        raise exception 'update % has draft problems (%): it can only be rejected', upd.update_id, upd.draft_problems;
      end if;
      select string_agg(s.fact_id || ' ' || s.says || ': drafted ' || coalesce(s.drafted, 'none') || ', now ' || coalesce(s.now, 'none'), '; ')
        into stale from changedesk.stale_facts(upd.update_id) s;
      if stale is not null then
        raise exception 'update % no longer matches the pipe (%): reject it and draft it again', upd.update_id, stale;
      end if;
      role_to := coalesce(upd.to_role, (select r.requester_role from changedesk.requests r where r.request_id = upd.request_id));
      insert into changedesk.decisions (decision_id, run_id, request_id, kind, action, detail, decided_by, decided_at, note, stamp)
      values (d ->> 'decision_id', d ->> 'run_id', upd.request_id, 'update', 'approved',
        jsonb_build_object('update_id', upd.update_id, 'audience', upd.audience, 'to_role', role_to), who, at,
        trim(coalesce(d ->> 'note', '')), d ->> 'stamp');
      update changedesk.updates set status = 'approved', approved_by = who, approved_at = at, decision_id = d ->> 'decision_id'
      where update_id = upd.update_id;
      insert into changedesk.outbox (outbox_id, update_id, decision_id, audience, to_role, subject, body, approved_by, approved_at, stamp)
      values ('O-' || upd.update_id, upd.update_id, d ->> 'decision_id', upd.audience, role_to, upd.subject, upd.body, who, at, d ->> 'stamp');
      approved := approved || to_jsonb(upd.update_id);
    elsif d ->> 'action' = 'rejected' then
      if length(trim(coalesce(d ->> 'reason', ''))) = 0 then
        raise exception 'a rejection of % needs a reason', upd.update_id;
      end if;
      insert into changedesk.decisions (decision_id, run_id, request_id, kind, action, detail, decided_by, decided_at, note, stamp)
      values (d ->> 'decision_id', d ->> 'run_id', upd.request_id, 'update', 'rejected',
        jsonb_build_object('update_id', upd.update_id, 'audience', upd.audience, 'reason', trim(d ->> 'reason')), who, at,
        trim(coalesce(d ->> 'note', '')), d ->> 'stamp');
      update changedesk.updates set status = 'rejected', approved_by = who, approved_at = at, decision_id = d ->> 'decision_id'
      where update_id = upd.update_id;
      rejected := rejected || to_jsonb(upd.update_id);
    else
      raise exception 'unknown approval action %', d ->> 'action';
    end if;
  end loop;
  return jsonb_build_object('approved', approved, 'rejected', rejected, 'outbox', (select coalesce(jsonb_agg('O-' || x), '[]'::jsonb)
                                                                                     from jsonb_array_elements_text(approved) x));
end $$;
