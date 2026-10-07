// Send robot camera frames to Cosmos3 Super Reasoner on Nebius Token Factory and store real results.
//   node tools/cosmos_perceive.cjs            (all frames in site/assets/frames)
//   node tools/cosmos_perceive.cjs cam-r14-leak
// Needs NEBIUS_API_KEY in the environment or the repo .env, and the dedicated endpoint in the Ready state.
// Writes site/assets/perception/<frame>.json and index.json. Nothing is written for a failed call.
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const FRAMES = path.join(ROOT, 'site', 'assets', 'frames');
const OUT = path.join(ROOT, 'site', 'assets', 'perception');

function env(name) {
  if (process.env[name]) return process.env[name];
  const f = path.join(ROOT, '.env');
  const m = fs.existsSync(f) && fs.readFileSync(f, 'utf8').match(new RegExp(`^${name}=(.+)$`, 'm'));
  return m ? m[1].trim() : null;
}
const yaml = fs.readFileSync(path.join(ROOT, 'config', 'models.yaml'), 'utf8');
const BASE = yaml.match(/base_url:\s*(\S+)/)[1];
const MODEL = yaml.match(/perception:\s*\n\s*id:\s*(\S+)/)[1];

const ROBOTS = { 'cam-r14-leak': ['R14', 'cold aisle 2 · row end'], 'cam-r03-person': ['R03', 'cold aisle 2 · zone C2'],
  'cam-r12-cart': ['R12', 'cold aisle 2 · row end (Day 2)'], 'cam-r07-clear': ['R07', 'cold aisle 1'] };

const SYSTEM = 'You are the perception module of an autonomous rack-service robot in a hyperscale data center hall. ' +
  'You see one frame from the robot\'s forward camera. Report only what is visible. Answer with a single JSON object and nothing else.';
const USER = 'Analyze this frame for the robot\'s planner. Return JSON with exactly these keys: ' +
  '"scene" (one short sentence), "hazards" (array of {"type": "liquid_leak"|"person"|"cart"|"obstruction"|"open_rack_door"|"other", "description": string, "severity": "low"|"medium"|"high"|"critical"}), ' +
  '"person_present" (boolean), "path_clear" (boolean), "recommended_action" ("proceed"|"slow"|"reroute"|"halt"|"escalate"), "confidence" (number 0-1). ' +
  'A person in the robot\'s lane always means "escalate".';

function parseJSON(text) {
  const t = text.replace(/```(?:json)?/g, '');
  const a = t.indexOf('{'), b = t.lastIndexOf('}');
  if (a < 0 || b < a) return null;
  try { return JSON.parse(t.slice(a, b + 1)); } catch { return null; }
}

async function perceive(name, key) {
  const img = fs.readFileSync(path.join(FRAMES, name + '.jpg')).toString('base64');
  const body = { model: MODEL, temperature: 0.2, max_tokens: 700, messages: [
    { role: 'system', content: SYSTEM },
    { role: 'user', content: [{ type: 'image_url', image_url: { url: `data:image/jpeg;base64,${img}` } }, { type: 'text', text: USER }] }] };
  const t0 = Date.now();
  const r = await fetch(`${BASE}/chat/completions`, { method: 'POST', headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const latency = Date.now() - t0;
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status} ${JSON.stringify(j).slice(0, 300)}`);
  const raw = j.choices?.[0]?.message?.content ?? '';
  const [robot, where] = ROBOTS[name] || [name, ''];
  return { frame: `assets/frames/${name}.jpg`, name, robot, where, model: MODEL, endpoint: BASE, called_at: new Date().toISOString(),
    latency_ms: latency, usage: j.usage || null, result: parseJSON(raw), raw };
}

(async () => {
  const key = env('NEBIUS_API_KEY');
  if (!key) { console.error('NEBIUS_API_KEY is not set (environment or .env). No calls made.'); process.exit(2); }
  fs.mkdirSync(OUT, { recursive: true });
  const names = process.argv.slice(2).length ? process.argv.slice(2) : fs.readdirSync(FRAMES).filter(f => f.endsWith('.jpg')).map(f => f.replace(/\.jpg$/, ''));
  const indexFile = path.join(OUT, 'index.json');
  const index = fs.existsSync(indexFile) ? JSON.parse(fs.readFileSync(indexFile, 'utf8')) : { results: {} };
  let failed = 0;
  for (const n of names) {
    try {
      const res = await perceive(n, key);
      fs.writeFileSync(path.join(OUT, n + '.json'), JSON.stringify(res, null, 2));
      index.results[n] = { robot: res.robot, where: res.where, frame: res.frame, latency_ms: res.latency_ms, called_at: res.called_at, result: res.result };
      console.log(`${n}: ${res.latency_ms} ms · ${res.result ? res.result.recommended_action + ' · ' + res.result.scene : 'unparsed response, see raw'}`);
    } catch (e) { failed++; console.error(e.message); }
  }
  index.model = MODEL; index.updated_at = new Date().toISOString();
  fs.writeFileSync(indexFile, JSON.stringify(index, null, 2));
  process.exit(failed ? 1 : 0);
})();
