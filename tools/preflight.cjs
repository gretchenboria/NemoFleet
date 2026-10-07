// Preflight for a real run on Nebius: key, model catalog, model ids, Cosmos endpoint readiness.
//   node tools/preflight.cjs            (reads only; prints what it would set)
//   node tools/preflight.cjs --write    (also writes the chosen ids into config/models.yaml)
const { env, models, setModelId, request, chat } = require('./tf.cjs');

const PICK = {
  deliberator: [/nemotron[-_]?3[-_]?ultra/i, /nemotron.*ultra/i],
  reflex: [/nemotron[-_]?3[-_]?nano(?!.*(omni|vl))/i, /nemotron.*nano(?!.*(omni|vl))/i],
  scenario_generator: [/nemotron[-_]?3[-_]?super/i, /nemotron.*super/i],
};

(async () => {
  const write = process.argv.includes('--write');
  const key = env('NEBIUS_API_KEY');
  if (!key) { console.log('✗ NEBIUS_API_KEY missing. Add it to .env (gitignored):  NEBIUS_API_KEY=...'); process.exit(2); }
  const m = models();
  console.log(`✓ key present · base ${m.base}`);

  const cat = await request('GET', `${m.base}/models`, key);
  if (!cat.ok) { console.log(`✗ GET /models → HTTP ${cat.status}: ${JSON.stringify(cat.json).slice(0, 200)}`); process.exit(1); }
  const ids = (cat.json.data || []).map(d => d.id);
  console.log(`✓ catalog: ${ids.length} models (${cat.latency_ms} ms)`);
  ids.filter(i => /nemotron|cosmos/i.test(i)).forEach(i => console.log('   ·', i));

  for (const [role, patterns] of Object.entries(PICK)) {
    const found = patterns.map(p => ids.filter(i => p.test(i))).find(a => a.length) || [];
    const choice = m[role] && ids.includes(m[role]) ? m[role] : found[0];
    console.log(`${choice ? '✓' : '✗'} ${role}: ${choice || 'no matching model in catalog'}${found.length > 1 ? `  (also: ${found.slice(1).join(', ')})` : ''}`);
    if (choice && write && choice !== m[role]) { setModelId(role, choice); console.log(`   written to config/models.yaml`); }
  }

  if (m.perception) {
    try {
      const r = await chat(key, m.base, m.perception, [{ role: 'user', content: 'Reply with the single word: ready' }], { max_tokens: 5 });
      console.log(`✓ Cosmos endpoint answers (${r.latency_ms} ms): ${r.content.trim().slice(0, 40)}`);
    } catch (e) { console.log(`✗ Cosmos endpoint not ready: ${e.message.slice(0, 200)}\n   Start it in the Token Factory console, wait for Ready, then re-run.`); }
    console.log('! Cosmos dedicated endpoint bills about $0.37/min while running. Stop it when the run is done.');
  }
})().catch(e => { console.error(e); process.exit(1); });
