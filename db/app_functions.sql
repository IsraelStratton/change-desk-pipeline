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
        'requester_role', req.requester_role, 'lane', req.lane, 'arrived_on', req.arrived_at::date,
        'age_days', at::date - req.arrived_at::date, 'reason', trim(d ->> 'reason'), 'decision_id', d ->> 'decision_id',
        'decided_by', who);
    else
      raise exception 'unknown decision %', d ->> 'action';
    end if;
    insert into changedesk.decisions (decision_id, run_id, request_id, kind, action, detail, decided_by, decided_at, note, stamp)
    values (d ->> 'decision_id', d ->> 'run_id', req.request_id, 'decide', d ->> 'action',
      jsonb_strip_nulls(jsonb_build_object('merge_into', d ->> 'merge_into', 'age_days', at::date - req.arrived_at::date)),
      who, at, coalesce(d ->> 'reason', ''), d ->> 'stamp');
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
  insert into changedesk.updates (update_id, run_id, audience, kind, request_id, subject, body, call_id,
    drafted_by, drafted_at, draft_problems, status, stamp)
  select u.update_id, u.run_id, u.audience, u.kind, u.request_id, u.subject, u.body, u.call_id,
    u.drafted_by, u.drafted_at, coalesce(u.draft_problems, ''), 'draft', u.stamp
  from jsonb_to_recordset(drafts) as u(update_id text, run_id text, audience text, kind text, request_id text,
    subject text, body text, call_id text, drafted_by text, drafted_at timestamptz, draft_problems text, stamp text);
  get diagnostics n = row_count;
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
  update changedesk.settings set value = v, changed_by = trim(who), changed_at = now(), why = trim(why) where key = k;
  return jsonb_build_object('key', k, 'from', old, 'to', v);
end $$;
