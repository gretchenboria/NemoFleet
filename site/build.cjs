// Build the NemoFleet site into site/dist for Cloudflare Pages.
//   node site/build.cjs && npx wrangler pages deploy   (from the repo root; wrangler.toml binds D1/KV/R2 for ./functions)
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const SRC = path.join(__dirname, 'src'), DIST = path.join(__dirname, 'dist');

fs.rmSync(DIST, { recursive: true, force: true });
fs.mkdirSync(path.join(DIST, 'docs'), { recursive: true });
fs.cpSync(path.join(__dirname, 'assets'), path.join(DIST, 'assets'), { recursive: true });

const PDFS = [
  ['NemoFleet-Architecture-Today-vs-Next.pdf', 'TODAY · NEXT', 'Architecture: today and next', 'What runs end to end today, the future state, a component-by-component comparison and the whole tech stack, with live/planned status.'],
  ['NemoFleet-Architecture.pdf', 'ARCHITECTURE', 'System architecture', 'System map, two sites and the live API, peer layer, warm core, Night Shift, escalation sequence, responsibilities, red-team pipeline, code map.'],
  ['NemoFleet-Nebius-Plan.pdf', 'PLAN', 'Implementation plan', 'Agreed by three review agents: decisions, schedule, cut lines and vote record.'],
  ['NemoFleet-Demo-Use-Case.pdf', 'DEMO', 'Demo use case', 'One hazard at two sites (warehouse spill, data center coolant leak): Day 1 → Night Shift → Day 2, with what is real and the fallbacks.'],
  ['NemoFleet-Countercurrent-Options.pdf', 'DESIGN', 'Peer-learning options', 'The three peer-learning designs considered, with comparison.'],
  ['NemoFleet-Nebius-Feedback.pdf', 'FEEDBACK', 'Platform feedback', 'Measured feedback on Token Factory, Serverless AI and AI Cloud.'],
];
PDFS.forEach(([f]) => fs.copyFileSync(path.join(ROOT, 'docs', f), path.join(DIST, 'docs', f)));
fs.copyFileSync(path.join(ROOT, 'docs', 'NemoFleet-Peer-Learning-Explainer.mp4'), path.join(DIST, 'assets', 'nemofleet-explainer.mp4'));

const FAVICON = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="3" fill="#12171C"/>' +
  '<text x="16" y="19" font-family="Arial" font-weight="700" font-size="14" fill="#E5E9ED" text-anchor="middle">NF</text>' +
  '<rect x="6" y="23" width="20" height="1.5" fill="#D9622B"/><rect x="6" y="26" width="20" height="1.5" fill="#3A6EA5"/></svg>');
const NAV = [['index.html', 'Overview'], ['console.html', 'Console'], ['video.html', 'Video'], ['docs.html', 'Docs']];

function layout(file, title, desc, body, extra = '') {
  const nav = NAV.map(([href, label]) => `<li><a href="${href}"${href === file ? ' aria-current="page"' : ''}>${label}</a></li>`).join('');
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>${title}</title><meta name="description" content="${desc}">
<meta property="og:title" content="${title}"><meta property="og:description" content="${desc}"><meta property="og:image" content="assets/img/video-poster.jpg">
<link rel="icon" href="${FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Semi+Condensed:wght@400;600&family=JetBrains+Mono:wght@400;500;600&display=swap">
<link rel="stylesheet" href="assets/site.css"></head>
<body>
<nav class="nav" aria-label="Main"><div class="wrap">
  <a class="wordmark" href="index.html" aria-label="NemoFleet home"><span><b>Nemo</b><span>Fleet</span></span><i></i><i></i></a>
  <ul>${nav}</ul>
  <a class="gh" href="https://github.com/gretchenboria/NemoFleet">GitHub ↗</a>
</div></nav>
<main>${body}</main>
<footer class="foot"><div class="overlay-img" aria-hidden="true"></div><div class="wrap">
  <a class="wordmark" href="index.html"><span><b>Nemo</b><span>Fleet</span></span><i></i><i></i></a>
  <p class="small">Built for the Nebius × NVIDIA Global AI Hackathon, Physical AI track. NVIDIA Nemotron on Nebius Token Factory. Every number in the console comes from a real model call.</p>
  <p class="small mono">The edge lives it once. Nebius lives it hundreds of times.</p>
</div></footer>
${extra}
</body></html>
`;
}
const write = (f, html) => fs.writeFileSync(path.join(DIST, f), html);

// overview
write('index.html', layout('index.html', 'NemoFleet', 'One hazard, one Ultra call, and the whole fleet knows: Nemotron Ultra decides once on Nebius Token Factory, and fleet memory lets every robot reuse the decision through Nemotron Nano.',
  fs.readFileSync(path.join(SRC, 'index.body.html'), 'utf8'), '<script src="assets/anim.js" defer></script>'));

// video
const chapters = [['0:00', 0, 'A fleet that learns from itself'], ['0:09', 9, 'The problem'], ['0:27', 27, 'Three speeds of thinking'], ['0:58', 58, 'Two ideas from biology'],
  ['1:13', 73, 'Robots swap knowledge when they pass'], ['1:32', 92, 'Countercurrent pairing'], ['1:46', 106, 'Safety boundary'], ['2:05', 125, 'Night Shift on Nebius'],
  ['2:46', 166, 'Day 2: an unseen variant'], ['3:03', 183, 'Two sites: warehouse and data center'], ['3:22', 202, 'How we prove it']];
write('video.html', layout('video.html', 'NemoFleet Explainer', 'A 3-minute narrated explainer of NemoFleet: architecture, peer exchange, safety and Night Shift on Nebius.',
  `<section class="band" style="border-top:0"><div class="wrap">
    <div class="sec-head"><span class="eyebrow">Explainer · 3:43</span><h2>How NemoFleet works</h2><p class="lead">Narrated with Gemini 3.8 Flash TTS. Animations are illustrative; result numbers come only from recorded runs.</p></div>
    <video class="video" id="vid" controls preload="metadata" poster="assets/img/video-poster.jpg" src="assets/nemofleet-explainer.mp4"></video>
    <div class="tbl"><table><thead><tr><th>Time</th><th>Chapter</th></tr></thead><tbody>
      ${chapters.map(([ts, s, t]) => `<tr><td class="mono"><a href="#t${s}" data-t="${s}">${ts}</a></td><td>${t}</td></tr>`).join('')}
    </tbody></table></div>
  </div></section>`,
  `<script>document.querySelectorAll('[data-t]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();const v=document.getElementById('vid');v.currentTime=+a.dataset.t;v.play().catch(()=>{});}));</script>`));

// docs
write('docs.html', layout('docs.html', 'NemoFleet Docs', 'Architecture, implementation plan, demo use case, design options and platform feedback for NemoFleet.',
  `<section class="band grid-tex" style="border-top:0"><div class="wrap">
    <div class="sec-head"><span class="eyebrow">Documents</span><h2>Docs</h2><p class="lead">Print-ready PDFs. The markdown sources live in the repository.</p></div>
    <div class="docs">${PDFS.map(([f, tag, t, d]) => `<a class="doc" href="docs/${f}"><span class="tag">${tag}</span><span><b>${t}</b><span class="small">${d}</span></span><span class="mono small">PDF ↗</span></a>`).join('')}</div>
  </div></section>`));

// console (the dashboard prototype, with a link back to the site)
let consoleBody = fs.readFileSync(path.join(SRC, 'console.body.html'), 'utf8')
  .replace('<div class="wrap">', '<div class="wrap"><a href="index.html" style="font-family:var(--f-mono);font-size:13px;color:var(--muted);text-decoration:none">← NemoFleet overview</a>');
write('console.html', `<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><link rel="icon" href="${FAVICON}"><style>body{margin:0}</style></head><body>\n${consoleBody}\n</body></html>\n`);

// data for the console API (functions/api): scenarios and the model registry, read via env.ASSETS
fs.mkdirSync(path.join(DIST, 'scenarios'), { recursive: true });
fs.readdirSync(path.join(ROOT, 'scenarios')).filter(f => f.endsWith('.json')).forEach(f => fs.copyFileSync(path.join(ROOT, 'scenarios', f), path.join(DIST, 'scenarios', f)));
fs.mkdirSync(path.join(DIST, 'config'), { recursive: true });
// fine-tune results shown on the console's Night Shift tab (written by tools/night_shift/publish.py from real result files)
if (fs.existsSync(path.join(ROOT, 'config', 'night_shift.json'))) fs.copyFileSync(path.join(ROOT, 'config', 'night_shift.json'), path.join(DIST, 'config', 'night_shift.json'));
fs.writeFileSync(path.join(DIST, 'config', 'models.json'), JSON.stringify(require(path.join(ROOT, 'tools', 'tf.cjs')).models(), null, 2));

fs.writeFileSync(path.join(DIST, '_headers'), `/assets/*\n  Cache-Control: public, max-age=86400\n/docs/*\n  Cache-Control: public, max-age=3600\n/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n`);
console.log('built', fs.readdirSync(DIST).join(' '));
