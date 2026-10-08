// Switch the perception model (camera frame -> hazard JSON) between the options in config/models.yaml.
//   node tools/use_perception.cjs                      list options and the active one
//   node tools/use_perception.cjs cosmos               real image call to Cosmos; switches only if it answers with valid JSON
//   node tools/use_perception.cjs gemma4 --base https://<endpoint>/v1   set the option's endpoint (Gemma 4 on a Nebius Serverless Endpoint;
//                                                    its token goes in .env as GEMMA4_ENDPOINT_TOKEN and as a Pages secret of the same name)
//   --id <model> sets the option's model id
//   add --force to switch without the test call
// Then: node site/build.cjs && node tests/qa.cjs && npx wrangler pages deploy site/dist --project-name nemofleet
const fs = require('fs');
const path = require('path');
const { ROOT, env, models, perceptionOptions, setPerception, request, parseJSON } = require('./tf.cjs');
const MODELS_FILE = path.join(ROOT, 'config', 'models.yaml');

(async () => {
  const [name] = process.argv.slice(2).filter(a => !a.startsWith('--') && !['--id', '--base'].includes(process.argv[process.argv.indexOf(a) - 1]));
  const flag = f => process.argv.includes(f) ? process.argv[process.argv.indexOf(f) + 1] : null, idArg = flag('--id'), baseArg = flag('--base');
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
  if (baseArg) {
    const y = fs.readFileSync(MODELS_FILE, 'utf8'), re = new RegExp(`(\\n      ${name}:\\n(?:        [^\\n]*\\n)*?        base_url:\\s*)\\S+`);
    if (!re.test(y)) { console.log(`✗ ${name} has no base_url line in config/models.yaml`); process.exit(2); }
    fs.writeFileSync(MODELS_FILE, y.replace(re, `$1${baseArg.replace(/\/$/, '')}`));
    opts = perceptionOptions(); console.log(`✓ ${name}.base_url = ${opts[name].base_url}`);
  }
  const o = opts[name];
  if (!o.id) { console.log(`✗ ${name} has no model id yet. Pass --id <model>.`); process.exit(2); }
  if (!process.argv.includes('--force')) {
    if (o.base_url === null && 'base_url' in o) { console.log(`✗ ${name} has no endpoint yet. Pass --base https://<endpoint>/v1.`); process.exit(2); }
    const keyEnv = o.api_key_env || 'NEBIUS_API_KEY', key = env(keyEnv); if (!key) { console.log(`✗ ${keyEnv} missing from .env`); process.exit(2); }
    const frame = path.join(ROOT, 'site', 'assets', 'scenes', 'warehouse', 'frames', 'cam-r03-person.jpg');
    const img = 'data:image/jpeg;base64,' + fs.readFileSync(frame).toString('base64');
    // same output contract as perceive() in functions/api/[[path]].js
    const prompt = 'Analyze this robot camera frame for the planner. Return JSON with keys "scene" (one sentence), "hazards" (array of {"type","description","severity"}), "person_present" (boolean), "path_clear" (boolean), "recommended_action" ("proceed"|"slow"|"reroute"|"halt"|"escalate"), "confidence" (0-1).';
    const r = await request('POST', `${o.base_url || m.base}/chat/completions`, key, { model: o.id, temperature: 0.2, max_tokens: 700,
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
