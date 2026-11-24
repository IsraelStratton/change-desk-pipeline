// Run one Code node of a built workflow (n8n/*.json) outside n8n, with the n8n helpers it uses
// ($, $input, $json, $execution) stubbed. Shaped from the GTM pipeline's harness (tests/n8n_harness.js):
// the JavaScript run here is exactly the text in the workflow file, which is what n8n runs.
//
// stdin:  {workflow, node, items: [{json}], outputs: {node name: [{json}]}, execution_id}
// stdout: {ok: true, items: [{json}]} or {ok: false, error}
'use strict';
const fs = require('fs');

const input = JSON.parse(fs.readFileSync(0, 'utf8'));

async function main() {
  const wf = JSON.parse(fs.readFileSync(input.workflow, 'utf8'));
  const node = wf.nodes.find((n) => n.name === input.node);
  if (!node || node.type !== 'n8n-nodes-base.code') throw new Error(`${input.node} is not a Code node`);
  const items = input.items || [];
  const outputs = input.outputs || {};
  const each = node.parameters.mode === 'runOnceForEachItem';
  const $ = (ref) => {
    const got = outputs[ref];
    if (!got) throw new Error(`${input.node}: $('${ref}') has not run`);
    return { all: () => got, first: () => got[0], get item() { return got[0]; } };
  };
  const $execution = { id: input.execution_id || '1' };
  const fn = new Function('$', '$input', '$json', '$execution', `return (async () => {\n${node.parameters.jsCode}\n})();`);
  const $input = { all: () => items, first: () => items[0] };
  if (each) {
    const out = [];
    for (const it of items) {
      const r = await fn($, Object.assign({ item: it }, $input), it.json, $execution);
      out.push(Array.isArray(r) ? r[0] : r);
    }
    return out;
  }
  return fn($, $input, undefined, $execution);
}

main()
  .then((items) => process.stdout.write(JSON.stringify({ ok: true, items })))
  .catch((err) => process.stdout.write(JSON.stringify({ ok: false, error: err.message })));
