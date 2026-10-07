// NemoFleet QA suite: repo hygiene, build, links, and browser checks of the static site.
//   node tests/qa.cjs        (exit code 0 only if every check passes)
// Needs Google Chrome and docs/video/node_modules (puppeteer-core, marked).
const fs = require('fs');
const path = require('path');
const http = require('http');
const vm = require('vm');
const { execFileSync } = require('child_process');
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
for (const f of ['docs/build_architecture_pdf.py', 'docs/build_countercurrent_pdf.py']) {
  try { execFileSync('python3', ['-c', `import ast,sys; ast.parse(open(sys.argv[1]).read())`, path.join(ROOT, f)]); check(`Python parses: ${f}`, true); }
  catch (e) { check(`Python parses: ${f}`, false, String(e.stderr || e.message).slice(0, 200)); }
}
const frames = ['cam-r14-leak', 'cam-r03-person', 'cam-r12-cart', 'cam-r07-clear'].filter(f => !fs.existsSync(path.join(ROOT, 'site', 'assets', 'frames', f + '.jpg')));
check('robot camera frames and overhead floor present', frames.length === 0 && fs.existsSync(path.join(ROOT, 'site', 'assets', 'img', 'floor-overhead.jpg')), frames.join(', '));
const perc = JSON.parse(fs.readFileSync(path.join(ROOT, 'site', 'assets', 'perception', 'index.json'), 'utf8'));
const fakes = Object.entries(perc.results || {}).filter(([n]) => { const f = path.join(ROOT, 'site', 'assets', 'perception', n + '.json'); return !fs.existsSync(f) || !JSON.parse(fs.readFileSync(f, 'utf8')).raw; });
check('every Cosmos result shown has a stored raw response from a real call', fakes.length === 0, fakes.map(x => x[0]).join(', '));
try {
  const outDry = execFileSync('node', [path.join(ROOT, 'tools', 'run_scenario.cjs'), path.join(ROOT, 'scenarios', 'hall-b-coolant-leak.json'), '--dry-run'], { cwd: ROOT }).toString();
  const runDir = outDry.match(/→ (\S+)\/summary\.json/)[1];
  const sum = JSON.parse(fs.readFileSync(path.join(ROOT, runDir, 'summary.json'), 'utf8'));
  fs.rmSync(path.join(ROOT, runDir), { recursive: true, force: true });
  const safety = sum.results.find(r => r.robot === 'R03');
  check('scenario dry run: 6 events, person event routed to Ultra, handshakes make no model calls', sum.totals.events === 6 && safety.tier === 'ultra' && sum.totals.peer === 2 && sum.totals.model_calls === 0, JSON.stringify(sum.totals));
} catch (e) { check('scenario dry run', false, String(e.message).slice(0, 200)); }
const models = fs.readFileSync(path.join(ROOT, 'config', 'models.yaml'), 'utf8');
check('models.yaml names the Token Factory base URL and Cosmos endpoint', /base_url: https:\/\/api\.tokenfactory\./.test(models) && /Cosmos3-Super-Reasoner/.test(models));

// ---------- 3. build ----------
let built = true;
try { execFileSync('node', [path.join(ROOT, 'site', 'build.cjs')], { cwd: ROOT, stdio: 'pipe' }); } catch (e) { built = false; check('site builds', false, String(e.stderr).slice(0, 300)); }
if (built) check('site builds', true);
const pages = ['index.html', 'demo.html', 'console.html', 'video.html', 'docs.html'];
pages.forEach(p => check(`page exists: ${p}`, fs.existsSync(path.join(DIST, p))));
for (const f of fs.readdirSync(path.join(DIST, 'docs'))) {
  const b = fs.readFileSync(path.join(DIST, 'docs', f));
  check(`valid PDF: docs/${f}`, b.slice(0, 5).toString() === '%PDF-' && b.length > 20000);
}
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
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('requestfailed', r => { if (!/fonts\.g/.test(r.url()) && r.failure()?.errorText !== 'net::ERR_ABORTED') errors.push('request failed: ' + r.url()); });
  page.on('response', r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });

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
  await page.click('[data-t="122"]'); await new Promise(r => setTimeout(r, 300));
  const ct = await page.evaluate(() => document.getElementById('vid').currentTime);
  check('chapter link seeks the video', Math.abs(ct - 122) < 2, `currentTime ${ct}`);

  // console interactions
  await page.goto(base + 'console.html', { waitUntil: 'load' });
  await page.click('#act-night'); await new Promise(r => setTimeout(r, 200));
  const toast = await page.evaluate(() => { const t = document.getElementById('toast'); return { shown: !t.hidden, text: t.textContent }; });
  check('console: Run Night Shift shows a clearly labelled example toast', toast.shown && /example only/i.test(toast.text), JSON.stringify(toast));
  await page.click('#act-pause');
  const confirmText = await page.$eval('#act-pause', b => b.textContent);
  check('console: Pause fleet asks for confirmation first', /Confirm/.test(confirmText), confirmText);
  const before = await page.$eval('#open-count', e => +e.textContent);
  await page.click('#al-0-acknowledge');
  const after = await page.$eval('#open-count', e => +e.textContent);
  check('console: acknowledging an alarm lowers the open count', after === before - 1, `${before} → ${after}`);

  await browser.close(); server.close();
  const failed = results.filter(r => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
})().catch(e => { console.error(e); server.close(); process.exit(1); });
