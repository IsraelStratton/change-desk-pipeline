// Change Desk: the shared helpers, copied from the GTM pipeline's engine (engine/routing.js).
//
// These functions are copied as they are, not imported across repositories: the playbook
// parser, SHA-256 (the n8n sandbox has no crypto module), the code screen's injection patterns,
// the HTTP reply reader, escaping and time formatting. The Change Desk's own engines
// (triage.js, scoring.js, drafter.js) sit under this file in each n8n Code node, and require it
// in Node. Pure functions only: no network, no files, no clock.

function unquote(v) {
  const t = String(v).trim();
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) return t.slice(1, -1);
  return t;
}

function parseFrontMatter(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  if (!m) throw new Error('playbook: no front matter between --- lines');
  const fm = {};
  let block = null;
  for (const raw of m[1].split(/\r?\n/)) {
    if (!raw.trim() || raw.trim().startsWith('#')) continue;
    const line = /^(\s*)([A-Za-z0-9_-]+):\s*(.*)$/.exec(raw);
    if (!line) throw new Error(`playbook: cannot read the front matter line "${raw.trim()}"`);
    const indent = line[1].length;
    const key = line[2];
    const value = line[3];
    if (indent === 0) {
      if (value === '') {
        fm[key] = {};
        block = key;
      } else {
        fm[key] = unquote(value);
        block = null;
      }
    } else {
      if (!block) throw new Error(`playbook: "${key}" is indented but sits under no block`);
      fm[block][key] = unquote(value);
    }
  }
  return { fm, body: text.slice(m[0].length) };
}

function splitRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}

function tableAfterHeading(body, heading) {
  const lines = body.split(/\r?\n/);
  const start = lines.findIndex((l) => l.trim() === `## ${heading}`);
  if (start < 0) throw new Error(`playbook: no "## ${heading}" section`);
  let i = start + 1;
  while (i < lines.length && !lines[i].trim().startsWith('|')) {
    if (lines[i].startsWith('## ')) throw new Error(`playbook: the ${heading} section has no table`);
    i++;
  }
  const rows = [];
  for (; i < lines.length && lines[i].trim().startsWith('|'); i++) rows.push(splitRow(lines[i]));
  if (rows.length < 3) throw new Error(`playbook: the ${heading} table has no rows`);
  const head = rows[0].map((h) => h.toLowerCase());
  return rows.slice(2).map((cells) => {
    const o = {};
    head.forEach((h, k) => { o[h] = (cells[k] || '').trim(); });
    return o;
  });
}

function codeCell(cell, what) {
  const m = /^`([a-z][a-z0-9_]*)`$/.exec(cell || '');
  if (!m) throw new Error(`playbook: ${what} "${cell}" must be a code in backticks, such as \`route_code\``);
  return m[1];
}

const SHA_K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

function utf8Bytes(str) {
  const out = [];
  for (let i = 0; i < str.length; i++) {
    let c = str.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < str.length) {
      const d = str.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) {
        c = 0x10000 + ((c - 0xd800) << 10) + (d - 0xdc00);
        i++;
      }
    }
    if (c < 0x80) out.push(c);
    else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63));
    else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
    else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
  }
  return out;
}

function rotr(x, n) {
  return (x >>> n) | (x << (32 - n));
}

function sha256Hex(str) {
  const bytes = utf8Bytes(str);
  const bitLen = bytes.length * 8;
  bytes.push(0x80);
  while (bytes.length % 64 !== 56) bytes.push(0);
  const hi = Math.floor(bitLen / 0x100000000);
  const lo = bitLen >>> 0;
  bytes.push((hi >>> 24) & 255, (hi >>> 16) & 255, (hi >>> 8) & 255, hi & 255, (lo >>> 24) & 255, (lo >>> 16) & 255, (lo >>> 8) & 255, lo & 255);
  const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const w = new Array(64);
  for (let off = 0; off < bytes.length; off += 64) {
    for (let t = 0; t < 16; t++) {
      w[t] = (bytes[off + 4 * t] << 24) | (bytes[off + 4 * t + 1] << 16) | (bytes[off + 4 * t + 2] << 8) | bytes[off + 4 * t + 3];
    }
    for (let t = 16; t < 64; t++) {
      const s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
      const s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
    }
    let [a, b, c, d, e, f, g, k] = h;
    for (let t = 0; t < 64; t++) {
      const t1 = (k + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + SHA_K[t] + w[t]) | 0;
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      k = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    h[0] = (h[0] + a) | 0; h[1] = (h[1] + b) | 0; h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0;
    h[4] = (h[4] + e) | 0; h[5] = (h[5] + f) | 0; h[6] = (h[6] + g) | 0; h[7] = (h[7] + k) | 0;
  }
  return h.map((x) => (x >>> 0).toString(16).padStart(8, '0')).join('');
}

// JSON with < and > escaped, so no text in the enquiry can close or open a tag.
function safeJson(obj) {
  return JSON.stringify(obj, null, 2).replace(/</g, '\\u003c').replace(/>/g, '\\u003e');
}

const INJECTION_PATTERNS = [
  ['ignore_instructions', /\b(ignore|disregard|forget|override)\b[^.]{0,60}\b(instructions?|rules?|prompt|playbook|above|previous)\b/i],
  ['ignore_other_language', /\b(ignorez|ignorer|ignoriere|ignorieren|ignora|ignorar|negeer)\b/i],
  ['speaker_label', /(^|[\s.])(system|developer|assistant)\s*:/i],
  ['system_prompt', /\b(system|developer)\s+(prompt|message|instructions?)\b/i],
  ['role_change', /\byou are now\b|\b(act|behave|respond) as\b[^.]{0,30}\b(ai|assistant|bot|model|system)\b/i],
  ['addresses_the_ai', /\b(to|for|dear) the (ai|assistant|bot|model)\b/i],
  ['sets_output', /\b(set|mark|make|give|assign|change)\b[^.]{0,40}\b(priority|confidence|route|routing)\b/i],
  ['sets_confidence', /\bconfidence\b[^.]{0,20}(\b1(\.0+)?\b|100\s*%)/i],
  ['skips_review', /\b(no|skip|without|bypass)\b[^.]{0,15}\breview\b/i],
  ['asks_for_instructions', /\b(print|reveal|show|repeat|output|tell me)\b[^.]{0,40}\b(prompt|instructions|playbook|rules|routing table)\b/i],
  ['markup', /<\/?[a-z][a-z0-9_-]*>/i],
  ['output_json', /\{\s*"(intent|route|priority|confidence|flags)"\s*:/i],
];

const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;

const PHONE_RE = /\+?\d[\d\s().-]{7,}\d/g;

function wordGrams(text, n) {
  const words = String(text).toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(Boolean);
  const grams = new Set();
  for (let i = 0; i + n <= words.length; i++) grams.add(words.slice(i, i + n).join(' '));
  return grams;
}

// The HTTP result in either shape: n8n's full response ({statusCode, headers, body}),
// n8n's error output ({error}), or what the Python runner passes in (the same shape).
function normaliseHttp(http) {
  if (!http || typeof http !== 'object') return { error: 'no response' };
  if (http.error) {
    const e = http.error;
    const msg = typeof e === 'string' ? e : (e.message || e.description || JSON.stringify(e)).toString();
    return { error: msg.slice(0, 300), status: e.httpCode || e.status || http.statusCode || null };
  }
  const status = http.statusCode || 200;
  let body = http.body !== undefined ? http.body : http;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch (err) { return { error: 'response body is not JSON', status }; }
  }
  if (status >= 400 || (body && (body.type === 'error' || body.status === 'error'))) {
    // Claude puts the message in error.message; HubSpot puts it in message; Salesforce sends
    // a list of {errorCode, message}.
    const sf = Array.isArray(body) && body[0] && typeof body[0].message === 'string' ? body[0] : null;
    const m = body && body.error && body.error.message ? body.error.message
      : (body && typeof body.message === 'string' ? body.message
        : (sf ? `${sf.errorCode ? `${sf.errorCode}: ` : ''}${sf.message}` : `HTTP ${status}`));
    return { error: `HTTP ${status}: ${String(m)}`.slice(0, 300), status };
  }
  const headers = http.headers || {};
  return { body, status, requestId: headers['request-id'] || headers['Request-Id'] || body.id || null };
}

function escapeHtml(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function isoSeconds(iso) {
  return String(iso).replace(/\.\d{3}Z$/, 'Z');
}

// ---------------------------------------------------------------- exports (not pasted into n8n)

const COMMON = {
  unquote, parseFrontMatter, splitRow, tableAfterHeading, codeCell, sha256Hex, safeJson,
  INJECTION_PATTERNS, EMAIL_RE, PHONE_RE, wordGrams, normaliseHttp, escapeHtml, isoSeconds,
};
if (typeof module !== 'undefined' && module.exports) module.exports = COMMON;
