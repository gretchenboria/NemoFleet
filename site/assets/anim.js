// NemoFleet hero animations: antennation handshake and countercurrent pairing.
// Canvas 2D, DPR-aware, no libraries. Under reduced motion each draws one representative frame.
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const ease = t => { t = clamp(t); return t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
  const out = t => 1 - Math.pow(1 - clamp(t), 3);
  const MONO = '"JetBrains Mono", Menlo, monospace', BODY = 'Barlow, Arial, sans-serif';

  function hexMix(a, b, t) {
    const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const A = p(a), B = p(b);
    return 'rgb(' + A.map((v, i) => Math.round(v + (B[i] - v) * clamp(t))).join(',') + ')';
  }
  function palette() {
    return { bg: css('--surface'), line: css('--line'), ink: css('--ink'), ink2: css('--ink-2'), ink3: css('--ink-3'),
      s1: css('--s1'), s15: css('--s15'), s2: css('--s2'), warn: css('--warn'), cold: css('--cold'), heat: css('--heat') };
  }
  function setup(canvas, W, H) {
    const ctx = canvas.getContext('2d');
    const fit = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1), cw = canvas.clientWidth || W;
      canvas.width = Math.round(cw * dpr); canvas.height = Math.round(cw * H / W * dpr);
      ctx.setTransform(canvas.width / W, 0, 0, canvas.height / H, 0, 0);
    };
    fit(); addEventListener('resize', fit);
    return ctx;
  }
  function gridTex(ctx, W, H, C) {
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = C.line; ctx.globalAlpha = .45; ctx.lineWidth = .5;
    for (let x = 0; x <= W; x += 24) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
    for (let y = 0; y <= H; y += 24) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
    ctx.globalAlpha = 1;
  }
  function pill(ctx, x, y, text, col, C, size = 12) {
    ctx.font = `500 ${size}px ${MONO}`;
    const w = ctx.measureText(text).width + 14, h = size + 10;
    ctx.fillStyle = C.bg; ctx.strokeStyle = col; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.roundRect(x - w / 2, y - h / 2, w, h, 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = col; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text, x, y + .5);
    ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
  }

  // ---------- (b) antennation handshake, 7 s loop ----------
  function antennation(canvas) {
    const W = 720, H = 400, ctx = setup(canvas, W, H), LOOP = 7;
    const TOP = 182, BOT = 236, HAZ = { x: 618, y: 186, w: 52, h: 46 };
    function robot(x, y, dir, C, label, knows) {
      ctx.save(); ctx.translate(x, y);
      ctx.strokeStyle = C.ink; ctx.globalAlpha = .3; ctx.lineWidth = 1.5;
      for (const a of [-0.45, 0.45]) { ctx.beginPath(); ctx.moveTo(dir * 10, a * 6); ctx.lineTo(dir * (10 + 10 * Math.cos(a)), a * 6 + 10 * Math.sin(a)); ctx.stroke(); }
      ctx.globalAlpha = 1;
      ctx.fillStyle = knows ? C.warn : C.s1; ctx.fillRect(-10, -10, 20, 20);
      ctx.fillStyle = C.bg; ctx.fillRect(dir > 0 ? 4 : -7, -2, 3, 4);
      ctx.restore();
      ctx.fillStyle = C.ink2; ctx.font = `600 12px ${MONO}`; ctx.textAlign = 'center'; ctx.fillText(label, x, y + (y < 210 ? -18 : 30)); ctx.textAlign = 'start';
    }
    function ring(x, y, C, a) {
      ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = C.s15; ctx.globalAlpha = .4 * a; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(x, y, 34, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    }
    function frame(t) {
      const C = palette(); t = t % LOOP;
      gridTex(ctx, W, H, C);
      ctx.fillStyle = C.line;
      ctx.fillRect(30, 120, 660, 28); ctx.fillRect(30, 270, 440, 28); ctx.fillRect(540, 270, 150, 28);
      ctx.fillStyle = C.ink3; ctx.font = `500 11px ${MONO}`; ctx.fillText('AISLE 4 · ZONE B', 34, 112);
      ctx.fillText('CROSS-AISLE', 476, 330);
      // hazard cell + ttl decay
      const ttl = 1 - t / LOOP * 0.85;
      ctx.save(); ctx.strokeStyle = C.warn; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.strokeRect(HAZ.x, HAZ.y, HAZ.w, HAZ.h); ctx.restore();
      ctx.globalAlpha = .25 + .55 * ttl; ctx.fillStyle = C.warn; ctx.beginPath(); ctx.ellipse(HAZ.x + 26, HAZ.y + 24, 18, 9, 0, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1;
      ctx.fillStyle = C.warn; ctx.font = `500 11px ${MONO}`; ctx.fillText(`c14 · ttl ${Math.round(90 * ttl)}s`, HAZ.x - 6, HAZ.y - 8);
      // positions
      const ax = t < 1.5 ? lerp(60, 300, ease(t / 1.5)) : t < 1.9 ? 300 : t < 3.2 ? lerp(300, 470, ease((t - 1.9) / 1.3)) : t < 3.6 ? 470 : lerp(470, 572, out((t - 3.6) / 1.4));
      const bx = t < 1.5 ? lerp(600, 322, ease(t / 1.5)) : t < 1.9 ? 322 : lerp(322, 40, ease((t - 1.9) / 2.2));
      let cx = 505, cy = 300;
      if (t < 2.0) cy = 330; else if (t < 2.7) { cy = lerp(330, BOT, ease((t - 2.0) / 0.7)); }
      else { cy = BOT; cx = t < 3.2 ? 505 - (t - 2.7) * 30 : t < 3.6 ? 490 : lerp(490, 380, ease((t - 3.6) / 1.6)); }
      const aKnows = t >= 1.75, cKnows = t >= 3.45;
      // handshakes
      if (t >= 1.4 && t < 2.2) { ring(ax, TOP, C, 1); ring(bx, BOT, C, 1); }
      if (t >= 3.1 && t < 3.9) { ring(ax, TOP, C, 1); ring(cx, BOT, C, 1); }
      if (t >= 1.5 && t < 1.8) {
        const p = out((t - 1.5) / 0.28);
        pill(ctx, lerp(bx, ax, p), lerp(BOT - 20, TOP + 20, p) - 40, 'HAZARD c14 · ttl 90s', C.warn, C, 11);
        pill(ctx, lerp(ax, bx, p), lerp(TOP + 20, BOT - 20, p) + 40, 'ORDER 4471', C.ink2, C, 11);
      }
      if (t >= 3.2 && t < 3.5) { const p = out((t - 3.2) / 0.28); pill(ctx, lerp(ax, cx, p), lerp(TOP, BOT, p) + 46, 'HAZARD c14', C.warn, C, 11); }
      if (bx > 50) robot(bx, BOT, -1, C, 'B', true);
      robot(ax, TOP, 1, C, 'A', aKnows);
      if (t >= 1.9) robot(cx, cy, cy < BOT + 1 && t >= 2.7 ? -1 : 1, C, 'C', cKnows);
      if (aKnows) pill(ctx, ax, TOP - 44, t < 3.2 ? 'hop 1 · conf 0.92' : 'hop 1 · conf 0.92', C.s15, C, 11);
      if (cKnows && t < 6.6) pill(ctx, cx, BOT + 54, 'hop 2 · conf 0.83', C.s15, C, 11);
      // teaching moment
      const m = clamp((t - 5.0) / 0.4) * clamp((LOOP - t) / 0.4);
      if (m > 0) {
        ctx.globalAlpha = m; pill(ctx, 470, 80, 'A settled by Nano (S1) · peer precedent hop 1', C.s1, C, 12); ctx.globalAlpha = 1;
      }
      ctx.fillStyle = C.ink3; ctx.font = `500 11px ${MONO}`; ctx.fillText('ULTRA CALLS', 600, 30);
      ctx.fillStyle = C.s2; ctx.font = `600 26px ${BODY}`; ctx.fillText('0', 600, 58);
      ctx.fillStyle = C.ink3; ctx.font = `500 11px ${MONO}`; ctx.fillText('MODEL CALLS TO SPREAD', 30, 30);
      ctx.fillStyle = C.s15; ctx.font = `600 26px ${BODY}`; ctx.fillText('0', 30, 58);
    }
    return frame;
  }

  // ---------- (a) countercurrent pairing, 6 s loop ----------
  function countercurrent(canvas) {
    const W = 720, H = 400, ctx = setup(canvas, W, H), LOOP = 6;
    const X0 = 30, X1 = 470, SPAN = X1 - X0, SP = 88, V = SPAN / LOOP, LA = 150, LB = 250;
    const ctr = x => 0.38 + 0.55 * clamp((x - X0) / SPAN);
    function chip(x, y, c, C, op) {
      ctx.globalAlpha = op; ctx.fillStyle = hexMix(C.cold, C.heat, c); ctx.beginPath(); ctx.roundRect(x - 22, y - 9, 44, 18, 2); ctx.fill();
      ctx.fillStyle = '#ffffff'; ctx.font = `600 10.5px ${MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('c=' + c.toFixed(2), x, y + .5);
      ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic'; ctx.globalAlpha = 1;
    }
    function frame(t) {
      const C = palette(); t = t % LOOP;
      gridTex(ctx, W, H, C);
      // faint vessel echo
      ctx.globalAlpha = .07; ctx.lineWidth = 6;
      ctx.strokeStyle = C.heat; ctx.beginPath(); ctx.moveTo(X0, LA - 30); ctx.bezierCurveTo(180, LA - 60, 320, LB + 40, X1, LB + 20); ctx.stroke();
      ctx.strokeStyle = C.cold; ctx.beginPath(); ctx.moveTo(X0, LB + 30); ctx.bezierCurveTo(180, LB + 60, 320, LA - 40, X1, LA - 20); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = C.line; ctx.lineWidth = 1;
      [LA, LB].forEach(y => { ctx.strokeRect(X0 - 4, y - 22, SPAN + 8, 44); });
      ctx.fillStyle = C.ink3; ctx.font = `500 11px ${MONO}`;
      ctx.fillText('LANE A · INBOUND · NAIVE  →', X0, LA - 32); ctx.fillText('←  LANE B · OUTBOUND · TRAINED', X0, LB + 40);
      ctx.fillText('EDGE', X0, 360); ctx.textAlign = 'end'; ctx.fillText('CORE', X1, 360); ctx.textAlign = 'start';
      const naive = [], trained = [];
      for (let i = 0; i < 5; i++) {
        const d = (i * SP + t * V) % SPAN; naive.push({ x: X0 + d, d });
        trained.push({ x: X1 - (i * SP + SP / 2 + t * V) % SPAN });
      }
      const edgeOp = x => clamp(Math.min(x - X0, X1 - x) / 24);
      let label = null;
      naive.forEach(n => trained.forEach(tr => {
        const dx = Math.abs(n.x - tr.x);
        if (dx < 10) {
          const a = (1 - dx / 10) * edgeOp(n.x);
          ctx.strokeStyle = C.s15; ctx.globalAlpha = a; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(n.x, LA + 10); ctx.lineTo(n.x, LB - 10); ctx.stroke(); ctx.globalAlpha = 1;
          if (!label || Math.abs(n.x - 250) < Math.abs(label.x - 250)) label = { x: n.x, a };
        }
      }));
      if (label) { ctx.globalAlpha = label.a; pill(ctx, label.x + 44, (LA + LB) / 2, 'Δ3 prec', C.s15, C, 10.5); ctx.globalAlpha = 1; }
      trained.forEach(tr => chip(tr.x, LB, ctr(tr.x), C, edgeOp(tr.x)));
      naive.forEach(n => { const step = SP / 2, lastPass = n.x - (n.d % step); chip(n.x, LA, Math.max(0.08, ctr(lastPass) - 0.12), C, edgeOp(n.x)); });
      // learning curves
      const gx = 520, gy = 90, gw = 170, gh = 200;
      ctx.strokeStyle = C.line; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(gx, gy); ctx.lineTo(gx, gy + gh); ctx.lineTo(gx + gw, gy + gh); ctx.stroke();
      ctx.fillStyle = C.ink3; ctx.font = `500 10.5px ${MONO}`; ctx.fillText('COMPETENCE OF A NEW ROBOT', gx, gy - 14);
      ctx.fillText('passes →', gx + gw - 52, gy + gh + 16);
      const p = clamp(t / (LOOP * 0.8));
      const curve = (f, col) => {
        ctx.strokeStyle = col; ctx.lineWidth = 2.5; ctx.beginPath();
        for (let i = 0; i <= 40 * p; i++) { const u = i / 40, x = gx + u * gw, y = gy + gh - f(u) * gh; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
        ctx.stroke();
      };
      curve(u => 0.1 + 0.4 * (1 - Math.exp(-5 * u)), C.ink3);
      curve(u => 0.1 + 0.8 * u, C.s15);
      ctx.font = `600 11px ${MONO}`; ctx.fillStyle = C.s15; ctx.fillText('countercurrent', gx + 8, gy + 12);
      ctx.fillStyle = C.ink3; ctx.fillText('random pairing', gx + 8, gy + 28);
      ctx.font = `500 10px ${MONO}`; ctx.fillText('illustrative · sweep pending', gx, gy + gh + 34);
    }
    return frame;
  }

  const boot = [['anim-antennation', antennation, 5.6], ['anim-countercurrent', countercurrent, 4.2]];
  boot.forEach(([id, make, still]) => {
    const el = document.getElementById(id);
    if (!el) return;
    const draw = make(el);
    if (reduce) { const redraw = () => draw(still); redraw(); addEventListener('resize', redraw); matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redraw); return; }
    const t0 = performance.now();
    const loop = now => { draw((now - t0) / 1000); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  });
})();
