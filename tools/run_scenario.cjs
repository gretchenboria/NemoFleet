// Run a NemoFleet scenario against real Nebius endpoints.
//   node tools/run_scenario.cjs scenarios/hall-b-coolant-leak.json --dry-run   (no network: validates scenario, gate and schema)
//   node tools/run_scenario.cjs scenarios/hall-b-coolant-leak.json      (real calls: Cosmos, Nano, Ultra)
// Writes runs/<scenario>-<timestamp>/calls.jsonl (every model call, for Night Shift replay) and summary.json.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { ROOT, env, models, chat, parseJSON } = require('./tf.cjs');

const ACTIONS = { goto: ['robot', 'target'], halt: ['robot'], quarantine_zone: ['cells', 'ttl_s'], reassign_task: ['task', 'robot'], alert_human: ['severity', 'message'], proceed: ['robot'], reroute: ['robot', 'via'] };
function validate(d) {
  const errs = [];
  if (!d || typeof d !== 'object') return ['not a JSON object'];
  if (!Array.isArray(d.actions) || !d.actions.length) errs.push('actions must be a non-empty array');
  if (typeof d.confidence !== 'number' || d.confidence < 0 || d.confidence > 1) errs.push('confidence must be a number in [0, 1]');
  (d.actions || []).forEach((a, i) => {
    const need = ACTIONS[a && a.type];
    if (!need) errs.push(`actions[${i}].type "${a && a.type}" is not one of ${Object.keys(ACTIONS).join(', ')}`);
    else need.forEach(k => { if (a[k] === undefined) errs.push(`actions[${i}] (${a.type}) is missing "${k}"`); });
  });
  return errs;
}

const SYSTEM = 'You are the decision module of NemoFleet, a robot fleet. Decide what the robot or fleet should do next. ' +
  'Never output coordinates or paths: a deterministic planner owns motion. Reply with only one JSON object: ' +
  '{"actions": [ {"type": "proceed", "robot": "R07"} | {"type": "reroute", "robot": "R14", "via": "aisle 3"} | {"type": "halt", "robot": "R03"} | ' +
  '{"type": "quarantine_zone", "cells": ["41,7"], "ttl_s": 600} | {"type": "goto", "robot": "R05", "target": "dock 2"} | ' +
  '{"type": "reassign_task", "task": "T-4471", "robot": "R05"} | {"type": "alert_human", "severity": "high", "message": "..."} ], ' +
  '"confidence": 0.0-1.0, "rationale": "one sentence"}';

(async () => {
  const file = process.argv[2], dry = process.argv.includes('--dry-run');
  if (!file) { console.error('usage: node tools/run_scenario.cjs scenarios/<id>.json [--dry-run]'); process.exit(2); }
  const sc = JSON.parse(fs.readFileSync(path.resolve(file), 'utf8'));
  const m = models(), key = env('NEBIUS_API_KEY');
  if (!dry) {
    const missing = ['perception', 'reflex', 'deliberator'].filter(r => !m[r]);
    if (!key) { console.error('NEBIUS_API_KEY missing (.env). Run with --dry-run to test offline.'); process.exit(2); }
    if (missing.length) { console.error(`Model ids missing in config/models.yaml: ${missing.join(', ')}. Run: node tools/preflight.cjs --write`); process.exit(2); }
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const runDir = path.join(ROOT, 'runs', `${sc.id}-${stamp}${dry ? '-dry' : ''}`);
  fs.mkdirSync(runDir, { recursive: true });
  const log = rec => fs.appendFileSync(path.join(runDir, 'calls.jsonl'), JSON.stringify({ ts: new Date().toISOString(), ...rec }) + '\n');

  // 1. perception: real Cosmos calls through the existing tool (writes site/assets/perception/*.json)
  const frames = [...new Set(sc.events.filter(e => e.frame).map(e => e.frame))];
  if (!dry) { try { execFileSync('node', [path.join(__dirname, 'cosmos_perceive.cjs'), '--scene', sc.scene, ...frames], { stdio: 'inherit' }); } catch { console.error('Some Cosmos calls failed; continuing with the frames that succeeded.'); } }
  const perception = {};
  for (const f of frames) {
    const p = path.join(ROOT, 'site', 'assets', 'perception', sc.scene, f + '.json');
    if (fs.existsSync(p)) { perception[f] = JSON.parse(fs.readFileSync(p, 'utf8')); if (!dry) log({ tier: 'perception', model: perception[f].model, robot: perception[f].robot, frame: f, latency_ms: perception[f].latency_ms, usage: perception[f].usage, output: perception[f].raw }); }
  }

  // 2. events through the gate
  const precedents = {}, results = [];
  for (const ev of sc.events) {
    if (ev.kind === 'peer_handshake') {
      precedents[ev.robot] = { from: ev.from, hops: ((precedents[ev.from] || {}).hops || 0) + 1 };
      results.push({ t: ev.t, robot: ev.robot, tier: 'peer', model_calls: 0, note: ev.text });
      console.log(`t=${ev.t}s ${ev.robot} · peer handshake from ${ev.from} · no model call`);
      continue;
    }
    const seen = ev.frame && perception[ev.frame] ? perception[ev.frame].result : null;
    const context = `Site: ${sc.site}. Robot ${ev.robot} at ${ev.where}. ${ev.text}` + (seen ? `\nPerception (Cosmos): ${JSON.stringify(seen)}` : '') +
      (precedents[ev.robot] ? `\nPeer precedent: hop ${precedents[ev.robot].hops} from ${precedents[ev.robot].from}.` : '');
    const safety = ev.kind === 'safety' || (seen && (seen.person_present || seen.recommended_action === 'escalate'));
    let tier = safety ? 'ultra' : 'nano', decision = null, errors = [], calls = 0;

    if (dry) {
      console.log(`t=${ev.t}s ${ev.robot} · ${ev.kind} · would call ${tier === 'ultra' ? 'Ultra (safety gate)' : 'Nano, escalate to Ultra if confidence < ' + sc.tau}`);
      results.push({ t: ev.t, robot: ev.robot, tier, dry_run: true });
      continue;
    }
    const ask = async (t) => {
      const model = t === 'ultra' ? m.deliberator : m.reflex;
      let msgs = [{ role: 'system', content: SYSTEM }, { role: 'user', content: context }];
      for (let attempt = 1; attempt <= 2; attempt++) {
        const r = await chat(key, m.base, model, msgs); calls++;
        const d = parseJSON(r.content), errs = validate(d);
        log({ tier: t, model, robot: ev.robot, event: ev.kind, attempt, latency_ms: r.latency_ms, usage: r.usage, input: context, output: r.content, valid: !errs.length, errors: errs });
        if (!errs.length) return { d, latency_ms: r.latency_ms, model };
        errors = errs;
        msgs = [...msgs, { role: 'assistant', content: r.content }, { role: 'user', content: `Invalid: ${errs.join('; ')}. Reply again with only the corrected JSON object.` }];
      }
      return null;
    };
    let out = await ask(tier);
    if (tier === 'nano' && (!out || out.d.confidence < sc.tau)) { tier = 'ultra'; out = await ask('ultra'); }
    decision = out && out.d;
    results.push({ t: ev.t, robot: ev.robot, tier, model: out && out.model, model_calls: calls, latency_ms: out && out.latency_ms, decision, executed: !!decision, errors: decision ? [] : errors });
    console.log(`t=${ev.t}s ${ev.robot} · ${tier.toUpperCase()} · ${decision ? decision.actions.map(a => a.type).join(', ') + ` · conf ${decision.confidence}` : 'no valid action after retry → safe stop'}`);
  }

  const summary = { scenario: sc.id, dry_run: dry, run_dir: path.relative(ROOT, runDir), models: m, tau: sc.tau, results,
    totals: { events: results.length, ultra: results.filter(r => r.tier === 'ultra').length, nano: results.filter(r => r.tier === 'nano').length, peer: results.filter(r => r.tier === 'peer').length,
      model_calls: results.reduce((a, r) => a + (r.model_calls || 0), 0) } };
  fs.writeFileSync(path.join(runDir, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(`\n${dry ? 'Dry run' : 'Run'} complete → ${summary.run_dir}/summary.json  ·  ${JSON.stringify(summary.totals)}`);
})().catch(e => { console.error(e.message || e); process.exit(1); });
