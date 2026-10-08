// Switch the perception model (camera frame -> hazard JSON) between the options in config/models.yaml.
//   node tools/use_perception.cjs                      list options and the active one
//   node tools/use_perception.cjs cosmos               real image call to Cosmos; switches only if it answers with valid JSON
//   node tools/use_perception.cjs gemma4 --id <model>  set the option's model id first (e.g. when Gemma 4 lands on Token Factory)
//   add --force to switch without the test call
// Then: node site/build.cjs && node tests/qa.cjs && npx wrangler pages deploy site/dist --project-name nemofleet
const fs = require('fs');
const path = require('path');
const { ROOT, env, models, perceptionOptions, setPerception, request, parseJSON } = require('./tf.cjs');
const MODELS_FILE = path.join(ROOT, 'config', 'models.yaml');

(async () => {
  const [name] = process.argv.slice(2).filter(a => !a.startsWith('--') && process.argv[process.argv.indexOf(a) - 1] !== '--id');
  const idArg = process.argv.includes('--id') ? process.argv[process.argv.indexOf('--id') + 1] : null;
  let opts = perceptionOptions(), m = models();
  if (!name) {
    for (const [k, o] of Object.entries(opts)) console.log(`${k === m.perception_option ? '*' : ' '} ${k.padEnd(8)} ${String(o.id).padEnd(50)} ${o.label} · ${o.billing || ''}`);
    return;
  }
  if (!opts[name]) { console.log(`✗ no option "${name}". Options: ${Object.keys(opts).join(', ')}`); process.exit(2); }
  if (idArg) {
    const y = fs.readFileSync(MODELS_FILE, 'utf8');
    fs.writeFileSync(MODELS_FILE, y.replace(new RegExp(`(\\n      ${name}:\\n        id:\\s*)\\S+`), `$1${idArg}`));
    opts = perceptionOptions(); console.log(`✓ ${name}.id = ${opts[name].id}`);
  }
  const o = opts[name];
  if (!o.id) { console.log(`✗ ${name} has no model id yet. Pass --id <model>.`); process.exit(2); }
  if (!process.argv.includes('--force')) {
    const key = env('NEBIUS_API_KEY'); if (!key) { console.log('✗ NEBIUS_API_KEY missing'); process.exit(2); }
    const frame = path.join(ROOT, 'site', 'assets', 'scenes', 'warehouse', 'frames', 'cam-r03-person.jpg');
    const img = 'data:image/jpeg;base64,' + fs.readFileSync(frame).toString('base64');
    // same output contract as perceive() in functions/api/[[path]].js
    const prompt = 'Analyze this robot camera frame for the planner. Return JSON with keys "scene" (one sentence), "hazards" (array of {"type","description","severity"}), "person_present" (boolean), "path_clear" (boolean), "recommended_action" ("proceed"|"slow"|"reroute"|"halt"|"escalate"), "confidence" (0-1).';
    const r = await request('POST', `${m.base}/chat/completions`, key, { model: o.id, temperature: 0.2, max_tokens: 700,
      messages: [{ role: 'user', content: [{ type: 'image_url', image_url: { url: img } }, { type: 'text', text: prompt }] }] });
    const out = parseJSON(r.json.choices?.[0]?.message?.content || '');
    if (!r.ok || !out) { console.log(`✗ ${o.label} did not answer with valid JSON (HTTP ${r.status}): ${JSON.stringify(r.json).slice(0, 240)}\n  Not switched.`); process.exit(1); }
    console.log(`✓ ${o.label} answered in ${r.latency_ms} ms: person_present=${out.person_present} action=${out.recommended_action} hazards=${(out.hazards || []).map(h => h.type).join(', ') || 'none'}`);
  }
  setPerception(name);
  m = models();
  console.log(`✓ perception is now ${m.perception_label} (${m.perception})\n  Next: node site/build.cjs && node tests/qa.cjs && npx wrangler pages deploy site/dist --project-name nemofleet`);
  if (name === 'cosmos') console.log('! Cosmos bills about $0.37/min while its dedicated endpoint runs. Stop it when you are done.');
})().catch(e => { console.error(e); process.exit(1); });
