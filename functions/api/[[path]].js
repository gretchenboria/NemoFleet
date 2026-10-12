// NemoFleet console API (Cloudflare Pages Functions). Bindings: MEMORY (D1), TAGS (KV), RUNS (R2), ASSETS.
// Secret: NEBIUS_API_KEY (wrangler pages secret put NEBIUS_API_KEY --project-name nemofleet).
// Everything here is real: D1/KV/R2 writes, and Token Factory calls when the key is set.

const J = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
const now = () => new Date().toISOString();
const uid = p => `${p}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
const SCENARIOS = { warehouse: 'aisle4-spill', datacenter: 'hall-b-coolant-leak', sanfrancisco: 'soma-robotaxi' };  // sanfrancisco is experimental
const ACTIONS = { goto: ['robot', 'target'], halt: ['robot'], quarantine_zone: ['cells', 'ttl_s'], reassign_task: ['task', 'robot'], alert_human: ['severity', 'message'], proceed: ['robot'], reroute: ['robot', 'via'] };
const SYSTEM_BASE = 'You are the decision module of NemoFleet, a robot fleet. Decide what the robot or fleet should do next. Never output coordinates or paths: a deterministic planner owns motion. Reply with only one JSON object: {"actions": [ __EXAMPLES__ ], "confidence": 0.0-1.0, "rationale": "one sentence"}';
const EXAMPLES = {
  warehouse: '{"type": "proceed", "robot": "R07"} | {"type": "reroute", "robot": "R14", "via": "aisle 3"} | {"type": "halt", "robot": "R03"} | {"type": "quarantine_zone", "cells": ["A4"], "ttl_s": 600} | {"type": "goto", "robot": "R05", "target": "dock 2"} | {"type": "reassign_task", "task": "PICK-4471", "robot": "R05"} | {"type": "alert_human", "severity": "high", "message": "..."}',
  datacenter: '{"type": "proceed", "robot": "R07"} | {"type": "reroute", "robot": "R14", "via": "cold aisle 3"} | {"type": "halt", "robot": "R03"} | {"type": "quarantine_zone", "cells": ["C2"], "ttl_s": 600} | {"type": "goto", "robot": "R05", "target": "staging bay 1"} | {"type": "reassign_task", "task": "SWAP-B4-17-drive-3", "robot": "R05"} | {"type": "alert_human", "severity": "high", "message": "..."}',
  sanfrancisco: '{"type": "proceed", "robot": "AV07"} | {"type": "reroute", "robot": "AV14", "via": "Beale St"} | {"type": "halt", "robot": "AV03"} | {"type": "quarantine_zone", "cells": ["fremont-mission-howard"], "ttl_s": 900} | {"type": "goto", "robot": "AV05", "target": "pickup at 1st and Howard"} | {"type": "reassign_task", "task": "RIDE-2231", "robot": "AV05"} | {"type": "alert_human", "severity": "high", "message": "..."}',
};
const PERCEPTION_CONTEXT = { warehouse: 'an autonomous robot in a fulfillment warehouse', datacenter: 'an autonomous robot in a hyperscale data center hall',
  sanfrancisco: 'an autonomous robotaxi driving in downtown San Francisco (a person in or stepping into the vehicle\'s path always means "escalate")' };
const systemFor = scene => SYSTEM_BASE.replace('__EXAMPLES__', EXAMPLES[scene] || EXAMPLES.warehouse);
// Strict JSON schema for /v1/responses (text.format). It enforces shape only; validate() still runs as a second check.
const FIELD = { robot: { type: 'string' }, target: { type: 'string' }, cells: { type: 'array', items: { type: 'string' } }, ttl_s: { type: 'integer' }, task: { type: 'string' }, severity: { type: 'string', enum: ['low', 'medium', 'high'] }, message: { type: 'string' }, via: { type: 'string' } };
const obj = (properties, required = Object.keys(properties)) => ({ type: 'object', properties, required, additionalProperties: false });
const DECISION_SCHEMA = obj({
  actions: { type: 'array', minItems: 1, items: { anyOf: Object.entries(ACTIONS).map(([t, ks]) => obj({ type: { type: 'string', enum: [t] }, ...Object.fromEntries(ks.map(k => [k, FIELD[k]])) })) } },
  confidence: { type: 'number' }, rationale: { type: 'string' } });
const VERDICT_SCHEMA = obj({ agree: { type: 'boolean' }, better_action: { type: ['string', 'null'] }, reason: { type: 'string' } });

function validate(d) {
  const e = [];
  if (!d || typeof d !== 'object') return ['not a JSON object'];
  if (!Array.isArray(d.actions) || !d.actions.length) e.push('actions must be a non-empty array');
  if (typeof d.confidence !== 'number' || d.confidence < 0 || d.confidence > 1) e.push('confidence must be a number in [0, 1]');
  (d.actions || []).forEach((a, i) => { const need = ACTIONS[a && a.type]; if (!need) e.push(`actions[${i}].type is invalid`); else need.forEach(k => { if (a[k] === undefined) e.push(`actions[${i}] (${a.type}) missing "${k}"`); }); });
  return e;
}
function parseJSON(t) {
  t = String(t).replace(/<think>[\s\S]*?<\/think>/g, '').replace(/```(?:json)?/g, '');
  const a = t.indexOf('{'), b = t.lastIndexOf('}');
  if (a < 0 || b < a) return null;
  try { return JSON.parse(t.slice(a, b + 1)); } catch { return null; }
}
async function asset(env, req, path) { const r = await env.ASSETS.fetch(new URL(path, req.url)); if (!r.ok) throw new Error(`asset ${path}: ${r.status}`); return r; }
async function models(env, req) { return (await asset(env, req, '/config/models.json')).json(); }
async function scenario(env, req, scene) { return (await asset(env, req, `/scenarios/${SCENARIOS[scene]}.json`)).json(); }
function needKey(env) { if (!env.NEBIUS_API_KEY) throw Object.assign(new Error('Model calls are disabled: NEBIUS_API_KEY is not set on the Pages project. Run: npx wrangler pages secret put NEBIUS_API_KEY --project-name nemofleet'), { status: 503 }); }

async function chat(env, base, model, messages, max_tokens = 800, timeout_ms = 0, key = env.NEBIUS_API_KEY) {
  needKey(env);
  const t0 = Date.now();
  const r = await fetch(`${base}/chat/completions`, { method: 'POST', headers: { Authorization: `Bearer ${key}`, 'content-type': 'application/json' }, body: JSON.stringify({ model, messages, temperature: 0.2, max_tokens }), signal: timeout_ms ? AbortSignal.timeout(timeout_ms) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(`${model}: HTTP ${r.status} ${JSON.stringify(j).slice(0, 240)}`), { status: 502 });
  return { latency_ms: Date.now() - t0, usage: j.usage || {}, content: j.choices?.[0]?.message?.content ?? '' };
}
// Nemotron calls go through the Responses API with a strict schema. Tested on Token Factory 2026-10-08:
// response_format and max_completion_tokens are ignored there; max_output_tokens is enforced and includes reasoning.
async function respond(env, base, model, instructions, input, schema, max_output_tokens = 4000) {
  needKey(env);
  const t0 = Date.now();
  const r = await fetch(`${base}/responses`, { method: 'POST', headers: { Authorization: `Bearer ${env.NEBIUS_API_KEY}`, 'content-type': 'application/json' },
    body: JSON.stringify({ model, instructions, input, temperature: 0.2, max_output_tokens, text: { format: { type: 'json_schema', name: 'reply', strict: true, schema } } }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(`${model}: HTTP ${r.status} ${JSON.stringify(j).slice(0, 240)}`), { status: 502 });
  const content = (j.output || []).filter(o => o.type === 'message').flatMap(o => o.content || []).filter(c => c.type === 'output_text').map(c => c.text).join('');
  const u = j.usage || {};
  return { latency_ms: Date.now() - t0, status: j.status, content,
    usage: { prompt_tokens: u.input_tokens ?? null, completion_tokens: u.output_tokens ?? null, reasoning_tokens: u.output_tokens_details?.reasoning_tokens ?? null } };
}
async function logCall(env, rec) {
  const key = `calls/${rec.scene}/${rec.ts.slice(0, 10)}/${uid(rec.tier)}.json`;
  await env.RUNS.put(key, JSON.stringify(rec));
  const ins = await env.MEMORY.prepare('INSERT INTO calls (run_id, ts, tier, model, robot, event, latency_ms, prompt_tokens, completion_tokens, valid, r2_key, scene, decision_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)')
    .bind(rec.run_id || null, rec.ts, rec.tier, rec.model, rec.robot || null, rec.event || null, rec.latency_ms || null, rec.usage?.prompt_tokens ?? null, rec.usage?.completion_tokens ?? null, rec.valid == null ? null : rec.valid ? 1 : 0, key, rec.scene, rec.decision ? JSON.stringify(rec.decision) : null).run();
  return ins.meta?.last_row_id ?? null;
}
async function decide(env, m, scene, run_id, robot, event, tier, context) {
  const model = tier === 'ultra' ? m.deliberator : m.reflex;
  if (!model) throw Object.assign(new Error(`No ${tier === 'ultra' ? 'deliberator (Ultra)' : 'reflex (Nano)'} model id in config/models.yaml. Run node tools/preflight.cjs --write and redeploy.`), { status: 503 });
  let msgs = [{ role: 'user', content: context }], errs = [], call_id = null;
  for (let attempt = 1; attempt <= 2; attempt++) {
    const r = await respond(env, m.base, model, systemFor(scene), msgs, DECISION_SCHEMA);
    const d = parseJSON(r.content); errs = r.status === 'incomplete' ? ['response incomplete: hit max_output_tokens'] : validate(d);
    call_id = await logCall(env, { scene, run_id, ts: now(), tier, model, robot, event, latency_ms: r.latency_ms, usage: r.usage, input: context, output: r.content, valid: !errs.length, errors: errs, decision: errs.length ? null : d });
    if (!errs.length) return { decision: d, model, latency_ms: r.latency_ms, call_id };
    msgs = [...msgs, { role: 'assistant', content: r.content }, { role: 'user', content: `Invalid: ${errs.join('; ')}. Reply again with only the corrected JSON object.` }];
  }
  return { decision: null, model, errors: errs, call_id };
}
async function perceive(env, req, m, scene, run_id, robot, frame, ref = {}) {
  if (!m.perception) throw Object.assign(new Error('No perception model id: set one with node tools/use_perception.cjs and redeploy.'), { status: 503 });
  const img = await asset(env, req, `/assets/scenes/${scene}/frames/${frame}.jpg`);
  if (!/^image\//.test(img.headers.get('content-type') || '')) throw Object.assign(new Error(`camera frame ${scene}/${frame} is missing`), { status: 404 });
  const buf = new Uint8Array(await img.arrayBuffer());
  let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  const prompt = 'Analyze this robot camera frame for the planner. Return JSON with keys "scene" (one sentence), "hazards" (array of {"type","description","severity"}), "person_present" (boolean), "path_clear" (boolean), "recommended_action" ("proceed"|"slow"|"reroute"|"halt"|"escalate"), "confidence" (0-1). A person in the robot\'s lane always means "escalate".';
  // perception may live on Token Factory or on a self-hosted Nebius endpoint (Gemma 4 via vLLM) with its own token
  const pkey = m.perception_key_env && m.perception_key_env !== 'NEBIUS_API_KEY' ? env[m.perception_key_env] : env.NEBIUS_API_KEY;
  if (!pkey) throw Object.assign(new Error(`${m.perception_key_env} is not set on the Pages project (token for the ${m.perception_label} endpoint).`), { status: 503 });
  const r = await chat(env, m.perception_base || m.base, m.perception, [{ role: 'system', content: `You are the perception module of ${PERCEPTION_CONTEXT[scene] || PERCEPTION_CONTEXT.warehouse}. Report only what is visible. Answer with one JSON object.` },
    { role: 'user', content: [{ type: 'image_url', image_url: { url: `data:image/jpeg;base64,${btoa(bin)}` } }, { type: 'text', text: prompt }] }], 700, 15000, pkey);  // a slow frame must not stall the step: it continues as 'perception unavailable'
  const result = parseJSON(r.content), ts = now(), key = `perception/${scene}/${frame}/${ts}.json`;
  await env.RUNS.put(key, JSON.stringify({ scene, frame, robot, model: m.perception, ts, latency_ms: r.latency_ms, usage: r.usage, raw: r.content, result }));
  await env.MEMORY.prepare('INSERT INTO perception (id, scene, frame, robot, model, called_at, latency_ms, result_json, raw_r2_key) VALUES (?,?,?,?,?,?,?,?,?)').bind(`${scene}/${frame}/${ts}`, scene, frame, robot, m.perception, ts, r.latency_ms, JSON.stringify(result), key).run();
  ref.id = `${scene}/${frame}/${ts}`;
  await logCall(env, { scene, run_id, ts, tier: 'perception', model: m.perception, robot, event: frame, latency_ms: r.latency_ms, usage: r.usage, output: r.content, valid: !!result });
  return result;
}
// An alarm records what led to it (the event, the deciding call, the perception row, the stored decision), so GET incident can return one record.
async function alarm(env, scene, sev, title, meta, run_id, link = {}) {
  const id = uid('al');
  await env.MEMORY.prepare('INSERT INTO alarms (id, scene, sev, title, meta, run_id, event_index, event_json, safety, call_id, perception_id, precedent_id, precedent_link) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)')
    .bind(id, scene, sev, title, meta, run_id || null, link.event_index ?? null, link.event ? JSON.stringify(link.event) : null, link.safety ? 1 : 0, link.call_id ?? null, link.perception_id ?? null, link.precedent_id ?? null, link.precedent_link ?? null).run();
  return id;
}
async function action(env, scene, type, payload, source, run_id, link = {}) {
  await env.MEMORY.prepare('INSERT INTO actions (id, scene, type, payload_json, source, run_id, event_index, alarm_id) VALUES (?,?,?,?,?,?,?,?)').bind(uid('act'), scene, type, JSON.stringify(payload), source, run_id || null, link.event_index ?? null, link.alarm_id ?? null).run();
}
// A stored decision can be reused when it is not revoked, not superseded, and either pinned or not yet expired.
const LIVE_DECISION = 'revoked_at IS NULL AND superseded_by IS NULL AND (pinned = 1 OR expires_at IS NULL OR expires_at > ?)';
const lookupDecision = (env, scene, cell) => env.MEMORY.prepare(`SELECT * FROM precedents WHERE scene = ? AND hazard_key = ? AND safety = 0 AND source IN ('ultra', 'operator') AND ${LIVE_DECISION} ORDER BY created_at DESC LIMIT 1`).bind(scene, cell, now()).first();
const decisionStatus = (p, t) => p.revoked_at ? 'revoked' : p.superseded_by ? 'superseded' : p.pinned || !p.expires_at || p.expires_at > t ? 'live' : 'expired';
const parse = t => { try { return JSON.parse(t); } catch { return null; } };
const decisionRow = (p, t = now()) => ({ id: p.id, cell: p.hazard_key, situation: String(p.situation || '').replace(/\n(Perception|Fleet memory)[\s\S]*$/, '').replace(/\s+/g, ' ').slice(0, 220), decision: parse(p.decision_json), source: p.source, model: p.model, confidence: p.confidence,
  created_at: p.created_at, expires_at: p.expires_at, pinned: !!p.pinned, revoked: !!p.revoked_at, revoked_at: p.revoked_at || null, superseded_by: p.superseded_by || null, safety: !!p.safety, alarm_id: p.alarm_id || null, status: decisionStatus(p, t), reuse_count: p.reuse_count ?? null });

// Autonomy target: the share of self-settled decisions that may differ from Ultra. Only the levels measured for the tuned
// Nano (config/night_shift.json distill.gate.levels) can be chosen. It is the gate for the tuned adapter; the served Nano is gated by stated confidence and tau.
async function gateLevels(env, req) { try { return (await (await asset(env, req, '/config/night_shift.json')).json()).distill?.gate?.levels || []; } catch { return []; } }
// The tuned Nano adapter: configured in config/models.yaml (reflex_tuned), its token in the env var it names, promoted per scene by the operator.
// It is serving a scene only when all three hold.
async function adapterFor(env, req, scene, m) {
  m = m || await models(env, req).catch(() => ({})); const t = m.reflex_tuned; if (!t) return null;
  const configured = !!t.base_url, key = !!(t.api_key_env && env[t.api_key_env]), promoted = !!(await env.TAGS.get(`${scene}:promoted`));
  return { id: t.id || null, label: t.label || null, adapter: t.adapter || null, configured, key, key_env: t.api_key_env || null, promoted, serving: configured && key && promoted };
}
async function autonomyFor(env, req, scene, ad) {
  const t = Number(await env.TAGS.get(`${scene}:autonomy`)), level = t > 0 ? (await gateLevels(env, req)).find(l => l.target_error === t) : null;
  if (ad === undefined) ad = await adapterFor(env, req, scene);
  return { target_error: level ? t : null, level: level || null, in_force: ad?.serving && level ? 'probability_gate' : 'stated_confidence' };
}
// Whether a Nano-tier answer goes up to Ultra: by the tuned adapter's own probability when there is one and a target level is set, otherwise by stated confidence against tau.
function gateDecision(out, tau, level) {
  if (!out.decision) return { escalate: true, by: 'invalid' };
  if (level && typeof out.actions_probability === 'number') return { escalate: out.actions_probability < level.min_probability, by: 'probability' };
  return { escalate: out.decision.confidence < tau, by: 'stated_confidence' };
}
// One call to the tuned adapter's OpenAI-compatible endpoint. Any error or invalid decision is logged and returned as no decision; the caller falls back to the served Nano.
async function decideTuned(env, t, scene, run_id, robot, event, context) {
  const t0 = Date.now(); let content = '', errs = [], prob = null, usage = {}, d = null;
  try {
    const r = await fetch(`${t.base}/chat/completions`, { method: 'POST', headers: { Authorization: `Bearer ${t.key}`, 'content-type': 'application/json' },
      body: JSON.stringify({ model: t.model, messages: [{ role: 'system', content: systemFor(scene) }, { role: 'user', content: context }], max_tokens: 220 }), signal: AbortSignal.timeout(20000) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    content = j.choices?.[0]?.message?.content ?? ''; d = parseJSON(content); errs = validate(d); usage = j.usage || {};
    if (typeof j.actions_probability === 'number') prob = j.actions_probability;
  } catch (e) { errs = [`tuned endpoint: ${e.message}`]; }
  const latency_ms = Date.now() - t0;
  const call_id = await logCall(env, { scene, run_id, ts: now(), tier: 'nano', model: t.model, robot, event, latency_ms, usage, input: context, output: content, valid: !errs.length, errors: errs, fallback: errs.length ? 'served_nano' : null, decision: errs.length ? null : { ...d, actions_probability: prob } });
  return errs.length ? { decision: null, model: t.model, errors: errs, call_id } : { decision: d, model: t.model, latency_ms, call_id, actions_probability: prob };
}
async function tauFor(env, scene, sc) { const t = Number(await env.TAGS.get(`${scene}:tau`)); return t >= 0.3 && t <= 0.9 ? t : sc.tau; }
async function applyZones(env, scene, decision, by, run_id) {
  for (const a of decision.actions) if (a.type === 'quarantine_zone') for (const c of a.cells || []) await env.TAGS.put(`${scene}:zone:${c}`, JSON.stringify({ by, run_id, at: now() }), { expirationTtl: Math.max(60, a.ttl_s || 600) });
}

// a random 52-bit integer per posted event: unique without a counter, and still an exact JS/SQLite integer
const eventIndex = () => { const r = crypto.getRandomValues(new Uint32Array(2)); return r[0] * 0x100000 + (r[1] & 0xFFFFF); };
const sameText = (a, b) => { let d = a.length ^ b.length; for (let i = 0; i < b.length; i++) d |= (a.charCodeAt(i) || 0) ^ b.charCodeAt(i); return d === 0; };  // constant-time compare
const EVENT_KINDS = ['routine', 'first_sighting', 'repeat_sighting', 'variant', 'safety', 'peer_handshake'];
// One event through the pipeline: perception, fleet-memory lookup, Nano or Ultra, actions, stored decision, alarm.
// Shared by the rehearsal runner (POST scenario/step) and by robots posting their own events (POST events).
async function runEvent(env, req, scene, run_id, i, ev, sc) {
  if (await env.TAGS.get(`${scene}:pause`)) return J({ t: ev.t, robot: ev.robot, tier: 'paused', model_calls: 0, note: 'fleet paused by operator; no model call made' });
  const tau = await tauFor(env, scene, sc);
  if (ev.kind === 'peer_handshake') {
    const prev = await env.MEMORY.prepare(`SELECT * FROM precedents WHERE scene = ? AND safety = 0 AND ${LIVE_DECISION} ORDER BY created_at DESC LIMIT 1`).bind(scene, now()).first();  // any live, non-safety precedent, not only this run's
    if (prev) await env.MEMORY.prepare('INSERT INTO precedents (id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, expires_at, hazard_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)')
      .bind(uid('pr'), scene, prev.situation, prev.decision_json, 'peer', null, Math.max(0, (prev.confidence || 0.9) - 0.05), (prev.hops || 0) + 1, 0, run_id, new Date(Date.now() + 3600e3).toISOString(), prev.hazard_key || null).run();
    await env.TAGS.put(`${scene}:tag:${ev.robot}-from-${ev.from}`, JSON.stringify({ from: ev.from, hop: (prev?.hops || 0) + 1, at: now() }), { expirationTtl: 600 });
    return J({ t: ev.t, robot: ev.robot, tier: 'peer', model_calls: 0, note: prev ? `received precedent (hop ${(prev.hops || 0) + 1})` : 'no precedent yet to pass on' });
  }
  const m = await models(env, req);
  let seen = null, perception_error = null;
  const pref = {}, at = { event_index: i };
  if (ev.frame) seen = await perceive(env, req, m, scene, run_id, ev.robot, ev.frame, pref).catch(e => { perception_error = e.message; return null; });
  const safety = ev.kind === 'safety' || (seen && (seen.person_present || seen.recommended_action === 'escalate'));
  let ctx = `Site: ${sc.site}. Robot ${ev.robot} (${ev.device || 'robot'}) at ${ev.where}. ${ev.text}` + (seen ? `\nPerception (${m.perception_label || 'camera model'}): ${JSON.stringify(seen)}` : perception_error ? '\nPerception unavailable for this frame; camera content is unknown.' : '');
  // Fleet memory: a non-safety Ultra decision for this map cell is reused by Nano instead of calling Ultra again.
  // Safety precedents (person present) are never reused: those always go to Ultra (ARCHITECTURE.md invariant).
  const hazard = ['first_sighting', 'repeat_sighting', 'variant'].includes(ev.kind) || !!(seen && seen.recommended_action !== 'proceed' && (seen.hazards || []).length);
  const memo = hazard && ev.cell && !safety ? await lookupDecision(env, scene, ev.cell) : null;
  if (memo) ctx += `\nFleet memory: ${memo.source === 'operator' ? 'the operator' : 'Ultra'} already decided this hazard at cell ${ev.cell} (${memo.created_at}): ${memo.decision_json}. Apply the same decision to this robot if the situation matches. If what you see now differs from that precedent, say so in the rationale and lower your confidence.`;
  const novel = hazard && !memo;
  let tier = safety || novel ? 'ultra' : 'nano', out = null, memory = null, created = null, tuned = null, level = null;
  // Nano tier only: when the tuned adapter is promoted and serving for this scene it answers first; the served Nano is the fallback.
  const ad = tier === 'nano' ? await adapterFor(env, req, scene, m) : null;
  if (ad?.serving) {
    const t = m.reflex_tuned; level = (await autonomyFor(env, req, scene, ad)).level;
    out = await decideTuned(env, { base: t.base_url.replace(/\/+$/, ''), key: env[t.api_key_env], model: t.id || t.adapter }, scene, run_id, ev.robot, ev.kind, ctx);
    tuned = { model: out.model, used: !!out.decision, actions_probability: out.actions_probability ?? null, min_probability: level?.min_probability ?? null, fallback: out.decision ? null : out.errors.join('; ') };
    if (!out.decision) { await action(env, scene, 'tuned_fallback', { robot: ev.robot, model: out.model, reason: tuned.fallback, call_id: out.call_id, to: m.reflex }, 'nano', run_id, at); out = null; level = null; }
  }
  if (!out) out = await decide(env, m, scene, run_id, ev.robot, ev.kind, tier, ctx);
  const g = tier === 'nano' ? gateDecision(out, tau, level) : null;
  if (g?.escalate) { tier = 'ultra'; out = await decide(env, m, scene, run_id, ev.robot, ev.kind, 'ultra', ctx); }
  if (memo) {
    memory = { precedent: memo.id, cell: ev.cell, from: memo.created_at, ultra_avoided: tier === 'nano' && !!out.decision };
    await action(env, scene, memory.ultra_avoided ? 'memory_hit' : 'memory_override', memory, tier, run_id, at);
  }
  if (!out.decision) {  // invalid twice → safe stop (HANDOFF/ARCHITECTURE safety invariant)
    await env.TAGS.put(`${scene}:halt:${ev.robot}`, JSON.stringify({ by: 'safe_stop', run_id, at: now() }), { expirationTtl: 3600 });
    await action(env, scene, 'safe_stop', { robot: ev.robot, reason: 'no valid FleetAction after retry' }, tier, run_id, at);
  } else {
    await action(env, scene, 'decision', out.decision, tier, run_id, at);
    if (tier === 'ultra') await env.MEMORY.prepare('INSERT INTO precedents (id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, expires_at, hazard_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)')
      .bind(created = uid('pr'), scene, ctx.slice(0, 1000), JSON.stringify(out.decision), 'ultra', out.model, out.decision.confidence, 0, safety ? 1 : 0, run_id, new Date(Date.now() + 86400e3).toISOString(), ev.cell || null).run();
    await applyZones(env, scene, out.decision, tier, run_id);
  }
  const link = { event_index: i, event: { robot: ev.robot, where: ev.where, text: ev.text, cell: ev.cell || null, kind: ev.kind, frame: ev.frame || null }, safety, call_id: out.call_id, perception_id: pref.id || null,
    precedent_id: created || memo?.id || null, precedent_link: created ? 'created' : memo ? 'reused' : null };
  if (safety) await alarm(env, scene, 'crit', `${seen?.person_present ? 'Person' : 'Safety event'} near ${ev.robot} · ${ev.where}`, out.decision ? `Ultra: ${out.decision.actions.map(a => a.type).join(', ')} · ${out.decision.rationale || ''}` : 'no valid decision after retry → safe stop', run_id, link);
  else if (seen && seen.recommended_action !== 'proceed' && (seen.hazards || []).length) await alarm(env, scene, 'warn', `${String(seen.hazards[0].type).replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())} seen by ${ev.robot} · ${ev.where}`, seen.scene || '', run_id, link);
  else if (novel) await alarm(env, scene, 'warn', `Unknown hazard reported by ${ev.robot} · ${ev.where}`, out.decision ? `Ultra: ${out.decision.actions.map(a => a.type).join(', ')}` : 'no valid decision → safe stop', run_id, link);
  return J({ t: ev.t, robot: ev.robot, tau, tier, gate: safety ? 'safety' : novel ? 'novel' : tier === 'ultra' ? (g?.by === 'probability' ? 'low_probability' : 'low_confidence') : memory ? 'fleet_memory' : 'settled', memory, perception: seen, perception_error, perception_model: m.perception_label, tuned, decision: out.decision, errors: out.errors, model: out.model, latency_ms: out.latency_ms });
}

async function incident(env, id) {
  const a = await env.MEMORY.prepare('SELECT * FROM alarms WHERE id = ?').bind(id || '').first();
  if (!a) throw Object.assign(new Error('alarm not found'), { status: 404 });
  const one = (s, ...b) => env.MEMORY.prepare(s).bind(...b).first(), t = now();
  const call = a.call_id != null ? await one('SELECT id, ts, tier, model, latency_ms, valid, decision_json FROM calls WHERE id = ?', a.call_id) : null;
  const seen = a.perception_id ? await one('SELECT id, frame, robot, model, called_at, latency_ms, result_json FROM perception WHERE id = ?', a.perception_id) : null;
  const acts = (await env.MEMORY.prepare('SELECT id, type, payload_json, source, created_at FROM actions WHERE alarm_id = ?1 OR (?2 IS NOT NULL AND ?3 IS NOT NULL AND run_id = ?2 AND event_index = ?3) ORDER BY created_at').bind(a.id, a.run_id, a.event_index).all()).results;
  const pre = a.precedent_id ? await one('SELECT * FROM precedents WHERE id = ?', a.precedent_id) : null;
  const op = await one("SELECT * FROM precedents WHERE alarm_id = ? AND source = 'operator' ORDER BY created_at DESC LIMIT 1", a.id);
  const d = call ? parse(call.decision_json) : null, ov = [...acts].reverse().find(x => x.type === 'operator_override');
  const ovp = ov ? parse(ov.payload_json) : null;
  return {
    alarm: { id: a.id, scene: a.scene, sev: a.sev, title: a.title, meta: a.meta, status: a.status, created_at: a.created_at, updated_at: a.updated_at, person: !!a.safety },
    event: parse(a.event_json),
    perception: seen ? { frame: seen.frame, model: seen.model, called_at: seen.called_at, latency_ms: seen.latency_ms, result: parse(seen.result_json) } : null,
    decision: call ? { tier: call.tier, model: call.model, latency_ms: call.latency_ms, valid: !!call.valid, actions: d?.actions || null, confidence: d?.confidence ?? null, rationale: d?.rationale || null, at: call.ts } : null,
    actions: acts.map(x => ({ id: x.id, type: x.type, source: x.source, created_at: x.created_at, payload: parse(x.payload_json) })),
    stored_decision: pre ? { link: a.precedent_link, ...decisionRow(pre, t) } : null,
    override: ovp ? { at: ov.created_at, actions: ovp.actions, note: ovp.note, stored_decision: op ? decisionRow(op, t) : null } : null,
    vocabulary: ACTIONS, severities: FIELD.severity.enum,
  };
}

const routes = {
  'GET health': async (env, req) => {
    const m = await models(env, req).catch(() => ({}));
    const d1 = await env.MEMORY.prepare('SELECT COUNT(*) n FROM calls').first().then(() => true).catch(() => false);
    return J({ d1, kv: !!env.TAGS, r2: !!env.RUNS, nebius_key: !!env.NEBIUS_API_KEY, models: m });
  },
  'GET state': async (env, req, url) => {
    const scene = url.searchParams.get('scene'); if (!SCENARIOS[scene]) return J({ error: `scene must be one of ${Object.keys(SCENARIOS).join(', ')}` }, 400);
    const q = (s, ...b) => env.MEMORY.prepare(s).bind(...b).all().then(r => r.results);
    const [alarms, actions, calls, perception, precedents, night] = await Promise.all([
      q("SELECT * FROM alarms WHERE scene = ? AND status != 'released' ORDER BY created_at DESC LIMIT 20", scene),
      q('SELECT * FROM actions WHERE scene = ? ORDER BY created_at DESC LIMIT 10', scene),
      q('SELECT id, run_id, ts, tier, model, robot, event, latency_ms, prompt_tokens, completion_tokens, valid, decision_json, replay_json FROM calls WHERE scene = ? ORDER BY ts DESC LIMIT 200', scene),
      q('SELECT frame, robot, model, called_at, latency_ms, result_json FROM perception WHERE scene = ? ORDER BY called_at DESC LIMIT 40', scene),
      q("SELECT COUNT(*) n, SUM(source = 'peer') peer FROM precedents WHERE scene = ? AND (expires_at IS NULL OR expires_at > ?)", scene, now()),
      q('SELECT * FROM night_shift WHERE id LIKE ? ORDER BY started_at DESC LIMIT 8', `${scene}/%`)]);
    const tags = (await env.TAGS.list({ prefix: `${scene}:` })).keys.map(k => ({ name: k.name, expires: k.expiration ? new Date(k.expiration * 1000).toISOString() : null }));
    const peer_total = (await env.MEMORY.prepare("SELECT COUNT(*) n FROM precedents WHERE scene = ? AND source = 'peer'").bind(scene).first()).n;
    const sc = await scenario(env, req, scene), tau = await tauFor(env, scene, sc), adapter = await adapterFor(env, req, scene);
    // Fleet memory: Ultra calls avoided, and what an Ultra call costs on average (real calls only).
    const memory = await env.MEMORY.prepare("SELECT SUM(type = 'memory_hit') hits, SUM(type = 'memory_override') overrides FROM actions WHERE scene = ?").bind(scene).first();
    const ultra = await env.MEMORY.prepare("SELECT COUNT(*) n, AVG(latency_ms) ms, AVG(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)) tokens FROM calls WHERE scene = ? AND tier = 'ultra' AND valid = 1").bind(scene).first();
    return J({ scene, alarms, actions, calls, perception, precedents: { ...precedents[0], peer_total }, night_shift: night, tags, tau, tau_default: sc.tau, adapter, autonomy: await autonomyFor(env, req, scene, adapter), paused: !!(await env.TAGS.get(`${scene}:pause`)),
      memory: { hits: memory?.hits || 0, overrides: memory?.overrides || 0, ultra_calls: ultra?.n || 0, ultra_avg_ms: ultra?.ms ?? null, ultra_avg_tokens: ultra?.tokens ?? null } });
  },
  'POST alarms/ack': async (env, req, url, body) => { await env.MEMORY.prepare("UPDATE alarms SET status = CASE status WHEN 'acked' THEN 'open' ELSE 'acked' END, updated_at = ? WHERE id = ?").bind(now(), body.id).run(); return J({ ok: true }); },
  'POST alarms/release': async (env, req, url, body) => {
    const a = await env.MEMORY.prepare('SELECT * FROM alarms WHERE id = ?').bind(body.id).first();
    if (!a) return J({ error: 'alarm not found' }, 404);
    await env.MEMORY.prepare("UPDATE alarms SET status = 'released', updated_at = ? WHERE id = ?").bind(now(), body.id).run();
    const zones = (await env.TAGS.list({ prefix: `${a.scene}:zone:` })).keys; await Promise.all(zones.map(k => env.TAGS.delete(k.name)));
    await action(env, a.scene, 'release_zone', { alarm: a.id, zones: zones.map(k => k.name) }, 'operator', a.run_id, { alarm_id: a.id });
    return J({ ok: true, released_zones: zones.length });
  },
  'POST actions': async (env, req, url, body) => {
    const { scene, type } = body; if (!SCENARIOS[scene]) return J({ error: 'bad scene' }, 400);
    let alarm_id = null;
    if (type === 'quarantine_zone') { await env.TAGS.put(`${scene}:zone:${body.zone}`, JSON.stringify({ by: 'operator', at: now() }), { expirationTtl: 600 }); alarm_id = await alarm(env, scene, 'info', `Zone ${body.zone} quarantined by operator`, 'expires in 10 min'); }
    else if (type === 'halt') { await env.TAGS.put(`${scene}:halt:${body.robot}`, JSON.stringify({ by: 'operator', at: now() }), { expirationTtl: 3600 }); }
    else if (type === 'broadcast_hazard') { await env.TAGS.put(`${scene}:tag:broadcast-${Date.now()}`, JSON.stringify({ message: body.message || 'operator broadcast', at: now() }), { expirationTtl: 600 }); }
    else if (type === 'pause_fleet') { await env.TAGS.put(`${scene}:pause`, JSON.stringify({ by: 'operator', at: now() })); alarm_id = await alarm(env, scene, 'info', 'Fleet paused by operator', 'no model calls until resumed'); }
    else if (type === 'resume_fleet') { await env.TAGS.delete(`${scene}:pause`); }
    else if (type === 'set_tau') { const t = Number(body.tau); if (!(t >= 0.3 && t <= 0.9)) return J({ error: 'tau must be in [0.30, 0.90]' }, 400); await env.TAGS.put(`${scene}:tau`, String(t)); }
    else if (type === 'set_autonomy') {
      if (body.target_error == null) await env.TAGS.delete(`${scene}:autonomy`);
      else { const levels = await gateLevels(env, req), t = Number(body.target_error);
        if (!levels.some(l => l.target_error === t)) return J({ error: levels.length ? `target_error must be one of ${levels.map(l => l.target_error).join(', ')}` : 'no measured gate levels are published' }, 400);
        await env.TAGS.put(`${scene}:autonomy`, String(t)); }
    }
    else if (type === 'promote_adapter') {
      const ad = await adapterFor(env, req, scene);
      if (!ad || !ad.configured) return J({ error: 'Not serving: no endpoint is configured for the tuned adapter' }, 409);
      if (!ad.key) return J({ error: `Not serving: ${ad.key_env} is not set on the Pages project` }, 409);
      await env.TAGS.put(`${scene}:promoted`, JSON.stringify({ adapter: ad.adapter, by: 'operator', at: now() }));
    }
    else if (type === 'hold_adapter') { await env.TAGS.delete(`${scene}:promoted`); }
    else if (type === 'rollback_nano') { await env.TAGS.delete(`${scene}:promoted`); await env.TAGS.put(`${scene}:adapter`, JSON.stringify({ adapter: 'previous', at: now() })); }
    else if (type === 'escalate') {
      const m = await models(env, req), open = await env.MEMORY.prepare("SELECT title, meta FROM alarms WHERE scene = ? AND status = 'open' ORDER BY created_at DESC LIMIT 3").bind(scene).all();
      const ctx = `Operator escalation at ${scene}. Open alarms: ${JSON.stringify(open.results)}. Decide the fleet response.`;
      const out = await decide(env, m, scene, null, body.robot || null, 'operator_escalation', 'ultra', ctx);
      if (out.decision) { await action(env, scene, 'ultra_decision', out.decision, 'ultra'); await applyZones(env, scene, out.decision, 'ultra', null); }
      return J({ ok: !!out.decision, decision: out.decision, model: out.model, latency_ms: out.latency_ms });
    } else return J({ error: `unknown action ${type}` }, 400);
    await action(env, scene, type, body, 'operator', null, { alarm_id });
    return J({ ok: true });
  },
  'POST scenario/start': async (env, req, url, body) => {
    const sc = await scenario(env, req, body.scene), run_id = `${sc.id}-${now().replace(/[:.]/g, '-')}`;
    await env.MEMORY.prepare('INSERT INTO runs (id, scenario, scene, dry_run, started_at, r2_prefix) VALUES (?,?,?,?,?,?)').bind(run_id, sc.id, body.scene, 0, now(), `calls/${body.scene}/`).run();
    return J({ run_id, events: sc.events, tau: await tauFor(env, body.scene, sc), paused: !!(await env.TAGS.get(`${body.scene}:pause`)), nebius_key: !!env.NEBIUS_API_KEY });
  },
  'POST scenario/step': async (env, req, url, body) => {
    const { scene, run_id, i } = body, sc = await scenario(env, req, scene), ev = sc.events[i];
    if (!ev) return J({ error: 'no such event' }, 400);
    return runEvent(env, req, scene, run_id, i, ev, sc);
  },
  // A robot posts one event; it goes through the same pipeline as a rehearsal step. Events are grouped under one run per scene per day unless a run_id is passed.
  'POST events': async (env, req, url, body) => {
    if (!env.EVENTS_TOKEN) return J({ error: 'Robot events are disabled: EVENTS_TOKEN is not set on the Pages project. Run: npx wrangler pages secret put EVENTS_TOKEN --project-name nemofleet' }, 503);
    if (!sameText(req.headers.get('authorization') || '', `Bearer ${env.EVENTS_TOKEN}`)) return J({ error: 'missing or wrong events token' }, 401);
    const { scene } = body, errs = [];
    if (!SCENARIOS[scene]) return J({ error: `scene must be one of ${Object.keys(SCENARIOS).join(', ')}` }, 400);
    for (const k of ['robot', 'where', 'kind', 'text']) if (typeof body[k] !== 'string' || !body[k].trim()) errs.push(`"${k}" is required`);
    for (const k of ['device', 'cell', 'frame', 'from', 'run_id']) if (body[k] != null && (typeof body[k] !== 'string' || !body[k].trim())) errs.push(`"${k}" must be a non-empty string`);
    if (typeof body.kind === 'string' && body.kind.trim() && !EVENT_KINDS.includes(body.kind)) errs.push(`"kind" must be one of ${EVENT_KINDS.join(', ')}`);
    if (body.frame != null && !/^[\w-]+$/.test(String(body.frame))) errs.push('"frame" must be a camera frame name');
    if (errs.length) return J({ error: errs.join('; '), errors: errs }, 400);
    const sc = await scenario(env, req, scene), t = now(), run_id = body.run_id || `events-${scene}-${t.slice(0, 10)}`;
    await env.MEMORY.prepare('INSERT OR IGNORE INTO runs (id, scenario, scene, dry_run, started_at, r2_prefix) VALUES (?,?,?,?,?,?)').bind(run_id, 'events', scene, 0, t, `calls/${scene}/`).run();
    const ev = { t, robot: body.robot.trim(), device: body.device || null, where: body.where.trim(), cell: body.cell || null, kind: body.kind, text: body.text.trim().slice(0, 2000), frame: body.frame || null, from: body.from || 'fleet' };
    const res = await runEvent(env, req, scene, run_id, eventIndex(), ev, sc), out = await res.json();
    return J({ run_id, ...out }, res.status);
  },
  'POST scenario/finish': async (env, req, url, body) => {
    const t = await env.MEMORY.prepare('SELECT tier, COUNT(*) n FROM calls WHERE run_id = ? GROUP BY tier').bind(body.run_id).all();
    await env.MEMORY.prepare('UPDATE runs SET finished_at = ?, totals_json = ? WHERE id = ?').bind(now(), JSON.stringify(t.results), body.run_id).run();
    return J({ ok: true, totals: t.results });
  },
  // ---- decision book ----
  'GET decisions': async (env, req, url) => {
    const scene = url.searchParams.get('scene'); if (!SCENARIOS[scene]) return J({ error: 'bad scene' }, 400);
    const t = now(), since = new Date(Date.now() - 86400e3).toISOString();  // live, plus anything that expired in the last day
    const r = await env.MEMORY.prepare(`SELECT p.*, (SELECT COUNT(*) FROM actions a WHERE a.scene = p.scene AND a.type = 'memory_hit' AND json_extract(a.payload_json, '$.precedent') = p.id) reuse_count
      FROM precedents p WHERE p.scene = ? AND p.source IN ('ultra', 'operator') AND (p.pinned = 1 OR p.expires_at IS NULL OR p.expires_at > ?) ORDER BY p.created_at DESC LIMIT 100`).bind(scene, since).all();
    return J({ scene, decisions: r.results.map(p => decisionRow(p, t)) });
  },
  // the decision Nano would be handed for a hazard at this cell right now (the same lookup the step handler uses)
  'GET decisions/lookup': async (env, req, url) => {
    const scene = url.searchParams.get('scene'), cell = url.searchParams.get('cell'); if (!SCENARIOS[scene] || !cell) return J({ error: 'scene and cell are required' }, 400);
    const p = await lookupDecision(env, scene, cell);
    return J({ scene, cell, decision: p ? decisionRow(p) : null });
  },
  'POST decisions/update': async (env, req, url, body) => {
    const p = await env.MEMORY.prepare("SELECT * FROM precedents WHERE id = ? AND source IN ('ultra', 'operator')").bind(body.id || '').first();
    if (!p) return J({ error: 'decision not found' }, 404);
    if (p.revoked_at) return J({ error: 'decision is revoked' }, 409);
    const patch = {};
    if (body.expires_in_s !== undefined) { const s = Number(body.expires_in_s); if (!(s >= 60 && s <= 30 * 86400)) return J({ error: 'expires_in_s must be between 60 and 2592000' }, 400); patch.expires_at = new Date(Date.now() + s * 1000).toISOString(); }
    if (body.pinned !== undefined) { if (typeof body.pinned !== 'boolean') return J({ error: 'pinned must be true or false' }, 400); patch.pinned = body.pinned ? 1 : 0; }
    if (!Object.keys(patch).length) return J({ error: 'send expires_in_s or pinned' }, 400);
    await env.MEMORY.prepare('UPDATE precedents SET expires_at = ?, pinned = ? WHERE id = ?').bind(patch.expires_at ?? p.expires_at, patch.pinned ?? p.pinned, p.id).run();
    await action(env, p.scene, 'decision_update', { decision: p.id, cell: p.hazard_key, ...patch }, 'operator');
    return J({ ok: true, decision: decisionRow({ ...p, ...patch }) });
  },
  'POST decisions/revoke': async (env, req, url, body) => {
    const p = await env.MEMORY.prepare("SELECT * FROM precedents WHERE id = ? AND source IN ('ultra', 'operator')").bind(body.id || '').first();
    if (!p) return J({ error: 'decision not found' }, 404);
    const t = p.revoked_at || now();
    if (!p.revoked_at) {
      await env.MEMORY.prepare('UPDATE precedents SET revoked_at = ?, pinned = 0 WHERE id = ?').bind(t, p.id).run();
      // the copies robots passed to each other came from this decision: they go with it
      await env.MEMORY.prepare("UPDATE precedents SET revoked_at = ? WHERE scene = ? AND source = 'peer' AND revoked_at IS NULL AND decision_json = ? AND COALESCE(hazard_key, '') = COALESCE(?, '')").bind(t, p.scene, p.decision_json, p.hazard_key).run();
      await action(env, p.scene, 'decision_revoke', { decision: p.id, cell: p.hazard_key }, 'operator');
    }
    return J({ ok: true, decision: decisionRow({ ...p, revoked_at: t, pinned: 0 }) });
  },
  // ---- incident record ----
  'GET incident': async (env, req, url) => J(await incident(env, url.searchParams.get('id'))),
  'POST incident/override': async (env, req, url, body) => {
    const a = await env.MEMORY.prepare('SELECT * FROM alarms WHERE id = ?').bind(body.id || '').first();
    if (!a) return J({ error: 'alarm not found' }, 404);
    if (!Array.isArray(body.actions)) return J({ error: 'invalid actions: actions must be a non-empty array' }, 400);
    const decision = { actions: body.actions, confidence: 1, rationale: String(body.note || '').slice(0, 500) };
    const errs = validate(decision);
    (Array.isArray(body.actions) ? body.actions : []).forEach((x, i) => (ACTIONS[x && x.type] || []).forEach(k => {  // operator input: fields must also be filled and of the right kind
      const v = x[k], ok = k === 'cells' ? Array.isArray(v) && v.length > 0 && v.every(c => typeof c === 'string' && c.trim()) : k === 'ttl_s' ? Number.isInteger(v) && v >= 60 && v <= 86400 : k === 'severity' ? FIELD.severity.enum.includes(v) : typeof v === 'string' && !!v.trim();
      if (v !== undefined && !ok) errs.push(`actions[${i}] (${x.type}) "${k}" is invalid`);
    }));
    if (errs.length) return J({ error: `invalid actions: ${errs.join('; ')}`, errors: errs }, 400);
    const ev = parse(a.event_json), cell = ev?.cell || null, t = now();
    // Only a hazard at a map cell with no person involved becomes a reusable stored decision.
    let stored = null, superseded = [];
    if (cell && !a.safety) {
      stored = uid('pr');
      await env.MEMORY.prepare('INSERT INTO precedents (id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, expires_at, hazard_key, alarm_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)')
        .bind(stored, a.scene, `Robot ${ev.robot || ''} at ${ev.where || cell}. ${ev.text || a.title}`.slice(0, 1000), JSON.stringify(decision), 'operator', null, 1, 0, 0, a.run_id || null, new Date(Date.now() + 86400e3).toISOString(), cell, a.id).run();
      superseded = (await env.MEMORY.prepare("SELECT id FROM precedents WHERE scene = ? AND hazard_key = ? AND safety = 0 AND source IN ('ultra', 'operator', 'peer') AND superseded_by IS NULL AND id != ?").bind(a.scene, cell, stored).all()).results.map(r => r.id);
      await env.MEMORY.prepare("UPDATE precedents SET superseded_by = ? WHERE scene = ? AND hazard_key = ? AND safety = 0 AND source IN ('ultra', 'operator', 'peer') AND superseded_by IS NULL AND id != ?").bind(stored, a.scene, cell, stored).run();
    }
    await action(env, a.scene, 'operator_override', { alarm: a.id, actions: decision.actions, note: decision.rationale, stored_decision: stored, superseded, replaced_call: a.call_id ?? null }, 'operator', a.run_id, { alarm_id: a.id, event_index: a.event_index });
    await applyZones(env, a.scene, decision, 'operator', a.run_id);
    await env.MEMORY.prepare("UPDATE alarms SET status = 'acked', updated_at = ? WHERE id = ? AND status = 'open'").bind(t, a.id).run();
    return J({ ok: true, stored_decision: stored, superseded, incident: await incident(env, a.id) });
  },
  'GET episodes': async (env, req, url) => {
    const r = await env.MEMORY.prepare("SELECT id, run_id, ts, tier, model, robot, event, latency_ms, valid, decision_json, replay_json FROM calls WHERE scene = ? AND tier IN ('nano', 'ultra') ORDER BY ts DESC LIMIT 50").bind(url.searchParams.get('scene')).all();
    return J({ episodes: r.results });
  },
  'POST night-shift/replay': async (env, req, url, body) => {
    const scene = body.scene, m = await models(env, req), night = `night-${now().slice(0, 10)}`;
    if (!m.deliberator) throw Object.assign(new Error('No Ultra model id configured.'), { status: 503 });
    needKey(env);
    const rows = (await env.MEMORY.prepare("SELECT id, robot, event, decision_json FROM calls WHERE scene = ? AND tier = 'nano' AND valid = 1 AND replay_json IS NULL ORDER BY ts DESC LIMIT 4").bind(scene).all()).results;
    await env.MEMORY.prepare("INSERT OR REPLACE INTO night_shift (id, night, stage, status, started_at) VALUES (?,?,?,?,COALESCE((SELECT started_at FROM night_shift WHERE id = ?), ?))").bind(`${scene}/${night}/replay`, night, 'replay', 'running', `${scene}/${night}/replay`, now()).run();
    const verdicts = [];
    for (const r of rows) {
      const out = await respond(env, m.base, m.deliberator, 'You audit a robot reflex model. Reply with only JSON {"agree": boolean, "better_action": string|null, "reason": "one sentence"}.',
        `Robot ${r.robot}, event ${r.event}. Reflex decision: ${r.decision_json}. Would you have made the same decision?`, VERDICT_SCHEMA);
      const v = parseJSON(out.content) || { agree: null, reason: 'unparsed', raw: out.content };
      await env.MEMORY.prepare('UPDATE calls SET replay_json = ? WHERE id = ?').bind(JSON.stringify(v), r.id).run();
      verdicts.push({ id: r.id, ...v });
    }
    const left = (await env.MEMORY.prepare("SELECT COUNT(*) n FROM calls WHERE scene = ? AND tier = 'nano' AND valid = 1 AND replay_json IS NULL").bind(scene).first()).n;
    const tot = await env.MEMORY.prepare("SELECT COUNT(*) n, SUM(json_extract(replay_json, '$.agree') = 0) disagree FROM calls WHERE scene = ? AND replay_json IS NOT NULL").bind(scene).first();
    await env.MEMORY.prepare('UPDATE night_shift SET status = ?, metrics_json = ?, finished_at = ? WHERE id = ?').bind(left ? 'running' : 'succeeded', JSON.stringify({ rejudged: tot.n, disagree: tot.disagree || 0 }), left ? null : now(), `${scene}/${night}/replay`).run();
    return J({ verdicts, remaining: left, rejudged: tot.n, disagree: tot.disagree || 0,
      next_stages: 'Dream, Gate and Consolidate run as Nebius Serverless Jobs; that runner is not built yet.' });
  },
};

export async function onRequest({ request, env, params }) {
  const url = new URL(request.url), path = (params.path || []).join('/'), key = `${request.method} ${path}`;
  const h = routes[key];
  if (!h) return J({ error: `no route ${key}` }, 404);
  try {
    const body = request.method === 'POST' ? await request.json().catch(() => ({})) : {};
    return await h(env, request, url, body);
  } catch (e) { return J({ error: e.message }, e.status || 500); }
}
