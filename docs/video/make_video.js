// Build the NemoFleet peer-learning explainer video.
//   node make_video.js out.mp4                  full render
//   node make_video.js --preview 3,20,60 dir/   stills at given seconds
// Needs: ffmpeg/ffprobe, Google Chrome, puppeteer-core, and GEMINI_API_KEY (env or repo .env)
// for Gemini TTS; falls back to macOS `say` without a key.
const { execFileSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const TTS_MODEL = 'gemini-3.8-flash-tts', TTS_VOICE = 'Achird', TTS_TAGS = '[warm] [friendly] ';
const SAY_VOICE = 'Samantha', SAY_RATE = '172', FPS = 30, LEAD = 0.4, TAIL = 1.0;
const crypto = require('crypto');
const here = __dirname, work = path.join(here, 'build');
fs.mkdirSync(work, { recursive: true });

function geminiKey() {
  if (process.env.GEMINI_API_KEY) return process.env.GEMINI_API_KEY;
  const env = path.join(here, '..', '..', '.env');
  if (!fs.existsSync(env)) return null;
  const m = fs.readFileSync(env, 'utf8').match(/^GEMINI_API_KEY=(.+)$/m);
  return m ? m[1].trim() : null;
}

// Gemini TTS: style comes from inline audio tags (the model reads plain-text instructions aloud).
async function geminiTTS(key, text, out) {
  const body = { contents: [{ parts: [{ text: TTS_TAGS + text }] }],
    generationConfig: { responseModalities: ['AUDIO'], speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: TTS_VOICE } } } } };
  for (let attempt = 1; ; attempt++) {
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${TTS_MODEL}:generateContent`,
      { method: 'POST', headers: { 'x-goog-api-key': key, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const j = await r.json();
    const part = j.candidates?.[0]?.content?.parts?.[0]?.inlineData;
    if (part) {
      const buf = Buffer.from(part.data, 'base64');
      if (part.mimeType.includes('wav')) fs.writeFileSync(out, buf);
      else {
        const rate = (part.mimeType.match(/rate=(\d+)/) || [, '24000'])[1], pcm = out + '.pcm';
        fs.writeFileSync(pcm, buf);
        execFileSync('ffmpeg', ['-y', '-v', 'error', '-f', 's16le', '-ar', rate, '-ac', '1', '-i', pcm, out]);
        fs.unlinkSync(pcm);
      }
      return;
    }
    if (attempt >= 4) throw new Error('Gemini TTS failed: ' + JSON.stringify(j).slice(0, 300));
    await new Promise(res => setTimeout(res, 2000 * attempt));
  }
}

async function narrate(text, key) {
  const id = crypto.createHash('sha1').update([key ? TTS_MODEL + TTS_VOICE + TTS_TAGS : SAY_VOICE + SAY_RATE, text].join('|')).digest('hex').slice(0, 16);
  const out = path.join(work, `${id}.${key ? 'wav' : 'aiff'}`);
  if (!fs.existsSync(out)) {
    if (key) await geminiTTS(key, text, out);
    else execFileSync('say', ['-v', SAY_VOICE, '-r', SAY_RATE, '-o', out, text]);
  }
  return out;
}

async function buildTimeline() {
  const scenes = JSON.parse(fs.readFileSync(path.join(here, 'scenes.json'), 'utf8'));
  const key = geminiKey();
  console.log(key ? `voice: ${TTS_MODEL} / ${TTS_VOICE}` : `voice: macOS say / ${SAY_VOICE} (no GEMINI_API_KEY)`);
  let start = 0;
  const out = [];
  for (const s of scenes) {
    const aiff = await narrate(s.text, key);
    const audio = parseFloat(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', aiff]).toString());
    const dur = Math.max(s.min, LEAD + audio + TAIL);
    const parts = s.text.split(/(?<=[.!?])\s+/);
    const total = parts.reduce((a, p) => a + p.length, 0);
    let acc = 0;
    const sentences = parts.map((p, k) => {
      const t0 = LEAD + audio * acc / total;
      acc += p.length;
      return { text: p, t0, t1: k === parts.length - 1 ? dur - 0.2 : LEAD + audio * acc / total };
    });
    out.push({ id: s.id, start, dur, audio, aiff, sentences });
    start += dur;
  }
  return out;
}

function buildAudio(tl, out) {
  const args = ['-y', '-v', 'error'];
  tl.forEach(s => args.push('-i', s.aiff));
  const f = tl.map((s, i) => `[${i}:a]aresample=48000,adelay=${Math.round(LEAD * 1000)}:all=1,apad=whole_dur=${s.dur.toFixed(3)},atrim=0:${s.dur.toFixed(3)}[a${i}]`).join(';');
  const cat = tl.map((_, i) => `[a${i}]`).join('') + `concat=n=${tl.length}:v=0:a=1[out]`;
  args.push('-filter_complex', `${f};${cat}`, '-map', '[out]', '-c:a', 'aac', '-b:a', '160k', out);
  execFileSync('ffmpeg', args);
}

async function main() {
  const preview = process.argv[2] === '--preview';
  const tl = await buildTimeline();
  const total = tl.reduce((a, s) => a + s.dur, 0);
  console.log(tl.map(s => `${s.id}: ${s.start.toFixed(1)}s +${s.dur.toFixed(1)}s`).join('\n'), `\ntotal ${total.toFixed(1)}s`);

  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(here, 'anim.html'));
  await page.evaluate(t => window.setTimeline(t), tl.map(({ aiff, ...rest }) => rest));

  if (preview) {
    const times = process.argv[3].split(',').map(Number), dir = process.argv[4];
    fs.mkdirSync(dir, { recursive: true });
    for (const t of times) {
      await page.evaluate(t => window.render(t), t);
      await page.screenshot({ path: path.join(dir, `t${String(t).padStart(5, '0')}.png`) });
    }
    await browser.close();
    return;
  }

  const out = path.resolve(process.argv[2] || 'explainer.mp4');
  const audio = path.join(work, 'narration.m4a');
  buildAudio(tl, audio);
  const ff = spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-i', audio, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium', '-c:a', 'copy',
    '-movflags', '+faststart', '-shortest', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const frames = Math.ceil(total * FPS);
  for (let f = 0; f < frames; f++) {
    await page.evaluate(t => window.render(t), f / FPS);
    const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (f % 300 === 0) console.log(`frame ${f}/${frames}`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
  console.log('wrote', out);
}

if (require.main === module) main().catch(e => { console.error(e); process.exit(1); });
module.exports = { buildTimeline };
