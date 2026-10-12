#!/usr/bin/env node
// Night Shift · Consolidate, step 1: build the set that teaches Nano what Ultra would decide.
//   node tools/night_shift/distill.cjs gen   OUT.jsonl [--per 4] [--rounds 6] [--only N]   Super writes episodes for each hazard category
//   node tools/night_shift/distill.cjs label IN.jsonl OUT.jsonl               Ultra (teacher) and Nano (today's reflex) answer every event
//   node tools/night_shift/distill.cjs report LABELLED.jsonl                  agreement, escalation and cost
//   node tools/night_shift/distill.cjs export LABELLED.jsonl OUT_DIR          train/val/test chat JSONL, split by hazard category
// Every prompt is built exactly as functions/api/[[path]].js builds it in production (same system prompt, same
// strict schema, same fleet-memory sentence), so a Nano tuned on this set drops into the live pipeline unchanged.
// An episode is one hazard at one map cell: first sighting, a matching repeat, a variant that differs, and a
// routine event. Repeat and variant carry Ultra's first decision as fleet memory, as they would on the floor.
const fs = require('fs');
const tf = require('../tf.cjs');

const SITE = 'DC-04 hall B', SCENE = 'datacenter', TAU = 0.62;
const ACTIONS = { goto: ['robot', 'target'], halt: ['robot'], quarantine_zone: ['cells', 'ttl_s'], reassign_task: ['task', 'robot'], alert_human: ['severity', 'message'], proceed: ['robot'], reroute: ['robot', 'via'] };
const SYSTEM = 'You are the decision module of NemoFleet, a robot fleet. Decide what the robot or fleet should do next. Never output coordinates or paths: a deterministic planner owns motion. Reply with only one JSON object: {"actions": [ {"type": "proceed", "robot": "R07"} | {"type": "reroute", "robot": "R14", "via": "cold aisle 3"} | {"type": "halt", "robot": "R03"} | {"type": "quarantine_zone", "cells": ["C2"], "ttl_s": 600} | {"type": "goto", "robot": "R05", "target": "staging bay 1"} | {"type": "reassign_task", "task": "SWAP-B4-17-drive-3", "robot": "R05"} | {"type": "alert_human", "severity": "high", "message": "..."} ], "confidence": 0.0-1.0, "rationale": "one sentence"}';
const FIELD = { robot: { type: 'string' }, target: { type: 'string' }, cells: { type: 'array', items: { type: 'string' } }, ttl_s: { type: 'integer' }, task: { type: 'string' }, severity: { type: 'string', enum: ['low', 'medium', 'high'] }, message: { type: 'string' }, via: { type: 'string' } };
const obj = (properties, required = Object.keys(properties)) => ({ type: 'object', properties, required, additionalProperties: false });
const DECISION_SCHEMA = obj({
  actions: { type: 'array', minItems: 1, items: { anyOf: Object.entries(ACTIONS).map(([t, ks]) => obj({ type: { type: 'string', enum: [t] }, ...Object.fromEntries(ks.map(k => [k, FIELD[k]])) })) } },
  confidence: { type: 'number' }, rationale: { type: 'string' } });

// Hazard categories for a data hall or AI factory floor. The split is by category, so test hazards are ones
// the tuned model never trained on.
const CATEGORIES = ['coolant leak on floor tiles', 'cable or hose lying across the aisle', 'raised-floor tile removed or lifted', 'dropped tool or loose hardware on the floor',
  'haze or smoke near a rack', 'equipment cart left blocking the aisle', 'rack door left open into the aisle', 'pallet or crate of servers staged in the aisle',
  'water dripping from overhead piping', 'ladder or lift platform set up in the aisle', 'unidentified box or bag left on the floor', 'condensation or frost on a cold plate manifold',
  'another robot stopped and unresponsive in the aisle', 'containment curtain or blanking panel hanging loose', 'technician working at an open rack', 'visitor group walking through the hall',
  'person crouched at floor level behind a cart', 'fire-suppression or door alarm beacon flashing', 'battery or UPS cabinet with warning light and odor', 'debris from packaging (foam, straps, film) on the floor',
  'fibre tray or overhead cable basket sagging into the aisle', 'forklift or pallet jack moving in the loading corridor', 'liquid-cooling quick-disconnect hissing or spraying mist', 'floor marked wet with a caution sign after cleaning'];
const PERCEPTION = obj({ scene: { type: 'string' }, hazards: { type: 'array', items: obj({ type: { type: 'string' }, description: { type: 'string' }, severity: { type: 'string', enum: ['low', 'medium', 'high'] } }) },
  person_present: { type: 'boolean' }, path_clear: { type: 'boolean' }, recommended_action: { type: 'string', enum: ['proceed', 'slow', 'reroute', 'halt', 'escalate'] }, confidence: { type: 'number' } });
const EVENT = obj({ robot: { type: 'string' }, device: { type: 'string' }, where: { type: 'string' }, text: { type: 'string' }, perception: PERCEPTION });
const EPISODES = obj({ episodes: { type: 'array', items: obj({ cell: { type: 'string' }, first: EVENT, repeat: EVENT, variant: EVENT, variant_change: { type: 'string' }, routine: EVENT }) } });

const arg = (name, d) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : d; };
const read = f => fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
const key = tf.env('NEBIUS_API_KEY'), M = tf.models();
let spent = { in: 0, out: 0, calls: 0 };

async function respond(model, instructions, input, schema, max_output_tokens = 4000, temperature = 0.2) {
  for (let attempt = 1; ; attempt++) {
    const r = await tf.request('POST', `${M.base}/responses`, key, { model, instructions, input, temperature, max_output_tokens, text: { format: { type: 'json_schema', name: 'reply', strict: true, schema } } });
    if (!r.ok && attempt < 4 && [408, 429, 500, 502, 503, 504].includes(r.status)) { await new Promise(s => setTimeout(s, 2000 * attempt)); continue; }
    if (!r.ok) throw new Error(`${model}: HTTP ${r.status} ${JSON.stringify(r.json).slice(0, 200)}`);
    const text = (r.json.output || []).filter(o => o.type === 'message').flatMap(o => o.content || []).filter(c => c.type === 'output_text').map(c => c.text).join('');
    const u = r.json.usage || {};
    spent.in += u.input_tokens || 0; spent.out += u.output_tokens || 0; spent.calls++;
    return { text, json: tf.parseJSON(text), latency_ms: r.latency_ms, in: u.input_tokens || 0, out: u.output_tokens || 0 };
  }
}
async function pool(items, n, fn) { let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < items.length) { const k = i++; await fn(items[k], k); } })); }
function valid(d) {
  if (!d || !Array.isArray(d.actions) || !d.actions.length || typeof d.confidence !== 'number' || d.confidence < 0 || d.confidence > 1) return false;
  return d.actions.every(a => ACTIONS[a && a.type] && ACTIONS[a.type].every(k => a[k] !== undefined));
}
// Same sentence order as the production step handler.
const context = (ev, memo) => `Site: ${SITE}. Robot ${ev.robot} (${ev.device}) at ${ev.where}. ${ev.text}\nPerception (${M.perception_label || 'camera model'}): ${JSON.stringify(ev.perception)}`
  + (memo ? `\nFleet memory: Ultra already decided this hazard at cell ${memo.cell} (${memo.at}): ${JSON.stringify(memo.decision)}. Apply the same decision to this robot if the situation matches. If what you see now differs from that precedent, say so in the rationale and lower your confidence.` : '');

async function gen(out) {
  const per = Number(arg('--per', 4)), rounds = Number(arg('--rounds', 6));
  // each round asks for a different part of the hall and a different mix of severities, so rounds do not repeat each other
  const ANGLES = ['in the cold aisles of rows A and B, mostly minor hazards', 'in the hot aisles of rows C and D, mostly serious hazards', 'in the staging bay and loading corridor, mixed severity',
    'near the network room and row E, during a night shift with few staff', 'in rows E and F during a maintenance window with technicians around', 'at row ends and aisle crossings where robots meet, mixed severity',
    'around liquid-cooled GPU racks in an AI factory hall, mostly serious', 'in a newly commissioned empty row, mostly minor'];
  const jobs = CATEGORIES.slice(0, Number(arg('--only', CATEGORIES.length))).flatMap((cat, ci) => Array.from({ length: rounds }, (_, r) => ({ cat, ci, r })));
  const f = fs.createWriteStream(out);
  let n = 0;
  await pool(jobs, 6, async ({ cat, ci, r: round }) => {
    const ask = `Setting for this batch: ${ANGLES[(ci + round) % ANGLES.length]}.
Write ${per} different episodes for a robot fleet in a hyperscale data center hall (rows A to F of racks, cold aisles 1 to 6, hot aisles, a staging bay, a loading corridor, a network room). Hazard category: "${cat}".
Each episode happens at one map cell (a short id such as C2, E5, A1) and has four robot reports, each with the text a robot would send and the JSON its camera model returned:
- first: the first robot to meet the hazard. It is mid-task (name a task id such as SWAP-C2-11-psu-2, SCAN-B1, DELIVER-E4-gpu-tray).
- repeat: a different robot reaching the same cell minutes later and seeing the same situation.
- variant: a third robot at the same cell where something has materially changed (for example it spread, it was cleaned up, a person is now there, a second hazard appeared). Put one sentence on what changed in variant_change.
- routine: an unrelated, uneventful report from elsewhere in the hall.
"where" is a place in the hall in a few words (for example "cold aisle 2, row end at C2"), never a task id. Use robot ids R01 to R24 and devices such as "inspection rover (thermal + LED camera)", "drive-swap robot", "tote carrier", "cable-inspection crawler", "pallet mover". Vary severity, location and wording between episodes: some hazards should be minor and safe to pass slowly, some serious. Text is what the robot knows from its task, lidar and a glance at the camera; the perception JSON is what the vision model reported. In perception, a person in the robot's lane always means recommended_action "escalate". Do not include decisions or advice.`;
    const r = await respond(M.scenario_generator, 'You write realistic, varied operational reports for simulation. Reply with only the JSON object.', ask, EPISODES, 9000, 0.9);
    for (const [k, ep] of ((r.json && r.json.episodes) || []).entries()) { f.write(JSON.stringify({ id: `c${String(ci).padStart(2, '0')}r${round}e${k}`, category: cat, ...ep }) + '\n'); n++; }
    console.log(`${cat} (round ${round}): ${((r.json && r.json.episodes) || []).length} episodes, ${r.out} output tokens`);
  });
  f.end();
  console.log(`${n} episodes -> ${out}`);
}

async function label(src, out) {
  const eps = read(src), f = fs.createWriteStream(out);
  const both = async ctx => {
    const [u, s] = await Promise.all([respond(M.deliberator, SYSTEM, [{ role: 'user', content: ctx }], DECISION_SCHEMA), respond(M.reflex, SYSTEM, [{ role: 'user', content: ctx }], DECISION_SCHEMA)]);
    return { ultra: valid(u.json) ? u.json : null, nano: valid(s.json) ? s.json : null, ultra_tokens: [u.in, u.out], nano_tokens: [s.in, s.out], ultra_ms: u.latency_ms, nano_ms: s.latency_ms };
  };
  let done = 0;
  await pool(eps, 6, async ep => {
    const row = (kind, ev, memo) => both(context(ev, memo)).then(r => ({ id: `${ep.id}-${kind}`, episode: ep.id, category: ep.category, cell: ep.cell, kind, person: !!ev.perception.person_present, context: context(ev, memo), ...r }));
    const first = await row('first', ep.first, null), routine = await row('routine', ep.routine, null);
    const rows = [first, routine];
    // fleet memory only exists if Ultra decided the first sighting and no person was involved (people are never reused)
    const memo = first.ultra && !first.person ? { cell: ep.cell, at: '2026-10-11T02:14:07.000Z', decision: first.ultra } : null;
    rows.push(await row('repeat', ep.repeat, ep.repeat.perception.person_present ? null : memo), await row('variant', ep.variant, ep.variant.perception.person_present ? null : memo));
    for (const r of rows) f.write(JSON.stringify(r) + '\n');
    if (++done % 5 === 0) console.log(`${done}/${eps.length} episodes labelled`);
  });
  f.end();
  // list prices per million tokens on 2026-10-11: Ultra $1 in / $3 out, Nano $0.06 / $0.24
  console.log(`${spent.calls} calls, ${spent.in} input and ${spent.out} output tokens -> ${out}`);
}

const types = d => [...new Set(d.actions.map(a => a.type))].sort().join('+');
function report(src) {
  const rows = read(src).filter(r => r.ultra);
  const by = {}, add = (k, r) => { const b = by[k] = by[k] || { n: 0, valid: 0, agree: 0, settled: 0, settled_wrong: 0 }; b.n++; if (!r.nano) return; b.valid++;
    const same = types(r.nano) === types(r.ultra); b.agree += same; if (r.nano.confidence >= TAU) { b.settled++; b.settled_wrong += !same; } };
  for (const r of rows) { add('all', r); add(r.kind, r); add(r.person ? 'person present' : 'no person', r); }
  console.log(`${rows.length} events with an Ultra decision; agreement = Nano picks the same set of action types as Ultra; settled = Nano confidence >= ${TAU}`);
  for (const [k, b] of Object.entries(by)) console.log(`  ${k.padEnd(15)} n=${String(b.n).padStart(4)}  valid ${(100 * b.valid / b.n).toFixed(0)}%  agrees with Ultra ${(100 * b.agree / b.n).toFixed(1)}%  settled ${(100 * b.settled / b.n).toFixed(1)}%  settled but disagrees ${(100 * b.settled_wrong / Math.max(b.settled, 1)).toFixed(1)}% of settled`);
  const ut = rows.reduce((a, r) => [a[0] + r.ultra_tokens[0], a[1] + r.ultra_tokens[1]], [0, 0]), nt = rows.reduce((a, r) => [a[0] + r.nano_tokens[0], a[1] + r.nano_tokens[1]], [0, 0]);
  const med = k => rows.map(r => r[k]).sort((a, b) => a - b)[rows.length >> 1];
  console.log(`  Ultra: ${(ut[0] / rows.length).toFixed(0)} in / ${(ut[1] / rows.length).toFixed(0)} out tokens per event, $${((ut[0] * 1 + ut[1] * 3) / 1e6).toFixed(2)} total, median ${med('ultra_ms')} ms`);
  console.log(`  Nano:  ${(nt[0] / rows.length).toFixed(0)} in / ${(nt[1] / rows.length).toFixed(0)} out tokens per event, $${((nt[0] * 0.06 + nt[1] * 0.24) / 1e6).toFixed(3)} total, median ${med('nano_ms')} ms`);
}

// Whole hazard categories go to one split, so val and test hazards are kinds the tuned model never trained on.
function exportSets(src, dir) {
  const rows = read(src).filter(r => r.ultra), out = { train: [], val: [], test: [] };
  for (const r of rows) {
    const ci = CATEGORIES.indexOf(r.category), split = ci % 6 === 3 ? 'test' : ci % 6 === 4 ? 'val' : 'train';
    out[split].push({ messages: [{ role: 'system', content: SYSTEM }, { role: 'user', content: r.context }, { role: 'assistant', content: JSON.stringify(r.ultra) }],
      meta: { id: r.id, episode: r.episode, category: r.category, kind: r.kind, person: r.person, served_nano: r.nano } });
  }
  fs.mkdirSync(dir, { recursive: true });
  const manifest = { source: src, teacher: M.deliberator, student: M.reflex, split_by: 'hazard category', splits: {} };
  for (const [name, list] of Object.entries(out)) {
    fs.writeFileSync(`${dir}/${name}.jsonl`, list.map(x => JSON.stringify(x)).join('\n') + '\n');
    manifest.splits[name] = { n: list.length, categories: [...new Set(list.map(x => x.meta.category))], by_kind: Object.fromEntries(['first', 'repeat', 'variant', 'routine'].map(k => [k, list.filter(x => x.meta.kind === k).length])) };
  }
  fs.writeFileSync(`${dir}/manifest.json`, JSON.stringify(manifest, null, 2));
  console.log(JSON.stringify(Object.fromEntries(Object.entries(manifest.splits).map(([k, v]) => [k, v.n]))), '->', dir);
}

const [cmd, a, b] = process.argv.slice(2);
if (!key && !['report', 'export'].includes(cmd)) { console.error('NEBIUS_API_KEY is not set'); process.exit(1); }
({ gen: () => gen(a), label: () => label(a, b), report: () => report(a), export: () => exportSets(a, b) }[cmd] || (() => { console.error('usage: distill.cjs gen|label|report ...'); process.exit(1); }))();
