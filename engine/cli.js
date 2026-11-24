// Bridge from Python to the engines: JSON in on stdin, JSON out on stdout. Copied from the GTM
// pipeline (engine/cli.js) with this build's engines.
//   {"module": "triage" | "scoring" | "drafter" | "common", "calls": [{"fn": "parseTriagePlaybook", "args": ["..."]}, ...]}
// Each call may use the result of an earlier one: an argument {"$ref": 0} is replaced by the
// result of call 0. Only functions the engine exports can be called.
'use strict';
const ENGINES = {
  common: () => require('./common.js'),
  triage: () => require('./triage.js'),
  scoring: () => require('./scoring.js'),
  drafter: () => require('./drafter.js'),
};

function resolve(arg, results) {
  if (arg && typeof arg === 'object' && !Array.isArray(arg) && Object.keys(arg).length === 1 && '$ref' in arg) {
    if (!(arg.$ref in results)) throw new Error(`$ref ${arg.$ref} points at no earlier call`);
    return results[arg.$ref];
  }
  return arg;
}

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const { calls, module: name } = JSON.parse(input);
    const load = ENGINES[name || 'triage'];
    if (!load) throw new Error(`there is no engine called ${name}`);
    const engine = load();
    const results = [];
    for (const call of calls) {
      const fn = engine[call.fn];
      if (typeof fn !== 'function') throw new Error(`the engine has no function ${call.fn}`);
      results.push(fn(...(call.args || []).map((a) => resolve(a, results))));
    }
    process.stdout.write(JSON.stringify({ ok: true, results }));
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: err.message }));
  }
});
