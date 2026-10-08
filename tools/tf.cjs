// Minimal Nebius Token Factory client shared by the tools (OpenAI-compatible chat completions).
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const MODELS_FILE = path.join(ROOT, 'config', 'models.yaml');

function env(name) {
  if (process.env[name]) return process.env[name];
  const f = path.join(ROOT, '.env');
  const m = fs.existsSync(f) && fs.readFileSync(f, 'utf8').match(new RegExp(`^${name}=(.+)$`, 'm'));
  return m ? m[1].trim() : null;
}

// Reads ids from config/models.yaml: models.<role>.id, plus the active perception option.
function models() {
  const y = fs.readFileSync(MODELS_FILE, 'utf8');
  const out = { base: y.match(/base_url:\s*(\S+)/)[1] };
  for (const [, role, id] of y.matchAll(/\n  (\w+):\s*(?:#[^\n]*)?\n\s+id:\s*(\S+)/g)) out[role] = id === 'null' ? null : id;
  const p = perceptionOptions(y), active = y.match(/\n    active:\s*(\w+)/)?.[1], opt = p[active] || {};
  Object.assign(out, { perception: opt.id || null, perception_option: active || null, perception_label: opt.label || null, perception_billing: opt.billing || null,
    perception_base: opt.base_url || out.base, perception_key_env: opt.api_key_env || 'NEBIUS_API_KEY',
    perception_options: Object.fromEntries(Object.entries(p).map(([k, o]) => [k, { id: o.id || null, label: o.label || k }])) });
  return out;
}
// models.perception.options.<name>.{id,label,billing,...}
function perceptionOptions(y = fs.readFileSync(MODELS_FILE, 'utf8')) {
  const block = (y.match(/\n    options:\n([\s\S]*?)(?=\n  \w|\n\n  \w|$)/) || [])[1] || '', out = {};
  for (const [, name, body] of block.matchAll(/^      (\w+):\n((?:        [^\n]*\n?)*)/gm))
    out[name] = Object.fromEntries([...body.matchAll(/^        (\w+):\s*(.*?)\s*(?:#.*)?$/gm)].map(([, k, v]) => [k, v === 'null' ? null : v]));
  return out;
}
function setPerception(name) {
  const y = fs.readFileSync(MODELS_FILE, 'utf8');
  fs.writeFileSync(MODELS_FILE, y.replace(/(\n    active:\s*)\w+/, `$1${name}`));
}
function setModelId(role, id) {
  const y = fs.readFileSync(MODELS_FILE, 'utf8');
  const re = new RegExp(`(\\n  ${role}:[^\\n]*\\n\\s+id:\\s*)\\S+`);
  fs.writeFileSync(MODELS_FILE, y.replace(re, `$1${id}`));
}

async function request(method, url, key, body) {
  const t0 = Date.now();
  const r = await fetch(url, { method, headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const latency_ms = Date.now() - t0;
  const json = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, latency_ms, json };
}

async function chat(key, base, model, messages, opts = {}) {
  const res = await request('POST', `${base}/chat/completions`, key, { model, messages, temperature: 0.2, max_tokens: 800, ...opts });
  if (!res.ok) throw new Error(`${model}: HTTP ${res.status} ${JSON.stringify(res.json).slice(0, 300)}`);
  return { latency_ms: res.latency_ms, usage: res.json.usage || null, content: res.json.choices?.[0]?.message?.content ?? '' };
}

function parseJSON(text) {
  const t = String(text).replace(/<think>[\s\S]*?<\/think>/g, '').replace(/```(?:json)?/g, '');
  const a = t.indexOf('{'), b = t.lastIndexOf('}');
  if (a < 0 || b < a) return null;
  try { return JSON.parse(t.slice(a, b + 1)); } catch { return null; }
}

module.exports = { ROOT, env, models, perceptionOptions, setPerception, setModelId, request, chat, parseJSON };
