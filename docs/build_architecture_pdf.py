"""Build the NemoFleet architecture PDF as hand-laid SVG pages in HTML.

Usage:
    python3 docs/build_architecture_pdf.py /tmp/arch.html
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
        --no-pdf-header-footer --print-to-pdf=docs/NemoFleet-Architecture.pdf file:///tmp/arch.html
"""
import html
import sys

C = {
    "runtime": ("#1d4ed8", "#eff6ff"),
    "s1": ("#3f6212", "#f1f9e4"),
    "s2": ("#6d28d9", "#f5f3ff"),
    "motion": ("#334155", "#eef2f6"),
    "batch": ("#b45309", "#fff7ed"),
    "ui": ("#475569", "#ffffff"),
}
C["peer"] = ("#0f766e", "#f0fdfa")
C["hot"] = ("#b91c1c", "#fef2f2")
C["cold"] = ("#0e7490", "#ecfeff")
C["warm"] = ("#b45309", "#fffbeb")
INK = "#475569"


def e(s):
    return html.escape(s, quote=True)


def box(x, y, w, h, kind, title, sub=None, tag=None, title_size=15, mono=False):
    stroke, fill = C[kind]
    lines = sub if isinstance(sub, list) else ([sub] if sub else [])
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    total = title_size + 15 * len(lines)
    ty = y + h / 2 - total / 2 + title_size - 2
    cls = "tm" if mono else "t"
    out += f'<text x="{x + w / 2}" y="{ty}" class="{cls}" fill="{stroke}" style="font-size:{title_size}px">{e(title)}</text>'
    for i, line in enumerate(lines):
        out += f'<text x="{x + w / 2}" y="{ty + 17 + 15 * i}" class="s">{e(line)}</text>'
    if tag:
        tw = len(tag) * 7 + 14
        out += f'<rect x="{x + 10}" y="{y - 9}" width="{tw}" height="18" rx="9" fill="{stroke}"/>'
        out += f'<text x="{x + 10 + tw / 2}" y="{y + 4}" class="tag">{e(tag)}</text>'
    return out


def diamond(cx, cy, hw, hh, kind, title, sub):
    stroke, fill = C[kind]
    pts = f"{cx},{cy - hh} {cx + hw},{cy} {cx},{cy + hh} {cx - hw},{cy}"
    out = f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    out += f'<text x="{cx}" y="{cy - 2}" class="t" fill="{stroke}">{e(title)}</text>'
    out += f'<text x="{cx}" y="{cy + 15}" class="s">{e(sub)}</text>'
    return out


def arrow(pts, label=None, lx=None, ly=None, dashed=False, anchor="middle", head=True):
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    mk = ' marker-end="url(#ah)"' if head else ""
    out = f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="2"{dash}{mk}/>'
    if label:
        out += lbl(lx, ly, label, anchor)
    return out


def lbl(x, y, text, anchor="middle"):
    w = len(text) * 6.6 + 8
    rx = {"middle": x - w / 2, "start": x - 4, "end": x - w + 4}[anchor]
    return (f'<rect x="{rx}" y="{y - 13}" width="{w}" height="18" fill="#fff"/>'
            f'<text x="{x}" y="{y}" class="lbl" text-anchor="{anchor}">{e(text)}</text>')


DEFS = f"""<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker></defs>"""


STOPS = [(0.0, (8, 145, 178)), (0.5, (245, 158, 11)), (1.0, (220, 38, 38))]


def heat(t):
    """Cold cyan → amber → hot red, t in [0, 1]."""
    t = min(max(t, 0.0), 1.0)
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return "#%02x%02x%02x" % tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return "#dc2626"


def robot(x, y, t, label="", r=19):
    out = f'<circle cx="{x}" cy="{y}" r="{r}" fill="{heat(t)}" stroke="#fff" stroke-width="3"/>'
    out += f'<circle cx="{x}" cy="{y}" r="{r + 1.5}" fill="none" stroke="#0f172a" stroke-opacity=".25" stroke-width="1"/>'
    if label:
        out += f'<text x="{x}" y="{y + 4}" class="rb">{e(label)}</text>'
    return out


def colored_defs():
    out = "<defs>"
    for name, col in [("hot", "#dc2626"), ("cold", "#0891b2")]:
        out += (f'<marker id="ah-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" '
                f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>')
    return out + "</defs>"


def text(x, y, s, cls="s", anchor="middle", fill=None):
    f = f' fill="{fill}"' if fill else ""
    return f'<text x="{x}" y="{y}" class="{cls}" style="text-anchor:{anchor}"{f}>{e(s)}</text>'


def svg(vb_h, body, vb_w=1000):
    return f'<svg viewBox="0 0 {vb_w} {vb_h}" xmlns="http://www.w3.org/2000/svg">{DEFS}{body}</svg>'


# ---------- Page 1: system map ----------
def system_map():
    b = []
    # Operator console band
    b.append('<rect x="8" y="8" width="984" height="72" rx="12" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>')
    b.append('<text x="725" y="41" class="band" text-anchor="middle">OPERATOR</text>')
    b.append('<text x="725" y="57" class="band" text-anchor="middle">CONSOLE</text>')
    b.append(box(20, 22, 170, 44, "ui", "Live fleet view", "grid · robots · hazards", title_size=14))
    b.append(box(250, 22, 160, 44, "ui", "Frontier dashboard", "from Serverless Jobs", title_size=14))
    b.append(box(470, 22, 160, 44, "ui", "Reasoning log", "Nano + Ultra I/O", title_size=14))
    b.append(box(820, 22, 160, 44, "ui", "Command input", "natural language", title_size=14))

    # Runtime panel
    b.append('<rect x="8" y="92" width="984" height="388" rx="12" fill="none" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="5 5"/>')
    b.append('<text x="124" y="114" class="band">FLEET RUNTIME · FastAPI</text>')

    b.append(box(20, 160, 170, 300, "runtime", "World simulator", ["warehouse grid", "robots · humans", "hazards", "tick loop"]))
    b.append(box(250, 150, 160, 70, "s2", "Perception", ["Cosmos Reason VLM"]))
    b.append(box(250, 270, 160, 70, "runtime", "Event bus", ["sensor + scene events"]))
    b.append(box(470, 150, 160, 70, "runtime", "Precedent memory", ["Ultra + peer decisions"]))
    b.append(box(470, 270, 160, 70, "s1", "Reflex agent", ["Nemotron Nano", "action + confidence"], tag="SYSTEM 1"))
    b.append(diamond(705, 305, 50, 50, "s1", "Gate", "settled?"))
    b.append(box(820, 150, 160, 80, "s2", "Deliberator", ["Nemotron Ultra", "novel · high-stakes"], tag="SYSTEM 2"))
    b.append(box(820, 270, 160, 70, "runtime", "Action executor", ["Pydantic-validated"]))
    b.append(box(680, 390, 150, 75, "motion", "Motion planner", ["A* + CBS", "deterministic"]))
    b.append(box(250, 358, 160, 72, "peer", "Peer exchange", ["handshake on pass (B)", "countercurrent pairing (A)"], tag="SYSTEM 1.5"))

    b.append(arrow([(105, 160), (105, 68)]))
    b.append(arrow([(940, 66), (940, 148)]))
    b.append(arrow([(190, 185), (248, 185)], "frames", 219, 177))
    b.append(arrow([(190, 305), (248, 305)], "events", 219, 297))
    b.append(arrow([(330, 220), (330, 268)], "scene description", 338, 249, anchor="start"))
    b.append(arrow([(410, 305), (468, 305)]))
    b.append(arrow([(550, 220), (550, 268)], "few-shot precedents", 558, 249, anchor="start"))
    b.append(arrow([(630, 305), (653, 305)]))
    b.append(arrow([(705, 255), (705, 190), (818, 190)], "escalate", 762, 182))
    b.append(arrow([(755, 305), (818, 305)], "yes", 787, 297))
    b.append(arrow([(900, 230), (900, 268)], "decision", 908, 254, anchor="start"))
    b.append(arrow([(860, 150), (860, 128), (550, 128), (550, 148)], "new precedent", 705, 122))
    b.append(arrow([(190, 395), (248, 395)], "pass", 219, 387))
    b.append(arrow([(410, 395), (550, 395), (550, 342)], "peer precedents", 558, 375, anchor="start"))
    b.append(arrow([(410, 412), (678, 412)], "pass-by routes", 618, 404))
    b.append(arrow([(900, 340), (900, 420), (832, 420)], "goals + constraints", 892, 380, anchor="end"))
    b.append(arrow([(680, 445), (192, 445)], "collision-free trajectories", 436, 466))

    # Serverless jobs band
    b.append(f'<rect x="8" y="492" width="984" height="120" rx="12" fill="#fffbf5" stroke="{C["batch"][0]}" stroke-width="1.5" stroke-dasharray="5 5"/>')
    b.append('<text x="22" y="514" class="band">NEBIUS SERVERLESS JOBS · red-team at scale</text>')
    b.append(box(20, 528, 230, 70, "s2", "Scenario generator", ["Nemotron Super", "adversarial cases"]))
    b.append(box(310, 528, 230, 70, "batch", "Parallel headless runs", ["same runtime · sweep τ"]))
    b.append(box(600, 528, 200, 70, "batch", "Metrics", ["success · latency · $/task"]))
    b.append(box(860, 528, 120, 70, "ui", "Frontier chart", ["→ dashboard"]))
    b.append(arrow([(250, 563), (308, 563)]))
    b.append(arrow([(540, 563), (598, 563)]))
    b.append(arrow([(800, 563), (858, 563)]))
    return svg(620, "".join(b))


# ---------- Page 2: peer learning layer ----------
def peer_layer():
    b = [colored_defs()]
    # B: handshake on pass
    b.append(text(10, 22, "B · Handshake on pass (runtime)", "ptitle", "start"))
    b.append('<rect x="10" y="40" width="460" height="150" rx="14" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>')
    b.append('<line x1="20" y1="115" x2="460" y2="115" stroke="#cbd5e1" stroke-width="2" stroke-dasharray="10 8"/>')
    b.append(text(22, 56, "OUTBOUND →", "band", "start", "#b91c1c"))
    b.append(text(458, 182, "← INBOUND", "band", "end", "#0e7490"))
    for i, x in enumerate([350, 322, 294]):
        op = 1 - i * 0.3
        b.append(f'<polygon points="{x},70 {x + 9},86 {x - 9},86" fill="#f59e0b" fill-opacity="{op:.2f}" stroke="#b45309" stroke-opacity="{op:.2f}"/>')
    b.append(text(322, 104, "hazard tags fade", "ax"))
    b.append(robot(80, 80, 0.9))
    b.append(robot(420, 80, 0.9))
    b.append(robot(110, 152, 0.15))
    b.append(robot(400, 152, 0.15))
    b.append(robot(225, 80, 0.9, "out"))
    b.append(robot(250, 152, 0.15, "in"))
    b.append('<circle cx="238" cy="116" r="52" fill="none" stroke="#7c3aed" stroke-width="2" stroke-dasharray="4 4"/>')
    b.append(lbl(238, 121, "swap"))
    b.append(box(10, 222, 220, 84, "hot", "Outbound receives", ["hazards ahead", "fresh frontier precedents", "congestion"], title_size=14))
    b.append(box(250, 222, 220, 84, "cold", "Inbound receives", ["new orders", "policy delta", "map changes"], title_size=14))
    b.append(arrow([(212, 162), (140, 220)]))
    b.append(arrow([(264, 162), (340, 220)]))
    b.append(text(240, 332, "No model call · bounded payload · Cosmos called once per hazard", "s"))

    # A: countercurrent pairing
    ox = 530
    b.append(text(ox, 22, "A · Countercurrent pairing (learning)", "ptitle", "start"))
    b.append(f'<rect x="{ox}" y="56" width="460" height="56" rx="28" fill="#fef2f2" stroke="#fca5a5" stroke-width="1.5"/>')
    b.append(f'<rect x="{ox}" y="160" width="460" height="56" rx="28" fill="#ecfeff" stroke="#67e8f9" stroke-width="1.5"/>')
    b.append(text(ox + 8, 48, "TRAINED → toward the edge", "band", "start", "#b91c1c"))
    b.append(text(ox + 8, 234, "← NAIVE toward the core · warms up", "band", "start", "#0e7490"))
    xs = [ox + 50 + i * 90 for i in range(5)]
    for i, x in enumerate(xs):
        t = 0.95 - i * 0.16
        b.append(robot(x, 84, t))
        b.append(robot(x, 188, t - 0.14))
        b.append(f'<path d="M{x},108 L{x},164" stroke="#475569" stroke-width="2" marker-start="url(#ah)" marker-end="url(#ah)"/>')
    b.append(lbl(xs[0] + 6, 141, "small Δ", "start"))
    b.append(box(ox + 240, 262, 220, 60, "peer", "Pairing scheduler", ["adds pass-by waypoints", "small Δ at every pass"], title_size=14))
    b.append(arrow([(ox + 350, 262), (ox + 350, 220)]))
    return svg(345, "".join(b))


# ---------- Page 3: escalation sequence ----------
def sequence():
    parts = [
        ("Simulator", "runtime"), ("Cosmos Reason", "s2"), ("Nano reflex", "s1"),
        ("Gate", "s1"), ("Ultra", "s2"), ("Motion", "motion"), ("Memory", "runtime"),
    ]
    xs = [72 + i * 143 for i in range(len(parts))]
    b = []
    for (name, kind), x in zip(parts, xs):
        b.append(f'<line x1="{x}" y1="58" x2="{x}" y2="592" stroke="#cbd5e1" stroke-width="2" stroke-dasharray="4 5"/>')
        b.append(box(x - 64, 10, 128, 46, kind, name, title_size=14))
    S, Co, N, G, U, M, P = range(7)
    msgs = [
        (S, Co, "Camera frame from Robot 3", False),
        (Co, S, "“Person kneeling beside fallen box, aisle 4”", True),
        (S, N, "Event + local state", False),
        (P, N, "Own + peer precedents", True),
        (N, G, "Proposed: detour · confidence 0.41", False),
        (G, U, "Escalate: human present, always safety-critical", False),
        (U, G, "Halt R3 · quarantine aisle 4 · reroute R1, R5 · alert supervisor", True),
        (G, M, "Validated actions + zone constraints", False),
        (M, S, "New collision-free trajectories", True),
        (U, P, "Store decision as precedent", False),
        (P, N, "Precedent spreads robot to robot by handshake", True),
    ]
    y = 108
    for i, (a, c, label, ret) in enumerate(msgs, 1):
        x1, x2 = xs[a], xs[c]
        off = 4 if x2 > x1 else -4
        b.append(arrow([(x1, y), (x2 - off, y)], dashed=ret))
        mid = (x1 + x2) / 2
        rw = len(label) * 6.6 + 8
        cx = max(mid - rw / 2 - 8, 14)
        mid = max(mid, cx + 8 + rw / 2)
        b.append(lbl(mid, y - 9, label))
        b.append(f'<circle cx="{cx}" cy="{y - 13}" r="10" fill="#0f172a"/>')
        b.append(f'<text x="{cx}" y="{y - 9}" class="num">{i}</text>')
        y += 40
    nx1, nx2 = xs[N] - 60, xs[P] + 60
    b.append(f'<rect x="{nx1}" y="{y - 8}" width="{nx2 - nx1}" height="42" rx="8" fill="#fefce8" stroke="#ca8a04" stroke-width="1.5"/>')
    b.append(f'<text x="{(nx1 + nx2) / 2}" y="{y + 18}" class="note">Next similar non-human event → settled by Nano + peers, no Ultra call.</text>')
    return svg(596, "".join(b))


# ---------- Page 3: action schema ----------
def schema():
    b = []
    b.append(box(0, 95, 150, 60, "s2", "Model output", ["Nano or Ultra"]))
    b.append(diamond(285, 125, 70, 50, "runtime", "Pydantic", "validation"))
    b.append(box(195, 4, 180, 48, "ui", "Retry with error", ["max 2 attempts"], title_size=14))
    b.append(arrow([(150, 125), (213, 125)]))
    b.append(arrow([(285, 75), (285, 54)], "invalid", 293, 68, anchor="start"))
    b.append(arrow([(195, 28), (75, 28), (75, 93)]))
    b.append(box(410, 95, 140, 60, "runtime", "FleetAction", ["typed intent"]))
    b.append(arrow([(355, 125), (408, 125)], "valid", 381, 117))
    acts = ["goto(robot, target)", "halt(robot)", "quarantine_zone(cells, ttl)",
            "reassign_task(task, robot)", "alert_human(severity, msg)"]
    for i, a in enumerate(acts):
        cy = 22 + i * 52
        b.append(box(605, cy - 19, 240, 38, "runtime", a, title_size=13.5, mono=True))
        b.append(arrow([(550, 125), (603, cy)]))
        b.append(arrow([(845, cy), (870, 125)], head=False))
    b.append(arrow([(870, 125), (888, 125)]))
    b.append(box(890, 95, 110, 60, "motion", "Motion layer", ["+ simulator"], title_size=14))
    return svg(250, "".join(b))


# ---------- Page 4: red-team pipeline ----------
def pipeline():
    b = []
    cy = 148
    b.append(box(0, cy - 30, 110, 60, "ui", "Scenario", ["seeds"]))
    b.append(box(150, cy - 50, 205, 100, "s2", "Scenario generator", ["Nemotron Super", "blocked exits · humans in lanes", "conflicting orders", "sensor dropout"]))
    b.append(box(395, cy - 30, 105, 60, "batch", "Shard", ["across jobs"]))
    b.append(arrow([(110, cy), (148, cy)]))
    b.append(arrow([(355, cy), (393, cy)]))
    jobs = [("Job · τ = 0.3", "hybrid", "batch"), ("Job · τ = 0.5", "hybrid", "batch"), ("Job · τ = 0.7", "hybrid", "batch"),
            ("Pairing: countercurrent", "vs concurrent · vs no peers", "peer"), ("Baselines", "Nano-only · Ultra-only", "batch")]
    for i, (t, sub, kind) in enumerate(jobs):
        y = 4 + i * 59
        b.append(box(540, y, 190, 50, kind, t, [sub], title_size=14))
        b.append(arrow([(500, cy), (538, y + 25)]))
        b.append(arrow([(730, y + 25), (752, cy)], head=False))
    b.append(arrow([(752, cy), (766, cy)]))
    b.append(box(768, cy - 30, 104, 60, "runtime", "Results", ["CSV / Parquet"]))
    b.append(arrow([(872, cy), (898, cy)]))
    b.append(box(900, cy - 50, 100, 100, "ui", "Frontier", ["success", "latency", "$ / task", "warm-up"]))
    return svg(300, "".join(b))


CSS = """
@page { size: 11in 8.5in; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #fff; color: #0f172a;
  font-family: -apple-system, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif; }
.page { width: 11in; height: 8.5in; padding: 34px 40px 28px; position: relative;
  page-break-after: always; display: flex; flex-direction: column; overflow: hidden; }
.page:last-child { page-break-after: auto; }
header { display: flex; align-items: baseline; justify-content: space-between;
  border-bottom: 2px solid #0f172a; padding-bottom: 8px; margin-bottom: 14px; }
h1 { font-size: 24px; margin: 0; letter-spacing: -0.01em; }
h2 { font-size: 16px; margin: 18px 0 8px; }
.kicker { font-size: 12px; color: #64748b; letter-spacing: .08em; text-transform: uppercase; font-weight: 600; }
.lead { font-size: 13.5px; color: #334155; margin: 0 0 10px; line-height: 1.45; max-width: 9.4in; }
svg { width: 100%; height: auto; display: block; }
svg .t { font-weight: 650; text-anchor: middle; font-size: 15px; }
svg .tm { font-family: "SF Mono", Menlo, Consolas, monospace; font-weight: 600; text-anchor: middle; }
svg .s { font-size: 12.5px; fill: #334155; text-anchor: middle; }
svg .tag { font-size: 10px; font-weight: 700; fill: #fff; text-anchor: middle; letter-spacing: .06em; }
svg .band { font-size: 11px; font-weight: 700; fill: #64748b; letter-spacing: .1em; }
svg .lbl { font-size: 12.5px; font-weight: 550; fill: #0f172a; 
}
svg .num { font-size: 11px; font-weight: 700; fill: #fff; text-anchor: middle; }
svg .rb { font-size: 11px; font-weight: 700; fill: #fff; text-anchor: middle; }
svg .ptitle { font-size: 14px; font-weight: 650; fill: #0f172a; }
svg .ax { font-size: 11px; fill: #64748b; }
svg .note { font-size: 13.5px; font-weight: 600; fill: #713f12; text-anchor: middle; }
.legend { display: flex; gap: 22px; margin-top: auto; padding-top: 10px; font-size: 12px; color: #334155;
  flex-wrap: wrap; }
.legend span { display: inline-flex; align-items: center; gap: 7px; }
.sw { width: 16px; height: 16px; border-radius: 4px; border: 2px solid; display: inline-block; }
footer { position: absolute; bottom: 12px; right: 40px; font-size: 10.5px; color: #94a3b8; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #475569;
  border-bottom: 2px solid #0f172a; padding: 6px 10px; }
td { padding: 7px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; line-height: 1.35; }
td:first-child { font-weight: 650; white-space: nowrap; }
.chip { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 7px; vertical-align: 0; }
.grid { align-items: start; display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.card { border: 2px solid; border-radius: 10px; padding: 10px 14px; }
.card h3 { margin: 0 0 6px; font-family: "SF Mono", Menlo, monospace; font-size: 15px; }
.card div { font-size: 12.5px; line-height: 1.55; color: #334155; }
.card code { font-family: "SF Mono", Menlo, monospace; font-size: 12.5px; color: #0f172a; font-weight: 600; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 10px; }
.c { border: 1.5px solid #cbd5e1; border-radius: 10px; padding: 9px 12px; font-size: 12px; line-height: 1.45; color: #334155; }
.c b { display: block; color: #0f172a; font-size: 12.5px; margin-bottom: 3px; }
.principle { background: #f8fafc; border-left: 4px solid #0f172a; padding: 10px 14px; font-size: 13.5px;
  line-height: 1.45; margin-bottom: 14px; }
"""

LEGEND_ITEMS = [
    ("runtime", "Fleet runtime"),
    ("s1", "System 1 · reflex"),
    ("peer", "System 1.5 · peers"),
    ("s2", "NVIDIA models (Token Factory)"),
    ("motion", "Deterministic planning"),
    ("batch", "Serverless Jobs"),
]


def legend(dashed=False, items_list=None):
    items = "".join(
        f'<span><i class="sw" style="border-color:{C[k][0]};background:{C[k][1]}"></i>{e(t)}</span>'
        for k, t in (items_list or LEGEND_ITEMS))
    return f'<div class="legend">{items}{"<span>- - - dashed arrow = response / return</span>" if dashed else ""}</div>'


def page(n, kicker, title, body, show_legend=True, dashed=False, footer="NemoFleet Architecture", total=6, legend_items=None):
    return f"""<section class="page"><header><h1>{e(title)}</h1><div class="kicker">{e(kicker)}</div></header>
{body}{legend(dashed, legend_items) if show_legend else ""}<footer>{e(footer)} · {n} / {total}</footer></section>"""


def chip(kind):
    return f'<i class="chip" style="background:{C[kind][0]}"></i>'


resp_rows = [
    ("s2", "Perception", "Cosmos Reason", "What the camera sees, on first sighting", "~1 s", "Plan actions"),
    ("s1", "Reflex", "Nemotron Nano", "Routine responses + a confidence score", "< 1 s", "Handle safety-critical novel events alone"),
    ("peer", "Peer exchange", "Handshake + fading tags + pairing", "What the fleet already knows reaches this robot", "< 50 ms", "Override a safety escalation"),
    ("s1", "Escalation gate", "Rules + threshold τ", "Settled locally, or System 2 needed", "~0", "Generate content"),
    ("s2", "Deliberation", "Nemotron Ultra", "Novel, high-stakes decisions; task re-prioritization", "5–30 s", "Produce raw coordinates"),
    ("motion", "Motion", "A* + CBS", "Collision-free paths + pass-by waypoints", "< 10 ms", "Interpret semantics"),
    ("runtime", "Executor", "Pydantic schemas", "Whether an action is valid", "~0", "Accept malformed LLM output"),
]
resp_table = "<table><tr><th>Layer</th><th>Model / algorithm</th><th>Decides</th><th>Latency</th><th>Never does</th></tr>" + "".join(
    f"<tr><td>{chip(k)}{e(a)}</td><td>{e(b)}</td><td>{e(c)}</td><td>{e(d)}</td><td>{e(f)}</td></tr>"
    for k, a, b, c, d, f in resp_rows) + "</table>"

usage_rows = [
    ("s1", "Reflex agent", "Nemotron Nano", "Token Factory"),
    ("s2", "Deliberator", "Nemotron Ultra", "Token Factory"),
    ("s2", "Perception", "Cosmos Reason", "Token Factory or AI Cloud endpoint"),
    ("s2", "Scenario generator", "Nemotron Super", "Token Factory"),
    ("peer", "Peer exchange", "None: no model call is the point", "—"),
    ("batch", "Red-team + pairing sweeps", "—", "Serverless Jobs"),
]
usage_table = "<table><tr><th>Component</th><th>NVIDIA model</th><th>Nebius service</th></tr>" + "".join(
    f"<tr><td>{chip(k)}{e(a)}</td><td>{e(b)}</td><td>{e(c)}</td></tr>" for k, a, b, c in usage_rows) + "</table>"

modules = [
    ("runtime", "models.py", [("WorldState, Robot, Event", ""), ("FleetAction, Decision, Precedent", "")]),
    ("runtime", "sim/", [("world.py", "grid, robots, humans, tick loop"), ("proximity.py", "passes, handshakes, fading tags"),
                         ("scenarios.py", "loading + generation")]),
    ("motion", "motion/", [("astar.py", "single-agent paths"), ("cbs.py", "multi-agent conflict search")]),
    ("s2", "cognition/", [("client.py", "Token Factory client"), ("reflex.py", "Nano · System 1"),
                          ("peers.py", "payloads, provenance, TTL (B)"), ("pairing.py", "countercurrent scheduler (A)"),
                          ("deliberator.py", "Ultra · System 2"), ("gate.py", "escalation + safety overrides"),
                          ("perception.py", "Cosmos Reason"), ("memory.py", "precedent store")]),
    ("runtime", "api/", [("server.py", "/state /command /inject /tick /log")]),
    ("batch", "jobs/", [("redteam.py", "τ sweep + pairing sweep"), ("frontier.py", "aggregation + charts")]),
]


def module_cards():
    out = []
    for kind, name, files in modules:
        rows = "".join(f"<div><code>{e(f)}</code>{' — ' + e(d) if d else ''}</div>" for f, d in files)
        out.append(f'<div class="card" style="border-color:{C[kind][0]};background:{C[kind][1]}"><h3 style="color:{C[kind][0]}">{e(name)}</h3>{rows}</div>')
    out.append(f'<div class="card" style="border-color:{C["ui"][0]}"><h3>ui/</h3><div>Operator console: live view, command input, reasoning log, frontier dashboard</div></div>')
    return '<div class="grid">' + "".join(out) + "</div>"


def main(out_html):
    safety = '<div class="cards">' + "".join(f'<div class="c"><b>{e(t)}</b>{e(d)}</div>' for t, d in [
        ("Peers never override safety", "A human present, an unknown hazard class or a blocked exit always escalates to Ultra."),
        ("Provenance on every precedent", "Who decided it (Ultra or a peer), when, and how many hops. Confidence decays per hop."),
        ("Everything expires", "Precedents and hazard tags carry a TTL, so a bad lesson can’t circulate forever."),
        ("Conflicts escalate", "Ultra outranks peers. Two precedents that disagree are themselves an escalation trigger."),
    ]) + "</div>"
    pages = [
        page(1, "System map", "NemoFleet · System 1 / System 2 for robot fleets",
             '<p class="lead">A fast model on each robot handles routine events, peers share what the fleet already knows when they pass, '
             'and a large reasoning model in the cloud handles only what is novel or high-stakes. A deterministic planner owns every trajectory.</p>' + system_map()),
        page(2, "Peer learning layer · System 1.5", "Robots teach each other in passing",
             '<p class="lead">Two designs from the countercurrent options work together. <b>B</b> moves knowledge at runtime: robots swap a small payload whenever they pass. '
             '<b>A</b> shapes who passes whom, so each robot meets peers only slightly ahead of it. Most already-seen problems get settled without a cloud call.</p>'
             + peer_layer() + safety),
        page(3, "Escalation sequence", "A person enters a robot lane",
             '<p class="lead">Humans are always safety-critical, so this escalates to Ultra; the decision then spreads robot to robot by handshake.</p>'
             + sequence(), dashed=True),
        page(4, "Responsibilities and safety boundary", "Who decides what",
             '<div class="principle"><b>Principle:</b> models decide <i>what</i> should happen; the planner decides <i>how</i> to move. '
             'Every model output must pass schema validation before anything moves.</div>' + resp_table +
             '<h2>Action schema boundary</h2>' + schema()),
        page(5, "Red-team frontier", "Measuring when to escalate",
             '<p class="lead">Serverless Jobs run adversarial scenarios in parallel across escalation thresholds τ and pairing strategies: '
             'the escalation frontier, plus countercurrent vs. concurrent vs. no-peer warm-up and hazard-spread curves.</p>'
             + pipeline() + '<h2>Where NVIDIA and Nebius are used</h2>' + usage_table +
             '<p class="lead" style="margin-top:8px;font-size:12px;color:#64748b">Model IDs to be confirmed against the Token Factory catalog.</p>'),
        page(6, "Planned module layout", "Code map: nemofleet/", module_cards()),
    ]

    with open(out_html, "w") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><title>NemoFleet Architecture</title><style>{CSS}</style></head><body>{"".join(pages)}</body></html>')


if __name__ == "__main__":
    main(sys.argv[1])
