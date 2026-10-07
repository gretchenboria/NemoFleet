// NemoFleet console API (Cloudflare Pages Functions). Bindings: MEMORY (D1), TAGS (KV), RUNS (R2), ASSETS.
// Secret: NEBIUS_API_KEY (wrangler pages secret put NEBIUS_API_KEY --project-name nemofleet).
// Everything here is real: D1/KV/R2 writes, and Token Factory calls when the key is set.

const J = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
const now = () => new Date().toISOString();
const uid = p => `${p}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
const SCENARIOS = { warehouse: 'aisle4-spill', datacenter: 'hall-b-coolant-leak' };
const ACTIONS = { goto: ['robot', 'target'], halt: ['robot'], quarantine_zone: ['cells', 'ttl_s'], reassign_task: ['task', 'robot'], alert_human: ['severity', 'message'], proceed: ['robot'], reroute: ['robot', 'via'] };
const SYSTEM_BASE = 'You are the decision module of NemoFleet, a robot fleet. Decide what the robot or fleet should do next. Never output coordinates or paths: a deterministic planner owns motion. Reply with only one JSON object: {"actions": [ __EXAMPLES__ ], "confidence": 0.0-1.0, "rationale": "one sentence"}';
const EXAMPLES = {
  warehouse: '{"type": "proceed", "robot": "R07"} | {"type": "reroute", "robot": "R14", "via": "aisle 3"} | {"type": "halt", "robot": "R03"} | {"type": "quarantine_zone", "cells": ["A4"], "ttl_s": 600} | {"type": "goto", "robot": "R05", "target": "dock 2"} | {"type": "reassign_task", "task": "PICK-4471", "robot": "R05"} | {"type": "alert_human", "severity": "high", "message": "..."}',
  datacenter: '{"type": "proceed", "robot": "R07"} | {"type": "reroute", "robot": "R14", "via": "cold aisle 3"} | {"type": "halt", "robot": "R03"} | {"type": "quarantine_zone", "cells": ["C2"], "ttl_s": 600} | {"type": "goto", "robot": "R05", "target": "staging bay 1"} | {"type": "reassign_task", "task": "SWAP-B4-17-drive-3", "robot": "R05"} | {"type": "alert_human", "severity": "high", "message": "..."}',
};
const systemFor = scene => SYSTEM_BASE.replace('__EXAMPLES__', EXAMPLES[scene] || EXAMPLES.warehouse);

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

async function chat(env, base, model, messages, max_tokens = 800) {
  needKey(env);
  const t0 = Date.now();
  const r = await fetch(`${base}/chat/completions`, { method: 'POST', headers: { Authorization: `Bearer ${env.NEBIUS_API_KEY}`, 'content-type': 'application/json' }, body: JSON.stringify({ model, messages, temperature: 0.2, max_tokens }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(`${model}: HTTP ${r.status} ${JSON.stringify(j).slice(0, 240)}`), { status: 502 });
  return { latency_ms: Date.now() - t0, usage: j.usage || {}, content: j.choices?.[0]?.message?.content ?? '' };
}
async function logCall(env, rec) {
  const key = `calls/${rec.scene}/${rec.ts.slice(0, 10)}/${uid(rec.tier)}.json`;
  await env.RUNS.put(key, JSON.stringify(rec));
  await env.MEMORY.prepare('INSERT INTO calls (run_id, ts, tier, model, robot, event, latency_ms, prompt_tokens, completion_tokens, valid, r2_key, scene, decision_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)')
    .bind(rec.run_id || null, rec.ts, rec.tier, rec.model, rec.robot || null, rec.event || null, rec.latency_ms || null, rec.usage?.prompt_tokens ?? null, rec.usage?.completion_tokens ?? null, rec.valid == null ? null : rec.valid ? 1 : 0, key, rec.scene, rec.decision ? JSON.stringify(rec.decision) : null).run();
}
async function decide(env, m, scene, run_id, robot, event, tier, context) {
  const model = tier === 'ultra' ? m.deliberator : m.reflex;
  if (!model) throw Object.assign(new Error(`No ${tier === 'ultra' ? 'deliberator (Ultra)' : 'reflex (Nano)'} model id in config/models.yaml. Run node tools/preflight.cjs --write and redeploy.`), { status: 503 });
  let msgs = [{ role: 'system', content: systemFor(scene) }, { role: 'user', content: context }], errs = [];
  for (let attempt = 1; attempt <= 2; attempt++) {
    const r = await chat(env, m.base, model, msgs, 2000);  // reasoning models spend 400+ tokens thinking first
    const d = parseJSON(r.content); errs = validate(d);
    await logCall(env, { scene, run_id, ts: now(), tier, model, robot, event, latency_ms: r.latency_ms, usage: r.usage, input: context, output: r.content, valid: !errs.length, errors: errs, decision: errs.length ? null : d });
    if (!errs.length) return { decision: d, model, latency_ms: r.latency_ms };
    msgs = [...msgs, { role: 'assistant', content: r.content }, { role: 'user', content: `Invalid: ${errs.join('; ')}. Reply again with only the corrected JSON object.` }];
  }
  return { decision: null, model, errors: errs };
}
async function perceive(env, req, m, scene, run_id, robot, frame) {
  if (!m.perception) throw Object.assign(new Error('No perception (Cosmos) model id in config/models.yaml.'), { status: 503 });
  const buf = new Uint8Array(await (await asset(env, req, `/assets/scenes/${scene}/frames/${frame}.jpg`)).arrayBuffer());
  let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  const prompt = 'Analyze this robot camera frame for the planner. Return JSON with keys "scene" (one sentence), "hazards" (array of {"type","description","severity"}), "person_present" (boolean), "path_clear" (boolean), "recommended_action" ("proceed"|"slow"|"reroute"|"halt"|"escalate"), "confidence" (0-1). A person in the robot\'s lane always means "escalate".';
  const r = await chat(env, m.base, m.perception, [{ role: 'system', content: `You are the perception module of an autonomous robot in a ${scene === 'warehouse' ? 'fulfillment warehouse' : 'hyperscale data center hall'}. Report only what is visible. Answer with one JSON object.` },
    { role: 'user', content: [{ type: 'image_url', image_url: { url: `data:image/jpeg;base64,${btoa(bin)}` } }, { type: 'text', text: prompt }] }], 700);
  const result = parseJSON(r.content), ts = now(), key = `perception/${scene}/${frame}/${ts}.json`;
  await env.RUNS.put(key, JSON.stringify({ scene, frame, robot, model: m.perception, ts, latency_ms: r.latency_ms, usage: r.usage, raw: r.content, result }));
  await env.MEMORY.prepare('INSERT INTO perception (id, scene, frame, robot, model, called_at, latency_ms, result_json, raw_r2_key) VALUES (?,?,?,?,?,?,?,?,?)').bind(`${scene}/${frame}/${ts}`, scene, frame, robot, m.perception, ts, r.latency_ms, JSON.stringify(result), key).run();
  await logCall(env, { scene, run_id, ts, tier: 'perception', model: m.perception, robot, event: frame, latency_ms: r.latency_ms, usage: r.usage, output: r.content, valid: !!result });
  return result;
}
async function alarm(env, scene, sev, title, meta, run_id) {
  await env.MEMORY.prepare('INSERT INTO alarms (id, scene, sev, title, meta, run_id) VALUES (?,?,?,?,?,?)').bind(uid('al'), scene, sev, title, meta, run_id || null).run();
}
async function action(env, scene, type, payload, source, run_id) {
  await env.MEMORY.prepare('INSERT INTO actions (id, scene, type, payload_json, source, run_id) VALUES (?,?,?,?,?,?)').bind(uid('act'), scene, type, JSON.stringify(payload), source, run_id || null).run();
}

async function tauFor(env, scene, sc) { const t = Number(await env.TAGS.get(`${scene}:tau`)); return t >= 0.3 && t <= 0.9 ? t : sc.tau; }
async function applyZones(env, scene, decision, by, run_id) {
  for (const a of decision.actions) if (a.type === 'quarantine_zone') for (const c of a.cells || []) await env.TAGS.put(`${scene}:zone:${c}`, JSON.stringify({ by, run_id, at: now() }), { expirationTtl: Math.max(60, a.ttl_s || 600) });
}

const routes = {
  'GET health': async (env, req) => {
    const m = await models(env, req).catch(() => ({}));
    const d1 = await env.MEMORY.prepare('SELECT COUNT(*) n FROM calls').first().then(() => true).catch(() => false);
    return J({ d1, kv: !!env.TAGS, r2: !!env.RUNS, nebius_key: !!env.NEBIUS_API_KEY, models: m });
  },
  'GET state': async (env, req, url) => {
    const scene = url.searchParams.get('scene'); if (!SCENARIOS[scene]) return J({ error: 'scene must be warehouse or datacenter' }, 400);
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
    const sc = await scenario(env, req, scene), tau = await tauFor(env, scene, sc);
    return J({ scene, alarms, actions, calls, perception, precedents: { ...precedents[0], peer_total }, night_shift: night, tags, tau, tau_default: sc.tau, paused: !!(await env.TAGS.get(`${scene}:pause`)) });
  },
  'POST alarms/ack': async (env, req, url, body) => { await env.MEMORY.prepare("UPDATE alarms SET status = CASE status WHEN 'acked' THEN 'open' ELSE 'acked' END, updated_at = ? WHERE id = ?").bind(now(), body.id).run(); return J({ ok: true }); },
  'POST alarms/release': async (env, req, url, body) => {
    const a = await env.MEMORY.prepare('SELECT * FROM alarms WHERE id = ?').bind(body.id).first();
    if (!a) return J({ error: 'alarm not found' }, 404);
    await env.MEMORY.prepare("UPDATE alarms SET status = 'released', updated_at = ? WHERE id = ?").bind(now(), body.id).run();
    const zones = (await env.TAGS.list({ prefix: `${a.scene}:zone:` })).keys; await Promise.all(zones.map(k => env.TAGS.delete(k.name)));
    await action(env, a.scene, 'release_zone', { alarm: a.id, zones: zones.map(k => k.name) }, 'operator');
    return J({ ok: true, released_zones: zones.length });
  },
  'POST actions': async (env, req, url, body) => {
    const { scene, type } = body; if (!SCENARIOS[scene]) return J({ error: 'bad scene' }, 400);
    if (type === 'quarantine_zone') { await env.TAGS.put(`${scene}:zone:${body.zone}`, JSON.stringify({ by: 'operator', at: now() }), { expirationTtl: 600 }); await alarm(env, scene, 'info', `Zone ${body.zone} quarantined by operator`, 'expires in 10 min (KV TTL)'); }
    else if (type === 'halt') { await env.TAGS.put(`${scene}:halt:${body.robot}`, JSON.stringify({ by: 'operator', at: now() }), { expirationTtl: 3600 }); }
    else if (type === 'broadcast_hazard') { await env.TAGS.put(`${scene}:tag:broadcast-${Date.now()}`, JSON.stringify({ message: body.message || 'operator broadcast', at: now() }), { expirationTtl: 600 }); }
    else if (type === 'pause_fleet') { await env.TAGS.put(`${scene}:pause`, JSON.stringify({ by: 'operator', at: now() })); await alarm(env, scene, 'info', 'Fleet paused by operator', 'scenario steps make no model calls until resumed'); }
    else if (type === 'resume_fleet') { await env.TAGS.delete(`${scene}:pause`); }
    else if (type === 'set_tau') { const t = Number(body.tau); if (!(t >= 0.3 && t <= 0.9)) return J({ error: 'tau must be in [0.30, 0.90]' }, 400); await env.TAGS.put(`${scene}:tau`, String(t)); }
    else if (type === 'rollback_nano') { await env.TAGS.put(`${scene}:adapter`, JSON.stringify({ adapter: 'previous', at: now() })); }
    else if (type === 'escalate') {
      const m = await models(env, req), open = await env.MEMORY.prepare("SELECT title, meta FROM alarms WHERE scene = ? AND status = 'open' ORDER BY created_at DESC LIMIT 3").bind(scene).all();
      const ctx = `Operator escalation at ${scene}. Open alarms: ${JSON.stringify(open.results)}. Decide the fleet response.`;
      const out = await decide(env, m, scene, null, body.robot || null, 'operator_escalation', 'ultra', ctx);
      if (out.decision) { await action(env, scene, 'ultra_decision', out.decision, 'ultra'); await applyZones(env, scene, out.decision, 'ultra', null); }
      return J({ ok: !!out.decision, decision: out.decision, model: out.model, latency_ms: out.latency_ms });
    } else return J({ error: `unknown action ${type}` }, 400);
    await action(env, scene, type, body, 'operator');
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
    if (await env.TAGS.get(`${scene}:pause`)) return J({ t: ev.t, robot: ev.robot, tier: 'paused', model_calls: 0, note: 'fleet paused by operator; no model call made' });
    const tau = await tauFor(env, scene, sc);
    if (ev.kind === 'peer_handshake') {
      const prev = await env.MEMORY.prepare('SELECT * FROM precedents WHERE scene = ? AND run_id = ? ORDER BY created_at DESC LIMIT 1').bind(scene, run_id).first();
      if (prev) await env.MEMORY.prepare('INSERT INTO precedents (id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)')
        .bind(uid('pr'), scene, prev.situation, prev.decision_json, 'peer', null, Math.max(0, (prev.confidence || 0.9) - 0.05), (prev.hops || 0) + 1, 0, run_id, new Date(Date.now() + 3600e3).toISOString()).run();
      await env.TAGS.put(`${scene}:tag:${ev.robot}-from-${ev.from}`, JSON.stringify({ from: ev.from, hop: (prev?.hops || 0) + 1, at: now() }), { expirationTtl: 600 });
      return J({ t: ev.t, robot: ev.robot, tier: 'peer', model_calls: 0, note: prev ? `received precedent (hop ${(prev.hops || 0) + 1})` : 'no precedent yet to pass on' });
    }
    const m = await models(env, req);
    let seen = null, perception_error = null;
    if (ev.frame) seen = await perceive(env, req, m, scene, run_id, ev.robot, ev.frame).catch(e => { perception_error = e.message; return null; });
    const safety = ev.kind === 'safety' || (seen && (seen.person_present || seen.recommended_action === 'escalate'));
    const ctx = `Site: ${sc.site}. Robot ${ev.robot} (${ev.device || 'robot'}) at ${ev.where}. ${ev.text}` + (seen ? `\nPerception (Cosmos): ${JSON.stringify(seen)}` : perception_error ? '\nPerception unavailable for this frame; camera content is unknown.' : '');
    // ARCHITECTURE.md: an unknown hazard class always escalates. A hazard is unknown when this run has no live precedent yet.
    const hazard = ev.kind === 'first_sighting' || !!(seen && (seen.hazards || []).length);
    const known = hazard && await env.MEMORY.prepare('SELECT 1 FROM precedents WHERE scene = ? AND run_id = ? AND (expires_at IS NULL OR expires_at > ?) LIMIT 1').bind(scene, run_id, now()).first();
    const novel = hazard && !known;
    let tier = safety || novel ? 'ultra' : 'nano', out = await decide(env, m, scene, run_id, ev.robot, ev.kind, tier, ctx);
    if (tier === 'nano' && (!out.decision || out.decision.confidence < tau)) { tier = 'ultra'; out = await decide(env, m, scene, run_id, ev.robot, ev.kind, 'ultra', ctx); }
    if (!out.decision) {  // invalid twice → safe stop (HANDOFF/ARCHITECTURE safety invariant)
      await env.TAGS.put(`${scene}:halt:${ev.robot}`, JSON.stringify({ by: 'safe_stop', run_id, at: now() }), { expirationTtl: 3600 });
      await action(env, scene, 'safe_stop', { robot: ev.robot, reason: 'no valid FleetAction after retry' }, tier, run_id);
    } else {
      await action(env, scene, 'decision', out.decision, tier, run_id);
      if (tier === 'ultra') await env.MEMORY.prepare('INSERT INTO precedents (id, scene, situation, decision_json, source, model, confidence, hops, safety, run_id, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)')
        .bind(uid('pr'), scene, ctx.slice(0, 1000), JSON.stringify(out.decision), 'ultra', out.model, out.decision.confidence, 0, safety ? 1 : 0, run_id, new Date(Date.now() + 86400e3).toISOString()).run();
      await applyZones(env, scene, out.decision, tier, run_id);
    }
    if (safety) await alarm(env, scene, 'crit', `${seen?.person_present ? 'Person' : 'Safety event'} near ${ev.robot} · ${ev.where}`, out.decision ? `Ultra: ${out.decision.actions.map(a => a.type).join(', ')} · ${out.decision.rationale || ''}` : 'no valid decision after retry → safe stop', run_id);
    else if (seen && (seen.hazards || []).length) await alarm(env, scene, 'warn', `${seen.hazards[0].type} seen by ${ev.robot} · ${ev.where}`, seen.scene || '', run_id);
    else if (novel) await alarm(env, scene, 'warn', `Unknown hazard reported by ${ev.robot} · ${ev.where}`, out.decision ? `Ultra: ${out.decision.actions.map(a => a.type).join(', ')}` : 'no valid decision → safe stop', run_id);
    return J({ t: ev.t, robot: ev.robot, tau, tier, gate: safety ? 'safety' : novel ? 'novel' : tier === 'ultra' ? 'low_confidence' : 'settled', perception: seen, perception_error, decision: out.decision, errors: out.errors, model: out.model, latency_ms: out.latency_ms });
  },
  'POST scenario/finish': async (env, req, url, body) => {
    const t = await env.MEMORY.prepare('SELECT tier, COUNT(*) n FROM calls WHERE run_id = ? GROUP BY tier').bind(body.run_id).all();
    await env.MEMORY.prepare('UPDATE runs SET finished_at = ?, totals_json = ? WHERE id = ?').bind(now(), JSON.stringify(t.results), body.run_id).run();
    return J({ ok: true, totals: t.results });
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
      const out = await chat(env, m.base, m.deliberator, [{ role: 'system', content: 'You audit a robot reflex model. Reply with only JSON {"agree": boolean, "better_action": string|null, "reason": "one sentence"}.' },
        { role: 'user', content: `Robot ${r.robot}, event ${r.event}. Reflex decision: ${r.decision_json}. Would you have made the same decision?` }], 300);
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
