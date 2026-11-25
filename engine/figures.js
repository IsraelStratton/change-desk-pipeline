// Change Desk, stage 5: every figure in a text, and the fact it comes from (R23).
//
// A fact is a row's value with its source (changedesk.fact_value reads it). An update, or a close message, is
// drafted from facts; this file finds every figure in the draft (request ids, dates, percentages, money, numbers,
// and figures written in words) and traces each to a fact with the same value. A figure with no fact is a draft
// problem, and a draft with a problem can only be rejected. Used by engine/updates.js (the three audiences),
// engine/drafter.js (close messages) and scripts/check_updates.py (the check script). Pure functions only.

// ---------------------------------------------------------------- imports (not pasted into n8n: this file needs none)
// ---------------------------------------------------------------- end of imports

// ---------------------------------------------------------------- how a fact is shown

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function showDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
  if (!m) return String(iso);
  return `${Number(m[3])} ${MONTH_NAMES[Number(m[2]) - 1]} ${m[1]}`;
}

function trimNumber(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return String(x);
  return String(Math.round(n * 1000) / 1000);
}

// What the drafter sees for one fact. Dates in full, fractions as percentages, numbers with their unit.
function showFact(f) {
  if (f.value === null || f.value === undefined) return 'none';
  if (f.kind === 'date') return showDate(f.value);
  if (f.kind === 'percent') return `${trimNumber(Number(f.value) * 100)}%`;
  if (f.kind === 'number') return f.unit ? `${trimNumber(f.value)} ${f.unit}` : trimNumber(f.value);
  if (f.kind === 'flag') return (f.value === '0' || f.value === 'false') ? 'no' : 'yes';
  return String(f.value);
}

// ---------------------------------------------------------------- every figure in a text, and its fact (R23)

const MONTHS = { january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8, september: 9, october: 10, november: 11,
  december: 12, jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, aug: 8, sep: 9, sept: 9, oct: 10, nov: 11, dec: 12 };
const MONTH_PART = '(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)';
const ID_RE = /\bCD-\d{4,}\b/g;
const DATE_ISO_RE = /\b(\d{4})-(\d{2})-(\d{2})\b/g;
const DATE_SLASH_RE = /\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b/g;
const DATE_DMY_RE = new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+${MONTH_PART}\\.?(?:,?\\s+(\\d{4}))?\\b`, 'gi');
const DATE_MDY_RE = new RegExp(`\\b${MONTH_PART}\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?(?:,?\\s+(\\d{4}))?\\b`, 'gi');
const PERCENT_RE = /(?<![\w.])(\d+(?:\.\d+)?)\s?(?:%|per\s?cent\b)/gi;
const MONEY_RE = /(?:US)?\$\s?\d[\d,]*(?:\.\d+)?/g;
const NUMBER_RE = /(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?!\w)/g;
// A number written as a word is a figure too, traced like one: "three fixed dates" needs a fact of 3. A word joined to
// the next ("two-minute", "three-step") describes a thing and is not a count. "Dozen", "half" and "twice" have no one
// value to trace, so they stay a problem: the drafter is asked to write figures in digits.
const NUMBER_WORDS_RE = /\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|dozen|half|twice)\b(?!-\w)/gi;
const WORD_VALUES = { two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13,
  fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60,
  seventy: 70, eighty: 80, ninety: 90, hundred: 100, thousand: 1000 };
const UNIT_RE = /^\s*-?\s*(?:[A-Za-z]+\s+){0,2}?(hours?|days?|weeks?|items?|requests?|runs?)\b/i;
const UNIT_OF = { hour: 'hours', hours: 'hours', day: 'days', days: 'days', week: 'weeks', weeks: 'weeks', item: 'items', items: 'items',
  request: 'items', requests: 'items', run: 'runs', runs: 'runs' };

function pad2(n) {
  return String(n).padStart(2, '0');
}

function validDay(y, m, d) {
  if (!(m >= 1 && m <= 12 && d >= 1 && d <= 31)) return false;
  if (y === null) return true;
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
}

// Blank out the text of each match so a later pattern cannot read the same characters again.
function maskSpan(chars, start, end) {
  for (let i = start; i < end; i++) chars[i] = ' ';
}

function decimals(s) {
  const m = /\.(\d+)$/.exec(String(s));
  return m ? m[1].length : 0;
}

// Every figure in a text: request ids, dates, percentages, money, plain numbers, and figures written in words.
// Titles in the pack are taken out first: a title is the requester's own words, traced as a whole.
function figuresIn(text, pack) {
  const src = String(text || '');
  const chars = src.split('');
  const lower = src.toLowerCase();
  for (const t of titlesOf(pack)) {
    const lt = t.toLowerCase();
    let i = lower.indexOf(lt);
    while (i >= 0) { maskSpan(chars, i, i + lt.length); i = lower.indexOf(lt, i + lt.length); }
  }
  const figs = [];
  const run = (re, make) => {
    const masked = chars.join('');
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(masked)) !== null) {
      const f = make(m);
      if (f) {
        f.text = m[0].trim();
        f.at = m.index;
        figs.push(f);
        maskSpan(chars, m.index, m.index + m[0].length);
      }
    }
  };
  run(ID_RE, (m) => ({ kind: 'id', value: m[0] }));
  run(DATE_ISO_RE, (m) => (validDay(+m[1], +m[2], +m[3]) ? { kind: 'date', value: `${m[1]}-${m[2]}-${m[3]}`, year: +m[1] } : null));
  run(DATE_SLASH_RE, (m) => (validDay(+m[3], +m[2], +m[1]) ? { kind: 'date', value: `${m[3]}-${pad2(m[2])}-${pad2(m[1])}`, year: +m[3] } : null));
  run(DATE_DMY_RE, (m) => {
    const mon = MONTHS[m[2].toLowerCase()];
    const y = m[3] ? +m[3] : null;
    return validDay(y, mon, +m[1]) ? { kind: 'date', value: y ? `${y}-${pad2(mon)}-${pad2(m[1])}` : `--${pad2(mon)}-${pad2(m[1])}`, year: y } : null;
  });
  run(DATE_MDY_RE, (m) => {
    const mon = MONTHS[m[1].toLowerCase()];
    const y = m[3] ? +m[3] : null;
    return validDay(y, mon, +m[2]) ? { kind: 'date', value: y ? `${y}-${pad2(mon)}-${pad2(m[2])}` : `--${pad2(mon)}-${pad2(m[2])}`, year: y } : null;
  });
  run(PERCENT_RE, (m) => ({ kind: 'percent', value: Number(m[1]), places: decimals(m[1]) }));
  run(MONEY_RE, (m) => ({ kind: 'money', value: m[0] }));
  run(NUMBER_RE, (m) => {
    const after = src.slice(m.index + m[0].length, m.index + m[0].length + 40);
    const u = UNIT_RE.exec(after);
    return { kind: 'number', value: Number(m[0].replace(/,/g, '')), places: decimals(m[0]), unit: u ? UNIT_OF[u[1].toLowerCase()] : null };
  });
  run(NUMBER_WORDS_RE, (m) => {
    const w = m[0].toLowerCase();
    if (!(w in WORD_VALUES)) return { kind: 'number_word', value: w };
    const after = src.slice(m.index + m[0].length, m.index + m[0].length + 40);
    const u = UNIT_RE.exec(after);
    return { kind: 'number', value: WORD_VALUES[w], places: 0, unit: u ? UNIT_OF[u[1].toLowerCase()] : null, in_words: true };
  });
  return figs.sort((a, b) => a.at - b.at);
}

// The requesters' own titles in a pack: the items' titles and any others the pack lists (the manager's pack).
function titlesOf(pack) {
  const out = [];
  for (const it of (pack && pack.items) || []) out.push(String(it.title || ''));
  for (const t of (pack && pack.titles) || []) out.push(String(t || ''));
  return Array.from(new Set(out.filter((t) => t.length >= 4))).sort((a, b) => b.length - a.length);
}

function roundTo(x, places) {
  return Number(Number(x).toFixed(places));
}

// The facts a figure could be: same kind, same value (a figure may round a fact to the places it shows).
function factsFor(fig, facts) {
  const fs = facts || [];
  if (fig.kind === 'id') return fs.filter((f) => f.kind === 'id' && f.value === fig.value);
  if (fig.kind === 'date') {
    return fs.filter((f) => f.kind === 'date' && f.value && (fig.year ? f.value === fig.value : String(f.value).slice(4) === fig.value.slice(1)));
  }
  if (fig.kind === 'percent') {
    return fs.filter((f) => f.kind === 'percent' && f.value !== null && roundTo(Number(f.value) * 100, fig.places) === fig.value);
  }
  if (fig.kind === 'number') {
    const same = fs.filter((f) => f.kind === 'number' && f.value !== null && roundTo(f.value, fig.places) === fig.value);
    if (fig.unit) {
      const unitMatch = same.filter((f) => f.unit === fig.unit);
      if (unitMatch.length) return unitMatch;
      return same.filter((f) => !f.unit);
    }
    if (same.length) return same;
    // A year on its own is the year of a date fact.
    if (fig.places === 0 && fig.value >= 2020 && fig.value <= 2039) return fs.filter((f) => f.kind === 'date' && String(f.value).startsWith(`${fig.value}-`));
    return [];
  }
  return [];
}

function traceFigures(text, pack) {
  const figures = figuresIn(text, pack).map((fig) => {
    const found = fig.kind === 'number_word' ? [] : factsFor(fig, pack.facts);
    return { text: fig.text, kind: fig.kind, value: fig.value, unit: fig.unit || null, fact_id: found.length ? found[0].id : null,
      also: found.slice(1).map((f) => f.id) };
  });
  return { figures, untraced: figures.filter((f) => !f.fact_id && f.kind !== 'number_word'), in_words: figures.filter((f) => f.kind === 'number_word') };
}

// ---------------------------------------------------------------- exports (not pasted into n8n)

const FIGURES = {
  showDate, showFact, trimNumber, figuresIn, titlesOf, factsFor, traceFigures, maskSpan, roundTo,
};
if (typeof module !== 'undefined' && module.exports) module.exports = FIGURES;
