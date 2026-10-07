// Render the markdown planning docs as readable, typeset PDFs.
//   cd docs/video && npm install && cd .. && node build_doc_pdfs.cjs
// Needs Google Chrome; uses marked + puppeteer-core from docs/video/node_modules.
const fs = require('fs');
const path = require('path');
const nm = p => require(path.join(__dirname, 'video', 'node_modules', p));
const { marked } = nm('marked');
const puppeteer = nm('puppeteer-core');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const DOCS = [
  ['NEBIUS_PLAN.md', 'NemoFleet-Nebius-Plan.pdf', 'Implementation plan'],
  ['FEEDBACK.md', 'NemoFleet-Nebius-Feedback.pdf', 'Platform feedback'],
];

const CSS = `
@page { size: Letter; margin: 0.75in 0.8in 0.8in; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: #0f172a; font-size: 10.5pt; line-height: 1.55; margin: 0; }
.kicker { font-size: 8.5pt; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }
h1 { font-size: 22pt; line-height: 1.2; margin: 0 0 10px; letter-spacing: -.01em; padding-bottom: 10px; border-bottom: 2.5px solid #0f172a; }
h2 { font-size: 14pt; margin: 22px 0 8px; padding-top: 4px; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 16px 0 6px; break-after: avoid; }
p { margin: 0 0 9px; }
ul, ol { margin: 0 0 10px; padding-left: 20px; }
li { margin: 3px 0; }
li > ul, li > ol { margin: 3px 0; }
strong { font-weight: 650; }
a { color: #1d4ed8; text-decoration: none; }
code { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 9pt; background: #f1f5f9; border-radius: 4px; padding: 1px 4px; }
blockquote { margin: 10px 0; padding: 8px 14px; border-left: 4px solid #0f172a; background: #f8fafc; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 14px; font-size: 9pt; break-inside: auto; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { text-align: left; font-size: 8pt; text-transform: uppercase; letter-spacing: .05em; color: #475569;
  border-bottom: 2px solid #0f172a; padding: 6px 8px; }
td { padding: 6px 8px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr:nth-child(even) td { background: #fafbfc; }
hr { border: 0; border-top: 1px solid #e2e8f0; margin: 18px 0; }
`;

async function main() {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage();
  for (const [src, out, kicker] of DOCS) {
    const md = fs.readFileSync(path.join(__dirname, src), 'utf8')
      .replace(/\]\(([A-Za-z0-9_.-]+)\.md(#[^)]*)?\)/g, '](https://github.com/gretchenboria/NemoFleet/blob/main/docs/$1.md$2)');
    const body = marked.parse(md);
    await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>${CSS}</style></head>` +
      `<body><div class="kicker">NemoFleet · ${kicker}</div>${body}</body></html>`, { waitUntil: 'load' });
    await page.pdf({
      path: path.join(__dirname, out), format: 'Letter', printBackground: true, displayHeaderFooter: true,
      headerTemplate: '<span></span>',
      footerTemplate: `<div style="font-size:8px;color:#94a3b8;width:100%;padding:0 0.8in;display:flex;justify-content:space-between;font-family:-apple-system,Helvetica,Arial">` +
        `<span>NemoFleet · ${kicker}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
      margin: { top: '0.75in', bottom: '0.8in', left: '0.8in', right: '0.8in' },
    });
    console.log('wrote', out);
  }
  await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
