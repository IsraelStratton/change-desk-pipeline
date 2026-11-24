// Change Desk, stage 2: the scoring engine. The score with its working, the score change form, and
// the decide list form.
//
// Used the same three ways as engine/triage.js. Pure functions only. The score itself is worked out
// in the store (db/views.sql: score_working, score_totals, ranked_standard), from the parts and the
// weights in the settings, so every figure on a page can be traced to a row. This file builds the
// forms people use to change a part (R10) and to decide what to do with old items (R16), and turns
// their answers into the rows the store's checked functions take. It also holds the effort rule
// (effortPoints) that the store's effort_points function mirrors; a test checks they agree.

// ---------------------------------------------------------------- imports (not pasted into n8n: there, common.js sits above this file)
/* eslint-disable no-var */
var C = require('./common.js');
var escapeHtml = C.escapeHtml;
var isoSeconds = C.isoSeconds;
// ---------------------------------------------------------------- end of imports

const SCORING_ENGINE_VERSION = '1.0.0';
const SCORE_PARTS = ['value', 'effort', 'risk', 'goal_fit', 'readiness'];
const PART_WORDS = { value: 'value', effort: 'effort', risk: 'risk', goal_fit: 'goal fit', readiness: 'readiness' };
const LEAVE = 'Leave on the list for now';
const DO_NEXT = 'Do it next';
const MERGE_PREFIX = 'Merge into ';
const CLOSE_PREFIX = 'Close: ';
const CLOSE_REASONS = [
  'no longer needed',
  'overtaken by another change',
  'too little value for the work it needs',
  'the requester found another way',
];
const MAX_MERGE_CHOICES = 3;

function scoreClip(s, max) {
  const t = String(s === null || s === undefined ? '' : s);
  return t.length > max ? `${t.slice(0, max - 1)}…` : t;
}

function scoreBands(settings) {
  const bands = settings && settings.effort_points_by_size;
  if (!Array.isArray(bands) || !bands.length) throw new Error('settings: effort_points_by_size is missing');
  return bands;
}

// The effort rule: the first band whose limit the size is within. Mirrors changedesk.effort_points.
function sizeEffortPoints(hours, settings) {
  for (const b of scoreBands(settings)) {
    if (b.max_hours === null || b.max_hours === undefined || Number(hours) <= Number(b.max_hours)) return Number(b.points);
  }
  throw new Error('settings: no effort band fits');
}

// parts: {value, effort, risk, goal_fit, readiness} as whole numbers. Returns the score and its working.
function scoreWithWorking(parts, weights) {
  let total = 0;
  const lines = [];
  for (const p of SCORE_PARTS) {
    if (!Number.isInteger(parts[p]) || parts[p] < 1 || parts[p] > 10) throw new Error(`score: ${p} must be a whole number from 1 to 10`);
    const w = Number(weights[p]);
    const pts = Math.round(parts[p] * w * 100) / 100;
    total += pts;
    lines.push(`${p} ${parts[p]} x ${w} = ${pts.toFixed(2)}`);
  }
  return { score: Math.round(total * 100) / 100, working: lines.join(' + ') };
}

function rankPoints(score, weeksWaited, rate) {
  return Math.round((Number(score) + Math.max(0, Math.floor(weeksWaited)) * Number(rate)) * 100) / 100;
}

// ---------------------------------------------------------------- the score change form (R10)

function itemLabel(row) {
  return `${row.request_id} ${scoreClip(row.title, 60)}`;
}

// ranked: rows of changedesk.standard_ranked. working: rows of changedesk.score_working for them.
function buildScoreForm(ranked, working, meta) {
  const m = meta || {};
  const byItem = {};
  for (const w of working || []) (byItem[w.request_id] = byItem[w.request_id] || []).push(w);
  const rows = (ranked || []).map((r) => {
    const parts = (byItem[r.request_id] || []).slice().sort((a, b) => SCORE_PARTS.indexOf(a.part) - SCORE_PARTS.indexOf(b.part));
    const partCells = parts.map((p) => `${escapeHtml(PART_WORDS[p.part])} <b>${escapeHtml(p.points)}</b>`
      + `${p.is_change ? ` (was ${escapeHtml(p.previous_points)}, changed by ${escapeHtml(p.set_by)})` : ''}: ${escapeHtml(p.reason)}`).join('<br>');
    return '<tr>'
      + `<td><b>${escapeHtml(r.rank)}</b></td><td><b>${escapeHtml(r.request_id)}</b><br>${escapeHtml(r.title)}</td>`
      + `<td>score ${escapeHtml(r.score)} + ${escapeHtml(r.weeks_waited)} weeks waited x the age points = <b>${escapeHtml(r.rank_points)}</b>${r.do_next ? '<br><b>do it next</b>' : ''}</td>`
      + `<td>${partCells}</td></tr>`;
  }).join('');
  const html = `<p><b>The standard lane, ranked.</b> Score plus points for each week waited; "do it next" from the decide list comes first. `
    + 'Change one part of one item per submission. The change is logged with your name and reason, and the old value is kept.</p>'
    + `<table><tr><th>Rank</th><th>Item</th><th>Rank points</th><th>Parts and reasons</th></tr>${rows}</table>`;
  const items = (ranked || []).map((r) => ({ option: itemLabel(r) }));
  if (!items.length) throw new Error('score form: the standard lane has no waiting items');
  return [
    { fieldType: 'html', html: m.run_id ? `<p>Run ${escapeHtml(m.run_id)}.</p>${html}` : html },
    { fieldLabel: 'Your name or reviewer label', fieldName: 'decided_by', fieldType: 'text', requiredField: true, placeholder: 'e.g. desk-lead' },
    { fieldLabel: 'Item', fieldName: 'item', fieldType: 'dropdown', requiredField: true, fieldOptions: { values: items } },
    { fieldLabel: 'Part to change', fieldName: 'part', fieldType: 'dropdown', requiredField: true,
      fieldOptions: { values: SCORE_PARTS.map((p) => ({ option: PART_WORDS[p] })) } },
    { fieldLabel: 'New value (1 to 10; 10 is best for doing it)', fieldName: 'points', fieldType: 'dropdown', requiredField: true,
      fieldOptions: { values: Array.from({ length: 10 }, (_, i) => ({ option: String(i + 1) })) } },
    { fieldLabel: 'Why (kept in the log)', fieldName: 'reason', fieldType: 'textarea', requiredField: true },
  ];
}

function scoreStamp(decisionId, action, who, at) {
  return `changedesk ${decisionId} | no AI | score parts (settings score_weights) | ${action} by ${who} | ${isoSeconds(at)}`;
}

// Returns {rows, message}. rows is empty, with the reason in message, when the answer changes nothing.
function applyScoreChange(ranked, working, form, meta) {
  const m = meta || {};
  const f = form || {};
  const who = String(f.decided_by || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  const reason = String(f.reason || '').trim().slice(0, 1000);
  if (!who) throw new Error('score change: no reviewer name, so nothing is recorded');
  if (!reason) throw new Error('score change: no reason, so nothing is recorded');
  const item = (ranked || []).find((r) => itemLabel(r) === f.item);
  if (!item) throw new Error('score change: the item chosen is not in the ranked list');
  const part = SCORE_PARTS.find((p) => PART_WORDS[p] === f.part);
  if (!part) throw new Error('score change: unknown part');
  const points = Number(f.points);
  if (!Number.isInteger(points) || points < 1 || points > 10) throw new Error('score change: the value must be a whole number from 1 to 10');
  const current = (working || []).find((w) => w.request_id === item.request_id && w.part === part);
  if (!current) throw new Error(`score change: ${item.request_id} has no ${PART_WORDS[part]} part`);
  if (Number(current.points) === points) {
    return { rows: [], message: `No change: the ${PART_WORDS[part]} of ${item.request_id} is already ${points}.` };
  }
  const at = isoSeconds(m.decided_at || new Date().toISOString());
  const decisionId = `P-${String(m.run_id || 'run').replace(/[^A-Za-z0-9-]/g, '')}-${item.request_id}-${part}`;
  return {
    rows: [{ decision_id: decisionId, run_id: m.run_id, request_id: item.request_id, part, points, reason, decided_by: who,
      decided_at: at, stamp: scoreStamp(decisionId, `${part} ${current.points} to ${points}`, who, at) }],
    message: `${item.request_id}: ${PART_WORDS[part]} changed from ${current.points} to ${points} by ${who}. The old value is kept in the log.`,
  };
}

// ---------------------------------------------------------------- the decide list form (R16)

// list: rows of changedesk.decide_list. open: open items {request_id, title, playbook, status} a
// listed item may be merged into. Up to three, with the same playbook, are offered for each.
function mergeChoices(row, open) {
  return (open || []).filter((o) => o.request_id !== row.request_id && o.playbook === row.playbook)
    .slice(0, MAX_MERGE_CHOICES);
}

function decideOptions(row, open) {
  const opts = [LEAVE, DO_NEXT];
  for (const o of mergeChoices(row, open)) opts.push(`${MERGE_PREFIX}${o.request_id} (${scoreClip(o.title, 50)})`);
  for (const r of CLOSE_REASONS) opts.push(`${CLOSE_PREFIX}${r}`);
  return opts;
}

function decideKey(requestId) {
  return `decide_${String(requestId).replace(/[^A-Za-z0-9]/g, '_')}`;
}

function buildDecideForm(list, open, meta) {
  const m = meta || {};
  if (!(list || []).length) throw new Error('decide form: nothing is past its age limit');
  const rows = list.map((r) => '<tr>'
    + `<td><b>${escapeHtml(r.request_id)}</b><br>${escapeHtml(r.requester_role)}</td><td>${escapeHtml(r.title)}</td>`
    + `<td>${escapeHtml(r.lane)}</td><td>${escapeHtml(r.age_days)} days (limit ${escapeHtml(r.age_limit_days)}, ${escapeHtml(r.days_over)} over)</td>`
    + `<td>${escapeHtml(r.score === null || r.score === undefined ? '' : r.score)}</td></tr>`).join('');
  const html = `<p><b>${list.length} items are past their lane's age limit.</b> Decide each one: do it next, merge it, or close it with a reason. `
    + 'Nothing is left to rot. A close drafts a message to the requester for a person to approve: nothing is sent.</p>'
    + `<table><tr><th>Item</th><th>Title</th><th>Lane</th><th>Age</th><th>Score</th></tr>${rows}</table>`;
  const fields = [
    { fieldType: 'html', html: m.run_id ? `<p>Run ${escapeHtml(m.run_id)}.</p>${html}` : html },
    { fieldLabel: 'Your name or reviewer label', fieldName: 'decided_by', fieldType: 'text', requiredField: true, placeholder: 'e.g. desk-lead' },
  ];
  for (const r of list) {
    fields.push({ fieldLabel: `${r.request_id} ${scoreClip(r.title, 60)} (${r.age_days} days)`, fieldName: decideKey(r.request_id),
      fieldType: 'dropdown', requiredField: true, fieldOptions: { values: decideOptions(r, open).map((o) => ({ option: o })) } });
  }
  fields.push({ fieldLabel: 'Your reason in your own words (added to each merge and close; optional)', fieldName: 'note', fieldType: 'textarea', requiredField: false });
  return fields;
}

function decideStamp(decisionId, action, who, at) {
  return `changedesk ${decisionId} | no AI | decide list (settings age limits) | ${action} by ${who} | ${isoSeconds(at)}`;
}

function applyDecideChoices(list, open, form, meta) {
  const m = meta || {};
  const f = form || {};
  const who = String(f.decided_by || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  if (!who) throw new Error('decide: no reviewer name, so nothing is recorded');
  const note = String(f.note || '').trim().slice(0, 500);
  const at = isoSeconds(m.decided_at || new Date().toISOString());
  const rows = [];
  for (const r of list || []) {
    const choice = f[decideKey(r.request_id)];
    if (!choice || choice === LEAVE) continue;
    if (!decideOptions(r, open).includes(choice)) throw new Error(`decide: unknown choice for ${r.request_id}`);
    const decisionId = `D-${String(m.run_id || 'run').replace(/[^A-Za-z0-9-]/g, '')}-${r.request_id}`;
    const row = { decision_id: decisionId, run_id: m.run_id, request_id: r.request_id, decided_by: who, decided_at: at, merge_into: null, reason: '' };
    if (choice === DO_NEXT) {
      row.action = 'do_next';
      row.reason = note;
    } else if (choice.startsWith(MERGE_PREFIX)) {
      row.action = 'merge';
      row.merge_into = choice.slice(MERGE_PREFIX.length).split(' ')[0];
      row.reason = `the same need as ${row.merge_into}${note ? `. ${note}` : ''}`;
    } else {
      row.action = 'close';
      row.reason = `${choice.slice(CLOSE_PREFIX.length).replace(/^./, (c) => c.toUpperCase())}${note ? `. ${note}` : '.'}`;
    }
    row.stamp = decideStamp(decisionId, row.action === 'merge' ? `merge into ${row.merge_into}` : row.action, who, at);
    rows.push(row);
  }
  return rows;
}

// ---------------------------------------------------------------- exports (not pasted into n8n)

const SCORING = {
  SCORING_ENGINE_VERSION, SCORE_PARTS, PART_WORDS, CLOSE_REASONS, LEAVE, DO_NEXT, sizeEffortPoints, scoreWithWorking, rankPoints,
  buildScoreForm, applyScoreChange, mergeChoices, decideOptions, decideKey, buildDecideForm, applyDecideChoices, itemLabel,
};
if (typeof module !== 'undefined' && module.exports) module.exports = SCORING;
