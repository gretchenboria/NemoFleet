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
for (const f of ['site/assets/anim.js', 'site/build.cjs', 'docs/build_doc_pdfs.cjs', 'docs/video/make_video.js', 'tools/cosmos_perceive.cjs', 'tools/tf.cjs', 'tools/preflight.cjs', 'tools/run_scenario.cjs', 'tests/qa.cjs']) {
  try { new vm.Script(fs.readFileSync(path.join(ROOT, f), 'utf8').replace(/^#!.*/, ''), { filename: f }); check(`JS parses: ${f}`, true); }
  catch (e) { check(`JS parses: ${f}`, false, e.message); }
}
try { new vm.Script(fs.readFileSync(path.join(ROOT, 'functions/api/[[path]].js'), 'utf8').replace(/^export /m, ''), { filename: 'api' }); check('JS parses: functions/api/[[path]].js', true); }
catch (e) { check('JS parses: functions/api/[[path]].js', false, e.message); }
check('wrangler.jsonc binds MEMORY (D1), TAGS (KV), RUNS (R2) and publishes site/dist', (() => { const w = fs.readFileSync(path.join(ROOT, 'wrangler.jsonc'), 'utf8'); return /"MEMORY"/.test(w) && /"TAGS"/.test(w) && /"RUNS"/.test(w) && /"site\/dist"/.test(w); })());
for (const f of ['docs/build_architecture_pdf.py', 'docs/build_countercurrent_pdf.py']) {
  try { execFileSync('python3', ['-c', `import ast,sys; ast.parse(open(sys.argv[1]).read())`, path.join(ROOT, f)]); check(`Python parses: ${f}`, true); }
  catch (e) { check(`Python parses: ${f}`, false, String(e.stderr || e.message).slice(0, 200)); }
}
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
    check(`${scen} dry run: 6 events, person event routed to Ultra, handshakes make no model calls`, sum.totals.events === 6 && safety.tier === 'ultra' && sum.totals.peer === 2 && sum.totals.model_calls === 0, JSON.stringify(sum.totals));
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
  for (const sc of ['warehouse', 'datacenter']) {
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
  check('console offline: labelled "Offline preview" with a banner, and shows no numbers', off.mode === 'Offline preview' && off.banner && off.kpis.every(v => v === '—'), JSON.stringify({ mode: off.mode, kpis: off.kpis }));
  check('console: no "example only" text anywhere', !/example only/i.test(off.text));
  await page.click('#act-night'); await new Promise(r => setTimeout(r, 200));
  const toast = await page.evaluate(() => { const t = document.getElementById('toast'); return { shown: !t.hidden, text: t.textContent }; });
  check('console offline: buttons say they are not connected and link the live console', toast.shown && /Not connected/.test(toast.text) && /nemofleet\.pages\.dev/.test(toast.text), JSON.stringify(toast));

  // ---------- 6. live API + console against wrangler pages dev (local D1/KV/R2; no model calls) ----------
  const state = fs.mkdtempSync(path.join(os.tmpdir(), 'nf-qa-'));
  try {
    execFileSync('npx', ['wrangler', 'd1', 'migrations', 'apply', 'nemofleet-memory', '--local', '-c', 'cloudflare/wrangler.jsonc', '--persist-to', state], { cwd: ROOT, stdio: 'pipe' });
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
      check('API: scenario start returns 6 events; a handshake step makes no model call', s0.events?.length === 6 && peer.tier === 'peer' && peer.model_calls === 0, JSON.stringify(peer));
      errors = [];
      await page.goto(`http://127.0.0.1:${port}/console.html#datacenter`, { waitUntil: 'networkidle0' }); await new Promise(r => setTimeout(r, 1200));
      const live = await page.evaluate(() => ({ mode: document.getElementById('mode').textContent, text: document.body.innerText, svc: document.querySelectorAll('#svc .srow').length }));
      check('console LIVE: detects the API, renders services, no "example only" text, no errors', /^Live/.test(live.mode) && live.svc === 7 && !/example only/i.test(live.text) && !errors.length, live.mode + errors.join(';'));
      await page.click('#q-btn'); await new Promise(r => setTimeout(r, 1500));
      const tags = await page.$eval('#tags', e => e.innerText);
      check('console LIVE: Quarantine button writes a KV tag shown in the console', /zone:C2/.test(tags), tags);
    } finally { try { process.kill(-dev.pid); } catch {} }
  } catch (e) { check('live API checks ran', false, String(e.message).slice(0, 300)); }
  fs.rmSync(state, { recursive: true, force: true });

  await browser.close(); server.close();
  const failed = results.filter(r => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})().catch(e => { console.error(e); server.close(); process.exit(1); });
