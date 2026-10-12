// NemoFleet QA suite: repo hygiene, build, links, and browser checks of the static site.
//   node tests/qa.cjs        (exit code 0 only if every check passes)
// Needs Google Chrome and docs/video/node_modules (puppeteer-core, marked).
const fs = require('fs');
const path = require('path');
const http = require('http');
const vm = require('vm');
const { execFileSync, spawn } = require('child_process');
const os = require('os');
const ROOT = path.join(__dirname, '..');
const DIST = path.join(ROOT, 'site', 'dist');
const puppeteer = require(path.join(ROOT, 'docs', 'video', 'node_modules', 'puppeteer-core'));
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const results = [];
function check(name, ok, detail = '') { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail && !ok ? `  →  ${detail}` : ''}`); }
const walk = d => fs.readdirSync(d, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);

// ---------- 1. repo hygiene ----------
const tracked = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], { cwd: ROOT }).toString().trim().split('\n').filter(Boolean);
check('.env is not tracked or about to be committed', !tracked.includes('.env'));
let envIgnored = true; try { execFileSync('git', ['check-ignore', '-q', '.env'], { cwd: ROOT }); } catch { envIgnored = false; }
check('.env is gitignored', envIgnored);

const siteAssets = walk(path.join(ROOT, 'site', 'assets')).map(f => path.relative(ROOT, f));
const untrackedAssets = siteAssets.filter(f => !tracked.includes(f));
check('every site asset is committed or staged (none blocked by .gitignore)', untrackedAssets.length === 0, untrackedAssets.join(', '));
const secrets = fs.existsSync(path.join(ROOT, '.env'))
  ? fs.readFileSync(path.join(ROOT, '.env'), 'utf8').split('\n').map(l => l.split('=').slice(1).join('=').trim()).filter(v => v.length >= 16 && !/^https?:/.test(v))
  : [];
function scanForSecrets(files, label) {
  const hits = [];
  for (const f of files) {
    if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) continue;
    const buf = fs.readFileSync(f);
    for (const s of secrets) if (buf.includes(s)) hits.push(path.relative(ROOT, f));
    const txt = /\.(md|js|cjs|json|ya?ml|html|css|py|txt|toml)$/i.test(f) ? buf.toString('utf8') : '';
    if (/AIza[0-9A-Za-z_-]{35}|AQ\.[A-Za-z0-9_-]{30,}|cfat_[A-Za-z0-9]{30,}|v1\.CmMK[A-Za-z0-9_.-]{20,}/.test(txt)) hits.push(path.relative(ROOT, f) + ' (pattern)');
  }
  check(`no secrets in ${label} (${secrets.length} .env values + key patterns)`, hits.length === 0, [...new Set(hits)].join(', '));
}
scanForSecrets(tracked.map(f => path.join(ROOT, f)), 'git-tracked files');

// ---------- 2. code checks ----------
for (const f of ['site/assets/anim.js', 'site/build.cjs', 'docs/build_doc_pdfs.cjs', 'docs/video/make_video.js', 'tools/cosmos_perceive.cjs', 'tools/tf.cjs', 'tools/preflight.cjs', 'tools/use_perception.cjs', 'tools/run_scenario.cjs', 'tools/night_shift/distill.cjs', 'tests/qa.cjs']) {
  try { new vm.Script(fs.readFileSync(path.join(ROOT, f), 'utf8').replace(/^#!.*/, ''), { filename: f }); check(`JS parses: ${f}`, true); }
  catch (e) { check(`JS parses: ${f}`, false, e.message); }
}
try { new vm.Script(fs.readFileSync(path.join(ROOT, 'functions/api/[[path]].js'), 'utf8').replace(/^export /m, ''), { filename: 'api' }); check('JS parses: functions/api/[[path]].js', true); }
catch (e) { check('JS parses: functions/api/[[path]].js', false, e.message); }
check('wrangler.jsonc binds MEMORY (D1), TAGS (KV), RUNS (R2) and publishes site/dist', (() => { const w = fs.readFileSync(path.join(ROOT, 'wrangler.jsonc'), 'utf8'); return /"MEMORY"/.test(w) && /"TAGS"/.test(w) && /"RUNS"/.test(w) && /"site\/dist"/.test(w); })());
for (const f of ['docs/build_architecture_pdf.py', 'docs/build_countercurrent_pdf.py', 'tools/ego_mix/adapt_bag.py', 'tools/ego_mix/adapt_magni.py', 'tools/ego_mix/baseline.py', 'tools/ego_mix/adapt_waymo.py', 'tools/ego_mix/train.py', 'tools/ego_mix/score.py', 'tools/ego_mix/headroom.py', 'tools/ego_mix/adapt_smartspaces.py']) {
  try { execFileSync('python3', ['-c', `import ast,sys; ast.parse(open(sys.argv[1]).read())`, path.join(ROOT, f)]); check(`Python parses: ${f}`, true); }
  catch (e) { check(`Python parses: ${f}`, false, String(e.stderr || e.message).slice(0, 200)); }
}
try { execFileSync('python3', [path.join(ROOT, 'tools/ego_mix/selftest.py')]); check('ego_mix: label, JRDB adapter and place-level split pass the selftest', true); }
catch (e) { check('ego_mix: label, JRDB adapter and place-level split pass the selftest', false, String(e.stderr || e.message).slice(-200)); }
for (const [scene, names] of [['warehouse', ['cam-r14-spill', 'cam-r03-person', 'cam-r12-forklift', 'cam-r07-clear']], ['datacenter', ['cam-r14-leak', 'cam-r03-person', 'cam-r12-cart', 'cam-r07-clear']]]) {
  const dir = path.join(ROOT, 'site', 'assets', 'scenes', scene);
  const missing = names.filter(f => !fs.existsSync(path.join(dir, 'frames', f + '.jpg')));
  check(`${scene}: floor render and 4 robot camera frames present`, !missing.length && fs.existsSync(path.join(dir, 'floor.jpg')), missing.join(', '));
  const pdir = path.join(ROOT, 'site', 'assets', 'perception', scene), perc = JSON.parse(fs.readFileSync(path.join(pdir, 'index.json'), 'utf8'));
  const fakes = Object.keys(perc.results || {}).filter(n => { const f = path.join(pdir, n + '.json'); return !fs.existsSync(f) || !JSON.parse(fs.readFileSync(f, 'utf8')).raw; });
  check(`${scene}: every Cosmos result shown has a stored raw response from a real call`, !fakes.length, fakes.join(', '));
}
for (const scen of ['aisle4-spill', 'hall-b-coolant-leak']) {
  try {
    const outDry = execFileSync('node', [path.join(ROOT, 'tools', 'run_scenario.cjs'), path.join(ROOT, 'scenarios', scen + '.json'), '--dry-run'], { cwd: ROOT }).toString();
    const runDir = outDry.match(/→ (\S+)\/summary\.json/)[1];
    const sum = JSON.parse(fs.readFileSync(path.join(ROOT, runDir, 'summary.json'), 'utf8'));
    fs.rmSync(path.join(ROOT, runDir), { recursive: true, force: true });
    const safety = sum.results.find(r => r.robot === 'R03');
    check(`${scen} dry run: 7 events, person event routed to Ultra, handshakes make no model calls`, sum.totals.events === 7 && safety.tier === 'ultra' && sum.totals.peer === 2 && sum.totals.model_calls === 0, JSON.stringify(sum.totals));
  } catch (e) { check(`${scen} dry run`, false, String(e.message).slice(0, 200)); }
}
const models = fs.readFileSync(path.join(ROOT, 'config', 'models.yaml'), 'utf8');
check('models.yaml names the Token Factory base URL and Cosmos endpoint', /base_url: https:\/\/api\.tokenfactory\./.test(models) && /Cosmos3-Super-Reasoner/.test(models));

// ---------- 3. build ----------
let built = true;
try { execFileSync('node', [path.join(ROOT, 'site', 'build.cjs')], { cwd: ROOT, stdio: 'pipe' }); } catch (e) { built = false; check('site builds', false, String(e.stderr).slice(0, 300)); }
if (built) check('site builds', true);
const pages = ['index.html', 'console.html', 'video.html', 'docs.html'];
pages.forEach(p => check(`page exists: ${p}`, fs.existsSync(path.join(DIST, p))));
for (const f of fs.readdirSync(path.join(DIST, 'docs'))) {
  const b = fs.readFileSync(path.join(DIST, 'docs', f));
  check(`valid PDF: docs/${f}`, b.slice(0, 5).toString() === '%PDF-' && b.length > 20000);
}
{ const rd = JSON.parse(fs.readFileSync(path.join(DIST, 'assets', 'scenes', 'sanfrancisco', 'roads.json'), 'utf8'));
  check('sanfrancisco (experimental): road graph from OpenStreetMap with anchors', rd.nodes.length > 300 && rd.edges.length > 500 && rd.meta.zone.length > 2 && rd.meta.hazard && rd.meta.person && /OpenStreetMap/.test(rd.meta.attribution), `${rd.nodes.length} nodes ${rd.edges.length} edges`); }
check('build publishes scenarios and the model registry for the API', fs.existsSync(path.join(DIST, 'scenarios', 'hall-b-coolant-leak.json')) && fs.existsSync(path.join(DIST, 'scenarios', 'aisle4-spill.json')) && !!JSON.parse(fs.readFileSync(path.join(DIST, 'config', 'models.json'), 'utf8')).deliberator);
const mp4 = path.join(DIST, 'assets', 'nemofleet-explainer.mp4');
check('video under the 25 MB Pages file limit', fs.existsSync(mp4) && fs.statSync(mp4).size < 25 * 1024 * 1024);
const tooBig = walk(DIST).filter(f => fs.statSync(f).size >= 25 * 1024 * 1024);
check('no built file reaches 25 MB', tooBig.length === 0, tooBig.join(', '));
scanForSecrets(walk(DIST), 'built site');

// ---------- 4. links ----------
const broken = [];
for (const p of pages) {
  const html = fs.readFileSync(path.join(DIST, p), 'utf8');
  for (const [, url] of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
    if (/^(https?:|data:|mailto:|#)/.test(url) || url.includes('${')) continue;
    const rel = url.split('#')[0].split('?')[0];
    if (rel && !fs.existsSync(path.join(DIST, rel))) broken.push(`${p} → ${url}`);
  }
  const css = fs.readFileSync(path.join(DIST, 'assets', 'site.css'), 'utf8');
  for (const [, u] of css.matchAll(/url\(([^)]+)\)/g)) if (!/^data:/.test(u) && !fs.existsSync(path.join(DIST, 'assets', u.replace(/["']/g, '')))) broken.push(`site.css → ${u}`);
}
check('all internal links and assets resolve', broken.length === 0, [...new Set(broken)].join('; '));

// ---------- 5. browser ----------
const TYPES = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.jpg': 'image/jpeg', '.png': 'image/png', '.pdf': 'application/pdf', '.mp4': 'video/mp4' };
const server = http.createServer((req, res) => {
  let f = path.join(DIST, decodeURIComponent(req.url.split('?')[0].split('#')[0]));
  if (f.endsWith('/')) f += 'index.html';
  if (!f.startsWith(DIST) || !fs.existsSync(f)) { res.writeHead(404); return res.end('not found'); }
  const stat = fs.statSync(f), type = TYPES[path.extname(f)] || 'application/octet-stream', range = req.headers.range;
  if (range) {
    const [rs, re] = range.replace('bytes=', '').split('-'), s = Number(rs), end = Math.min(re === '' ? stat.size - 1 : Number(re), stat.size - 1);
    if (isNaN(s) || s > end) { res.writeHead(416, { 'Content-Range': `bytes */${stat.size}` }); return res.end(); }
    res.writeHead(206, { 'Content-Type': type, 'Content-Range': `bytes ${s}-${end}/${stat.size}`, 'Accept-Ranges': 'bytes', 'Content-Length': end - s + 1 });
    return fs.createReadStream(f, { start: s, end }).pipe(res);
  }
  res.writeHead(200, { 'Content-Type': type, 'Content-Length': stat.size, 'Accept-Ranges': 'bytes' }); fs.createReadStream(f).pipe(res);
});

(async () => {
  await new Promise(r => server.listen(0, r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage();
  let errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const probe = u => /\/api\/health$/.test(u || '');  // the console's offline-detection probe; 404 on the static server is expected
  page.on('console', m => { if (m.type() === 'error' && !probe(m.location()?.url)) errors.push(m.text()); });
  page.on('requestfailed', r => { if (!/fonts\.g/.test(r.url()) && r.failure()?.errorText !== 'net::ERR_ABORTED') errors.push('request failed: ' + r.url()); });
  page.on('response', r => { if (r.status() >= 400 && !probe(r.url())) errors.push(`${r.status()} ${r.url()}`); });

  for (const p of pages) for (const [w, h] of [[390, 844], [768, 1024], [1440, 900]]) for (const scheme of ['light', 'dark']) {
    errors = [];
    await page.setViewport({ width: w, height: h });
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }, { name: 'prefers-reduced-motion', value: 'no-preference' }]);
    await page.goto(base + p, { waitUntil: 'domcontentloaded' });
    await new Promise(r => setTimeout(r, 400));
    const info = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth > window.innerWidth + 1, title: document.title, lang: document.documentElement.lang,
      headings: document.querySelectorAll('h1, h2').length, bodyBg: getComputedStyle(document.body).backgroundColor }));
    check(`${p} @${w}px ${scheme}: no errors, no overflow`, !errors.length && !info.overflow, [...errors, info.overflow ? 'horizontal overflow' : ''].filter(Boolean).join('; '));
    if (w === 1440 && scheme === 'light') check(`${p}: title, lang, headings, explicit background`, info.title && info.lang === 'en' && info.headings > 0 && info.bodyBg !== 'rgba(0, 0, 0, 0)', JSON.stringify(info));
  }

  // animations draw something, with and without reduced motion
  for (const motion of ['no-preference', 'reduce']) {
    errors = [];
    await page.setViewport({ width: 1440, height: 900 });
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }, { name: 'prefers-reduced-motion', value: motion }]);
    await page.goto(base + 'index.html', { waitUntil: 'load' });
    await new Promise(r => setTimeout(r, 1800));
    const drawn = await page.evaluate(() => ['anim-antennation', 'anim-countercurrent'].map(id => {
      const c = document.getElementById(id), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, seen = new Set();
      for (let i = 0; i < d.length; i += 4 * 97) seen.add(d[i] >> 4 << 8 | d[i + 1] >> 4 << 4 | d[i + 2] >> 4);
      return { id, colors: seen.size, label: !!c.getAttribute('aria-label') };
    }));
    drawn.forEach(d => check(`animation ${d.id} draws (${motion} motion) and has a text alternative`, d.colors > 6 && d.label && !errors.length, JSON.stringify(d) + errors.join(';')));
  }

  // video loads and chapters seek
  await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'no-preference' }]);
  await page.goto(base + 'video.html', { waitUntil: 'domcontentloaded' });
  const dur = await page.evaluate(() => new Promise(res => { const v = document.getElementById('vid'); if (v.readyState >= 1) return res(v.duration); v.addEventListener('loadedmetadata', () => res(v.duration)); setTimeout(() => res(-1), 8000); }));
  check('explainer video loads metadata (about 3 min)', dur > 150 && dur < 260, `duration ${dur}`);
  await page.click('[data-t="125"]'); await new Promise(r => setTimeout(r, 300));
  const ct = await page.evaluate(() => document.getElementById('vid').currentTime);
  check('chapter link seeks the video', Math.abs(ct - 125) < 2, `currentTime ${ct}`);

  // console interactions
  for (const sc of ['warehouse', 'datacenter', 'sanfrancisco']) {
    errors = [];
    await page.goto(base + 'console.html#' + sc, { waitUntil: 'domcontentloaded' }); await new Promise(r => setTimeout(r, 900));
    const st = await page.evaluate(() => ({ pressed: document.querySelector('.scene-switch [aria-pressed="true"]')?.dataset.scene, imgs: [...document.querySelectorAll('#cams img')].map(i => i.complete && i.naturalWidth > 0), alarm: document.querySelector('.alarm .t')?.textContent }));
    check(`console #${sc}: scene selected, 4 camera frames load, no errors`, st.pressed === sc && st.imgs.length === 4 && st.imgs.every(Boolean) && !errors.length, JSON.stringify(st) + errors.join(';'));
  }
  await page.goto(base + 'console.html#warehouse', { waitUntil: 'load' });
  await page.click('#scene-datacenter');
  const sw = await page.evaluate(() => ({ hash: location.hash, site: document.getElementById('site-label').textContent }));
  check('console: scene switch changes the scene and the URL', sw.hash === '#datacenter' && /Hall B/.test(sw.site), JSON.stringify(sw));
  await new Promise(r => setTimeout(r, 800));
  const off = await page.evaluate(() => ({ mode: document.getElementById('mode').textContent, banner: !document.getElementById('banner').hidden, text: document.body.innerText,
    kpis: [...document.querySelectorAll('.kpi .v')].map(v => v.textContent) }));
  check('console offline: labelled "Offline" with a banner, and shows no numbers', off.mode === 'Offline' && off.banner && off.kpis.every(v => v === '—'), JSON.stringify({ mode: off.mode, kpis: off.kpis }));
  check('console: no "example only" text anywhere', !/example only/i.test(off.text));
  await page.click('#act-night'); await new Promise(r => setTimeout(r, 200));
  const toast = await page.evaluate(() => { const t = document.getElementById('toast'); return { shown: !t.hidden, text: t.textContent }; });
  check('console offline: buttons say they are not connected and link the live console', toast.shown && /Not connected/.test(toast.text) && /nemofleet\.pages\.dev/.test(toast.text), JSON.stringify(toast));

  // ---------- 6. live API + console against wrangler pages dev (local D1/KV/R2; no model calls) ----------
  const state = fs.mkdtempSync(path.join(os.tmpdir(), 'nf-qa-'));
  try {
    execFileSync('npx', ['wrangler', 'd1', 'migrations', 'apply', 'nemofleet-memory', '--local', '-c', 'cloudflare/wrangler.jsonc', '--persist-to', state], { cwd: ROOT, stdio: 'pipe' });
    // seed stored decisions, an event's call, perception and alarms straight into the local database (no model calls)
    const hour = 3600e3, iso = ms => new Date(Date.now() + ms).toISOString(), q = v => "'" + String(v).replace(/'/g, "''") + "'";
    const dj = JSON.stringify({ actions: [{ type: 'quarantine_zone', cells: ['QA1'], ttl_s: 600 }], confidence: 0.9, rationale: 'seeded' });
    const pre = (id, cell, exp, pinned, safety) => `INSERT INTO precedents (id, scene, situation, decision_json, source, model, confidence, safety, run_id, created_at, expires_at, hazard_key, pinned) VALUES (${q(id)}, 'datacenter', 'Site: QA. Robot R07 at cold aisle 3. Coolant on the floor.', ${q(dj)}, 'ultra', 'qa-ultra', 0.9, ${safety}, 'qa-run', ${q(iso(-hour))}, ${q(iso(exp))}, ${q(cell)}, ${pinned});`;
    const al = (id, cell, safety, extra) => `INSERT INTO alarms (id, scene, sev, title, meta, run_id, created_at, event_index, event_json, safety${extra ? ', call_id, perception_id, precedent_id, precedent_link' : ''}) VALUES (${q(id)}, 'datacenter', ${safety ? "'crit'" : "'warn'"}, ${q('QA alarm ' + cell)}, 'seeded', 'qa-run', ${q(iso(-hour))}, ${safety ? 2 : 1}, ${q(JSON.stringify({ robot: 'R07', where: 'cold aisle 3', text: 'Coolant on the floor.', cell, kind: safety ? 'safety' : 'first_sighting' }))}, ${safety}${extra || ''});`;
    fs.writeFileSync(path.join(state, 'seed.sql'), [
      `INSERT INTO runs (id, scenario, scene, started_at) VALUES ('qa-run', 'hall-b-coolant-leak', 'datacenter', ${q(iso(-hour))});`,
      pre('pr-qa-1', 'QA1', hour, 0, 0), pre('pr-qa-pin', 'QA3', -hour, 1, 0), pre('pr-qa-exp', 'QA4', -hour, 0, 0), pre('pr-qa-person', 'QA5', hour, 0, 1),
      `INSERT INTO calls (id, run_id, ts, tier, model, robot, event, latency_ms, valid, scene, decision_json) VALUES (9001, 'qa-run', ${q(iso(-hour))}, 'ultra', 'qa-ultra', 'R07', 'first_sighting', 1234, 1, 'datacenter', ${q(dj)});`,
      `INSERT INTO perception (id, scene, frame, robot, model, called_at, latency_ms, result_json) VALUES ('datacenter/qa/1', 'datacenter', 'qa', 'R07', 'qa-eyes', ${q(iso(-hour))}, 321, ${q(JSON.stringify({ scene: 'A puddle in the aisle.', hazards: [{ type: 'liquid_spill' }], person_present: false }))});`,
      `INSERT INTO actions (id, scene, type, payload_json, source, run_id, event_index) VALUES ('act-qa-1', 'datacenter', 'decision', ${q(dj)}, 'ultra', 'qa-run', 1), ('act-qa-2', 'datacenter', 'memory_hit', ${q(JSON.stringify({ precedent: 'pr-qa-1', cell: 'QA1' }))}, 'nano', 'qa-run', 3);`,
      al('al-qa-haz', 'QA1', 0, ", 9001, 'datacenter/qa/1', 'pr-qa-1', 'created'"), al('al-qa-person', 'QA2', 1, '')].join('\n'));
    execFileSync('npx', ['wrangler', 'd1', 'execute', 'nemofleet-memory', '--local', '-c', 'cloudflare/wrangler.jsonc', '--persist-to', state, '--file', path.join(state, 'seed.sql')], { cwd: ROOT, stdio: 'pipe' });
    const port = 8790 + Math.floor(Math.random() * 100);
    const dev = spawn('npx', ['wrangler', 'pages', 'dev', 'site/dist', '--d1', 'MEMORY=eb9d266f-5753-45da-9378-5797b5cf1fdc', '--kv', 'TAGS', '--r2', 'RUNS', '--port', String(port), '--persist-to', state], { cwd: ROOT, stdio: 'ignore', detached: true });
    const api = `http://127.0.0.1:${port}/api/`;
    const get = p => fetch(api + p).then(r => r.json()), post = (p, b) => fetch(api + p, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(b) }).then(r => r.json());
    let health = null;
    for (let i = 0; i < 60 && !health; i++) { await new Promise(r => setTimeout(r, 1000)); health = await get('health').catch(() => null); }
    try {
      check('API /api/health: d1, kv and r2 bound, model ids served', health && health.d1 && health.kv && health.r2 && health.models?.deliberator, JSON.stringify(health));
      await post('actions', { scene: 'datacenter', type: 'quarantine_zone', zone: 'C2' });
      let st = await get('state?scene=datacenter');
      check('API: quarantine writes a KV zone tag and raises an alarm', st.tags.some(t => t.name === 'datacenter:zone:C2') && st.alarms.some(a => /Zone C2 quarantined/.test(a.title)), JSON.stringify(st.tags));
      const al = st.alarms[0];
      await post('alarms/ack', { id: al.id }); st = await get('state?scene=datacenter');
      const acked = st.alarms.find(a => a.id === al.id)?.status;
      await post('alarms/ack', { id: al.id }); st = await get('state?scene=datacenter');
      check('API: alarm ack round-trip (open → acked → open)', acked === 'acked' && st.alarms.find(a => a.id === al.id)?.status === 'open', acked);
      const rel = await post('alarms/release', { id: al.id }); st = await get('state?scene=datacenter');
      check('API: release clears the alarm and its zone tags', rel.ok && !st.alarms.some(a => a.id === al.id) && !st.tags.some(t => t.name.includes(':zone:')), JSON.stringify(rel));
      const s0 = await post('scenario/start', { scene: 'datacenter' }), peer = await post('scenario/step', { scene: 'datacenter', run_id: s0.run_id, i: 2 });
      check('API: scenario start returns 7 events; a handshake step makes no model call', s0.events?.length === 7 && peer.tier === 'peer' && peer.model_calls === 0, JSON.stringify(peer));
      // events endpoint: a robot posts one event; the model-free paths run locally
      const evPost = await post('events', { scene: 'datacenter', robot: 'R09', device: 'AMR', where: 'cold aisle 3', cell: 'QA1', kind: 'peer_handshake', text: 'Passing R07 at the aisle end.', from: 'R07' });
      const evRun = await post('events', { scene: 'datacenter', robot: 'R09', where: 'cold aisle 3', kind: 'peer_handshake', text: 'Passing R07 again.', run_id: 'qa-run' });
      check('API events: a posted handshake event runs the shared pipeline with no model call, under the day\'s run or the one passed in', evPost.tier === 'peer' && evPost.model_calls === 0 && evPost.robot === 'R09' && /^events-datacenter-\d{4}-\d\d-\d\d$/.test(evPost.run_id) && /received precedent/.test(evPost.note) && evRun.run_id === 'qa-run' && evRun.tier === 'peer', JSON.stringify([evPost, evRun]).slice(0, 300));
      const evBad = await Promise.all([{ scene: 'moon', robot: 'R1', where: 'x', kind: 'routine', text: 'x' }, { scene: 'datacenter', where: 'x', kind: 'routine', text: 'x' }, { scene: 'datacenter', robot: 'R1', where: 'x', kind: 'teleport', text: 'x' }, { scene: 'datacenter', robot: 'R1', where: 'x', kind: 'routine', text: '' }]
        .map(b => fetch(api + 'events', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(b) }).then(async r => [r.status, (await r.json()).error])));
      check('API events: unknown scene, missing robot, unknown kind and empty text are rejected with 400', evBad.every(([st2, e]) => st2 === 400 && e) && /scene must be/.test(evBad[0][1]) && /"robot" is required/.test(evBad[1][1]) && /"kind" must be/.test(evBad[2][1]) && /"text" is required/.test(evBad[3][1]), JSON.stringify(evBad));
      // autonomy target: stored per scene, only measured levels, tau untouched
      const gate = JSON.parse(fs.readFileSync(path.join(ROOT, 'config', 'night_shift.json'), 'utf8')).distill.gate, lvl = gate.levels[gate.levels.length > 2 ? 2 : 0];
      const au0 = (await get('state?scene=datacenter')).autonomy, auSet = await post('actions', { scene: 'datacenter', type: 'set_autonomy', target_error: lvl.target_error }), stA = await get('state?scene=datacenter'), auBad = await post('actions', { scene: 'datacenter', type: 'set_autonomy', target_error: 0.5 });
      check('API autonomy: a measured target is stored per scene and returned in state; an unmeasured one is rejected; stated confidence and tau stay in force', au0?.target_error === null && auSet.ok && stA.autonomy.target_error === lvl.target_error && stA.autonomy.level.min_probability === lvl.min_probability && stA.autonomy.in_force === 'stated_confidence' &&
        stA.tau === stA.tau_default && /must be one of/.test(auBad.error || '') && (await get('state?scene=warehouse')).autonomy.target_error === null && stA.actions.some(a => a.type === 'set_autonomy' && a.source === 'operator'), JSON.stringify([au0, stA.autonomy, auBad]));
      // decision book
      const lookup = c => get('decisions/lookup?scene=datacenter&cell=' + c).then(r => r.decision);
      let book = (await get('decisions?scene=datacenter')).decisions, d1 = book.find(d => d.id === 'pr-qa-1');
      check('API decisions: lists the seeded stored decision with cell, parsed actions, source and reuse count', d1 && d1.cell === 'QA1' && d1.decision.actions[0].type === 'quarantine_zone' && d1.source === 'ultra' && d1.reuse_count === 1 && d1.status === 'live' && !book.some(d => d.source === 'peer'), JSON.stringify(d1));
      check('API decisions: lookup reuses a live or pinned decision, never an expired or person one', (await lookup('QA1'))?.id === 'pr-qa-1' && (await lookup('QA3'))?.id === 'pr-qa-pin' && !(await lookup('QA4')) && !(await lookup('QA5')));
      const up = await post('decisions/update', { id: 'pr-qa-exp', expires_in_s: 3600 }), upAt = new Date(up.decision?.expires_at) - Date.now();
      check('API decisions/update: a new expiry brings a decision back into use; a bad one is rejected', up.ok && upAt > 3500e3 && upAt < 3700e3 && (await lookup('QA4'))?.id === 'pr-qa-exp' && !!(await post('decisions/update', { id: 'pr-qa-exp', expires_in_s: 5 })).error, JSON.stringify(up));
      const unpin = await post('decisions/update', { id: 'pr-qa-pin', pinned: false }), gone = await lookup('QA3'), pin = await post('decisions/update', { id: 'pr-qa-pin', pinned: true });
      check('API decisions/update: unpin lets it expire, pin keeps it in use', unpin.ok && !gone && pin.decision?.pinned === true && (await lookup('QA3'))?.id === 'pr-qa-pin', JSON.stringify(pin));
      // incident record
      const inc = await get('incident?id=al-qa-haz');
      check('API incident: links the alarm to its event, perception, model decision, fleet actions and stored decision', inc.alarm?.id === 'al-qa-haz' && inc.event?.cell === 'QA1' && inc.perception?.result?.scene && inc.decision?.tier === 'ultra' && inc.decision.latency_ms === 1234 && inc.decision.actions?.length === 1 &&
        inc.actions.length === 1 && inc.actions[0].id === 'act-qa-1' && inc.stored_decision?.id === 'pr-qa-1' && inc.stored_decision.link === 'created', JSON.stringify(inc).slice(0, 400));
      await post('actions', { scene: 'datacenter', type: 'quarantine_zone', zone: 'C4' });
      const raised = (await get('state?scene=datacenter')).alarms.find(a => /Zone C4 quarantined/.test(a.title)), inc2 = await get('incident?id=' + raised.id);
      check('API incident: a locally raised alarm returns its record with the operator action that raised it', inc2.alarm?.id === raised.id && inc2.actions.some(x => x.type === 'quarantine_zone' && x.source === 'operator' && x.payload.zone === 'C4') && inc2.decision === null && !(await get('incident?id=nope')).alarm, JSON.stringify(inc2).slice(0, 300));
      await post('alarms/release', { id: raised.id });
      const bad1 = await post('incident/override', { id: 'al-qa-haz', actions: [{ type: 'teleport', robot: 'R07' }], note: 'x' }), bad2 = await post('incident/override', { id: 'al-qa-haz', actions: [{ type: 'halt' }] }), bad3 = await post('incident/override', { id: 'al-qa-haz', actions: [] });
      check('API incident/override: rejects an unknown action type, a missing field and an empty list', /invalid/.test(bad1.error || '') && /missing "robot"/.test(bad2.error || '') && !!bad3.error && !(await get('decisions?scene=datacenter')).decisions.some(d => d.source === 'operator'), JSON.stringify([bad1, bad2, bad3]).slice(0, 300));
      const ov = await post('incident/override', { id: 'al-qa-haz', actions: [{ type: 'reroute', robot: 'R07', via: 'cold aisle 4' }], note: 'QA override' });
      book = (await get('decisions?scene=datacenter')).decisions; const opd = book.find(d => d.id === ov.stored_decision);
      check('API incident/override: a hazard with no person becomes an operator decision that replaces the previous one for the cell', ov.ok && opd && opd.source === 'operator' && opd.cell === 'QA1' && opd.decision.actions[0].type === 'reroute' && book.find(d => d.id === 'pr-qa-1').superseded_by === opd.id &&
        (await lookup('QA1'))?.id === opd.id && ov.incident.override?.stored_decision?.id === opd.id && ov.incident.actions.some(x => x.type === 'operator_override' && x.source === 'operator'), JSON.stringify(ov).slice(0, 300));
      const ovp = await post('incident/override', { id: 'al-qa-person', actions: [{ type: 'halt', robot: 'R07' }], note: 'person' }); book = (await get('decisions?scene=datacenter')).decisions;
      check('API incident/override: an incident with a person is logged but never stored for reuse', ovp.ok && ovp.stored_decision === null && ovp.incident.actions.some(x => x.type === 'operator_override') && !book.some(d => d.cell === 'QA2') && !(await lookup('QA2')), JSON.stringify(ovp).slice(0, 300));
      const rv = await post('decisions/revoke', { id: 'pr-qa-pin' }), rvRow = (await get('decisions?scene=datacenter')).decisions.find(d => d.id === 'pr-qa-pin');
      check('API decisions/revoke: a revoked decision is kept in the list and ignored by the lookup', rv.ok && rvRow?.revoked === true && rvRow.status === 'revoked' && !(await lookup('QA3')) && !!(await post('decisions/update', { id: 'pr-qa-pin', pinned: true })).error, JSON.stringify(rvRow));
      errors = [];
      await page.goto(`http://127.0.0.1:${port}/console.html#datacenter`, { waitUntil: 'networkidle0' }); await new Promise(r => setTimeout(r, 1200));
      const live = await page.evaluate(() => ({ mode: document.getElementById('mode').textContent, text: document.body.innerText, svc: document.querySelectorAll('#svc .srow').length }));
      check('console LIVE: detects the API, renders services, no "example only" text, no errors', /^Live/.test(live.mode) && live.svc === 7 && !/example only/i.test(live.text) && !errors.length, live.mode + errors.join(';'));
      await page.click('#q-btn'); await new Promise(r => setTimeout(r, 1500));
      const tags = await page.$eval('#tags', e => e.innerText);
      check('console LIVE: Quarantine button writes a KV tag shown in the console', /zone:C2/.test(tags), tags);
      errors = [];
      const autoV = await page.evaluate(() => ({ btns: [...document.querySelectorAll('#auto-levels button')].map(b => b.textContent + ':' + b.getAttribute('aria-pressed')), rows: [...document.querySelectorAll('#auto-evidence tr')].map(r => r.innerText.replace(/\s+/g, ' ')), line: document.getElementById('gate-line').innerText.replace(/\s+/g, ' '), tau: !!document.getElementById('tau') }));
      check('console LIVE: Autonomy control shows the measured levels, the chosen target with its evidence beside stated confidence, and which gate is in force', autoV.btns.length === gate.levels.length && autoV.btns.filter(b => /:true$/.test(b)).length === 1 && autoV.rows.length === 2 && autoV.rows[0].includes(`${lvl.settled[0]} of ${lvl.settled[1]}`) && autoV.rows[1].includes(`${gate.stated_confidence.settled[0]} of ${gate.stated_confidence.settled[1]} ${gate.stated_confidence.wrong}`) &&
        /In force: stated confidence, τ 0\.\d\d/.test(autoV.line) && /Ready: probability gate, target/.test(autoV.line) && autoV.tau, JSON.stringify(autoV));
      await page.click('#tab-dec'); await new Promise(r => setTimeout(r, 300));
      const decv = await page.evaluate(() => ({ shown: !document.getElementById('pane-dec').hidden, rows: [...document.querySelectorAll('#dec tr[data-id]')].map(r => r.dataset.status + ':' + r.innerText.replace(/\s+/g, ' ')), pin: document.querySelectorAll('#dec [data-op="pin"]').length, ext: document.querySelectorAll('#dec select[data-op="extend"] option').length, rev: document.querySelectorAll('#dec [data-op="revoke"]').length }));
      check('console LIVE: Decisions view lists stored decisions with Pin, Extend and Revoke, no errors', decv.shown && decv.rows.length >= 4 && decv.rows.some(r => /^live:QA1 .*Reroute.*Operator/.test(r)) && decv.rows.some(r => /^revoked:QA3/.test(r)) && decv.pin >= 2 && decv.ext >= 8 && decv.rev >= 2 && !errors.length, JSON.stringify(decv).slice(0, 400) + errors.join(';'));
      await page.evaluate(() => document.querySelector('[data-op="incident"][data-alarm="al-qa-haz"]').click()); await new Promise(r => setTimeout(r, 1200));
      const incv = await page.evaluate(() => { const b = document.getElementById('incident'); return { shown: !b.hidden, text: b.innerText.replace(/\s+/g, ' '), btns: ['inc-accept', 'inc-override', 'inc-release'].every(i => document.getElementById(i)) }; });
      await page.click('#inc-override'); await page.select('#ov-type', 'alert_human');
      const form = await page.evaluate(() => ({ shown: !document.getElementById('inc-form').hidden, types: document.querySelectorAll('#ov-type option').length, fields: [...document.querySelectorAll('#ov-fields [data-k]')].map(i => i.dataset.k).join(',') }));
      check('console LIVE: incident panel shows the linked record with Accept, Override and Release, no errors', incv.shown && incv.btns && /QA alarm QA1/.test(incv.text) && /cold aisle 3/.test(incv.text) && /A puddle in the aisle/.test(incv.text) && /Quarantine zone/.test(incv.text) && /QA override/.test(incv.text) &&
        form.shown && form.types === 7 && form.fields === 'severity,message' && !errors.length, JSON.stringify({ incv, form }).slice(0, 500) + errors.join(';'));
    } finally { try { process.kill(-dev.pid); } catch {} }
  } catch (e) { check('live API checks ran', false, String(e.message).slice(0, 300)); }
  fs.rmSync(state, { recursive: true, force: true });

  await browser.close(); server.close();
  const failed = results.filter(r => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})().catch(e => { console.error(e); server.close(); process.exit(1); });
