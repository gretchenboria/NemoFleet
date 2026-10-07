"""Build the NemoFleet countercurrent-options PDF (duck rete mirabile + ant trails).

Usage:
    python3 docs/build_countercurrent_pdf.py /tmp/cc.html
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \\
        --no-pdf-header-footer --print-to-pdf=docs/NemoFleet-Countercurrent-Options.pdf file:///tmp/cc.html
"""
import math
import sys

from build_architecture_pdf import C, CSS, arrow, box, e, lbl, page, svg

C["hot"] = ("#b91c1c", "#fef2f2")
C["cold"] = ("#0e7490", "#ecfeff")
C["warm"] = ("#b45309", "#fffbeb")

FOOTER = "NemoFleet Countercurrent Options"
TOTAL = 5
LEGEND = [
    ("hot", "Trained / knowledge from the core"),
    ("cold", "Naive / frontier experience"),
    ("s2", "NVIDIA models on Token Factory"),
    ("runtime", "Fleet runtime"),
]

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


# ---------- Page 1: profile chart ----------
def profile_chart():
    b = [colored_defs()]

    def panel(oy, title, hot_fn, cold_fn, cold_leftward, note):
        x0, x1, h = 44, 424, 112

        def Y(v):
            return oy + 28 + h - v * h

        out = text(x0, oy + 12, title, "ptitle", "start")
        out += f'<line x1="{x0}" y1="{oy + 24}" x2="{x0}" y2="{Y(0)}" stroke="#94a3b8" stroke-width="1.5"/>'
        out += f'<line x1="{x0}" y1="{Y(0)}" x2="{x1}" y2="{Y(0)}" stroke="#94a3b8" stroke-width="1.5"/>'
        out += text(x0 - 6, Y(1) + 4, "high", "ax", "end") + text(x0 - 6, Y(0) + 4, "low", "ax", "end")
        for fn, name, rev in [(hot_fn, "hot", False), (cold_fn, "cold", cold_leftward)]:
            xs = [i / 40 for i in range(41)]
            if rev:
                xs = xs[::-1]
            pts = " ".join(f"{x0 + u * (x1 - x0):.1f},{Y(fn(u)):.1f}" for u in xs)
            col = "#dc2626" if name == "hot" else "#0891b2"
            out += f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="3" marker-end="url(#ah-{name})"/>'
        out += text(x1, Y(0) + 15, "route →", "ax", "end")
        out += text(x1, Y(0) + 34, note, "pnote", "end")
        out += text(x1 - 62, oy + 12, "trained →", "hotlbl", "end")
        out += text(x1, oy + 12, ("← naive" if cold_leftward else "naive →"), "coldlbl", "end")
        return out

    def conc_hot(u): return 0.5 + 0.4 * math.exp(-3.2 * u)
    def conc_cold(u): return 0.5 - 0.4 * math.exp(-3.2 * u)
    def cc_hot(u): return 0.92 - 0.72 * u
    def cc_cold(u): return 0.82 - 0.72 * u

    b.append(panel(0, "Concurrent (same direction)", conc_hot, conc_cold, False,
                   "Both stall near the average."))
    b.append(panel(196, "Countercurrent (opposite directions)", cc_hot, cc_cold, True,
                   "Small gap everywhere → naive exits near expert level."))
    return svg(374, "".join(b), vb_w=440)


# ---------- Page 2: Option A, countercurrent curriculum ----------
def option_a():
    b = [colored_defs()]
    b.append(box(10, 110, 140, 260, "s2", "Core", ["Nemotron Ultra", "+ precedent memory", "", "the heart"]))
    b.append(box(850, 110, 140, 260, "cold", "Frontier", ["new zones", "new robots", "", "the ice"]))
    # channels
    b.append('<rect x="172" y="130" width="656" height="72" rx="36" fill="#fef2f2" stroke="#fca5a5" stroke-width="1.5"/>')
    b.append('<rect x="172" y="278" width="656" height="72" rx="36" fill="#ecfeff" stroke="#67e8f9" stroke-width="1.5"/>')
    b.append(text(180, 118, "TRAINED STREAM → rotates outward, runs cheaper toward the edge", "band", "start"))
    b.append(text(180, 372, "← NAIVE STREAM · warms up on the way in", "band", "start"))
    xs = [230 + i * 114 for i in range(6)]
    # rete mesh between channels
    for i in range(len(xs) - 1):
        b.append(f'<line x1="{xs[i]}" y1="208" x2="{xs[i + 1]}" y2="272" stroke="#e2e8f0" stroke-width="1.5"/>')
        b.append(f'<line x1="{xs[i + 1]}" y1="208" x2="{xs[i]}" y2="272" stroke="#e2e8f0" stroke-width="1.5"/>')
    for i, x in enumerate(xs):
        t_top = 0.95 - i * 0.13
        t_bot = t_top - 0.12
        b.append(robot(x, 166, t_top, f"T{i + 1}"))
        b.append(robot(x, 314, t_bot, f"N{6 - i}"))
        b.append(f'<path d="M{x},212 L{x},268" stroke="#475569" stroke-width="2" marker-start="url(#ah)" marker-end="url(#ah)"/>')
        b.append(lbl(x + 4, 245, "Δ small", "start") if i in (0, 5) else "")
    b.append(arrow([(150, 166), (170, 166)]))
    b.append(arrow([(828, 166), (848, 166)]))
    b.append(arrow([(850, 314), (830, 314)]))
    b.append(arrow([(172, 314), (152, 314)]))
    b.append(text(500, 30, "Rete mirabile: every robot passes many peers, each only slightly more (or less) trained", "ptitle"))
    b.append(text(500, 52, "Peer exchange settles low-confidence calls locally; only unresolved residue reaches Ultra", "s"))
    return svg(390, "".join(b))


# ---------- Page 3: Option B, ant-trail antennation ----------
def option_b():
    b = [colored_defs()]
    b.append(box(10, 10, 140, 66, "s2", "Ultra", ["reads digests only"]))
    b.append(box(10, 130, 140, 160, "runtime", "Depot", ["inbound robots", "hand over a", "pre-summarized", "digest"]))
    b.append(arrow([(80, 130), (80, 78)], "pre-warmed digest", 88, 108, anchor="start"))
    b.append(box(850, 10, 140, 66, "s2", "Cosmos", ["called once"]))
    b.append(box(850, 130, 140, 160, "cold", "Frontier", ["spill detected", "by the first", "robot to see it"]))
    b.append(arrow([(920, 130), (920, 78)], "1st sighting only", 912, 108, dashed=True, anchor="end"))
    # lane
    b.append('<rect x="170" y="130" width="660" height="160" rx="14" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>')
    b.append('<line x1="180" y1="210" x2="820" y2="210" stroke="#cbd5e1" stroke-width="2" stroke-dasharray="10 8"/>')
    b.append(text(186, 148, "OUTBOUND →", "band", "start", "#b91c1c"))
    b.append(text(814, 284, "← INBOUND", "band", "end", "#0e7490"))
    # pheromone tags near frontier, fading toward the depot
    for i, x in enumerate([800, 770, 740, 710]):
        op = 1 - i * 0.22
        b.append(f'<polygon points="{x},162 {x + 9},178 {x - 9},178" fill="#f59e0b" fill-opacity="{op:.2f}" stroke="#b45309" stroke-opacity="{op:.2f}"/>')
    b.append(text(755, 199, "hazard tags · fade over time", "ax"))
    for x in [240, 380, 620]:
        b.append(robot(x, 172, 0.9))
    for x in [300, 600, 760]:
        b.append(robot(x, 250, 0.15))
    # handshake pair
    b.append(robot(486, 172, 0.9, "out"))
    b.append(robot(514, 250, 0.15, "in"))
    b.append('<circle cx="500" cy="211" r="56" fill="none" stroke="#7c3aed" stroke-width="2" stroke-dasharray="4 4"/>')
    b.append(lbl(500, 216, "antennation"))
    # payload callouts
    b.append(box(250, 330, 230, 92, "hot", "Outbound receives", ["hazards ahead", "fresh frontier precedents", "congestion"], title_size=14))
    b.append(box(520, 330, 230, 92, "cold", "Inbound receives", ["new orders", "policy delta", "map changes"], title_size=14))
    b.append(arrow([(470, 262), (400, 328)]))
    b.append(arrow([(530, 262), (600, 328)]))
    return svg(430, "".join(b))


# ---------- Page 4: Option C, mentor mingling with thermal zones ----------
def option_c():
    b = [colored_defs()]
    b.append('<rect x="10" y="10" width="630" height="62" rx="12" fill="#fef2f2" stroke="#fca5a5" stroke-width="1.5"/>')
    b.append(text(26, 46, "CORE · Nemotron Ultra", "band", "start", "#b91c1c"))
    b.append(text(624, 46, "only what a mentor can't settle", "s", "end"))
    b.append('<rect x="10" y="86" width="630" height="62" rx="12" fill="#fffbeb" stroke="#fcd34d" stroke-width="1.5"/>')
    b.append(text(26, 122, "SYSTEM 1.5 · mentors", "band", "start", "#b45309"))
    b.append(text(624, 122, "answers its squad's questions first", "s", "end"))
    b.append('<rect x="10" y="162" width="630" height="280" rx="12" fill="#ecfeff" stroke="#67e8f9" stroke-width="1.5"/>')
    b.append(text(26, 186, "EDGE · Nano only · kept cold on purpose", "band", "start", "#0e7490"))
    squads = [(30, "Squad A · graduated", 0.72, False), (235, "Squad B · mentored now", 0.38, True), (440, "Squad C · next", 0.05, False)]
    for sx, name, t, mentored in squads:
        b.append(f'<rect x="{sx}" y="205" width="185" height="180" rx="12" fill="#fff" stroke="#94a3b8" stroke-width="1.5"/>')
        b.append(text(sx + 92, 373, name, "ptitle"))
        pts = [(sx + 40, 250), (sx + 145, 250), (sx + 92, 330)]
        for (x, y) in pts:
            b.append(robot(x, y, t))
        if mentored:
            mx, my = sx + 92, 268
            for (x, y) in pts:
                b.append(f'<line x1="{x}" y1="{y}" x2="{mx}" y2="{my}" stroke="#475569" stroke-width="1.5" stroke-dasharray="3 3"/>')
            b.append(robot(mx, my, 1.0, "M", r=21))
            b.append(arrow([(mx, my - 24), (mx, 74)], "only if mentor unsure", mx + 8, 196, anchor="start"))
    b.append('<path d="M380,389 C 420,424 500,424 532,391" fill="none" stroke="#b91c1c" stroke-width="2.5" marker-end="url(#ah-hot)"/>')
    b.append(lbl(456, 436, "rotate when warm"))
    # warm-up inset
    ox, oy, w, h = 690, 30, 290, 300
    b.append(f'<rect x="{ox - 20}" y="{oy - 20}" width="{w + 40}" height="{h + 110}" rx="12" fill="#fff" stroke="#cbd5e1" stroke-width="1.5"/>')
    b.append(text(ox + w / 2, oy + 4, "Squad escalation rate over time", "ptitle"))
    x0, y0, y1 = ox + 30, oy + h, oy + 30
    b.append(f'<line x1="{x0}" y1="{y1}" x2="{x0}" y2="{y0}" stroke="#94a3b8" stroke-width="1.5"/>')
    b.append(f'<line x1="{x0}" y1="{y0}" x2="{ox + w}" y2="{y0}" stroke="#94a3b8" stroke-width="1.5"/>')
    pts = " ".join(f"{x0 + u * (w - 30):.1f},{y0 - (h - 40) * (0.08 + 0.85 * math.exp(-3.5 * u)):.1f}" for u in [i / 40 for i in range(41)])
    b.append(f'<polyline points="{pts}" fill="none" stroke="#0891b2" stroke-width="3"/>')
    thr_y = y0 - (h - 40) * 0.2
    b.append(f'<line x1="{x0}" y1="{thr_y}" x2="{ox + w}" y2="{thr_y}" stroke="#b45309" stroke-width="1.5" stroke-dasharray="5 4"/>')
    b.append(text(ox + w, thr_y - 6, "graduation threshold", "ax", "end"))
    rot_x = x0 + (w - 30) * 0.42
    b.append(f'<line x1="{rot_x}" y1="{y1}" x2="{rot_x}" y2="{y0}" stroke="#b91c1c" stroke-width="1.5" stroke-dasharray="5 4"/>')
    b.append(text(rot_x + 6, y1 + 12, "mentor rotates", "ax", "start", "#b91c1c"))
    b.append(text(x0 - 6, y1 + 4, "high", "ax", "end") + text(x0 - 6, y0 + 4, "low", "ax", "end"))
    b.append(text(ox + w / 2 + 15, y0 + 22, "time with mentor →", "ax"))
    b.append(text(ox + w / 2, y0 + 50, "Rotate the mentor once the squad", "s"))
    b.append(text(ox + w / 2, y0 + 66, "drops below threshold.", "s"))
    return svg(450, "".join(b))


EXTRA_CSS = """
svg .rb { font-size: 11px; font-weight: 700; fill: #fff; text-anchor: middle; }
svg .ptitle { font-size: 13.5px; font-weight: 650; fill: #0f172a; }
svg .pnote { font-size: 12px; font-style: italic; fill: #334155; }
svg .ax { font-size: 11px; fill: #64748b; }
svg .hotlbl { font-size: 12px; font-weight: 700; fill: #dc2626; }
svg .coldlbl { font-size: 12px; font-weight: 700; fill: #0891b2; }
.cols { display: grid; grid-template-columns: 1.35fr 1fr; gap: 26px; align-items: start; }
.map td:first-child { color: #0f172a; }
.map td { padding: 5px 9px; font-size: 12px; }
.map th { padding: 5px 9px; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 10px; }
.cards.three { grid-template-columns: repeat(3, 1fr); }
.c { border: 1.5px solid #cbd5e1; border-radius: 10px; padding: 9px 12px; font-size: 12px; line-height: 1.45; color: #334155; }
.c b { display: block; color: #0f172a; font-size: 12.5px; margin-bottom: 3px; }
.c.metric { border-color: #7c3aed; background: #faf5ff; }
.breaks { margin-top: 12px; border: 1.5px dashed #b45309; background: #fffbeb; border-radius: 10px;
  padding: 9px 14px; font-size: 12.5px; line-height: 1.45; color: #422006; }
.cmp td:first-child { white-space: nowrap; color: #475569; font-weight: 650; }
.cmp td { font-size: 12px; padding: 6px 10px; }
.cmp th { font-size: 12px; text-transform: none; letter-spacing: 0; color: #0f172a; }
.rec { margin-top: 14px; display: grid; grid-template-columns: 1.3fr 1fr; gap: 14px; }
.rec .c { font-size: 12.5px; }
.rec .c.pick { border: 2px solid #0f172a; background: #f8fafc; }
"""


def pg(n, kicker, title, body):
    return page(n, kicker, title, body, footer=FOOTER, total=TOTAL, legend_items=LEGEND)


def cards(items, cls=""):
    return f'<div class="cards {cls}">' + "".join(
        f'<div class="c{" metric" if k == "metric" else ""}"><b>{e(t)}</b>{e(d)}</div>' for k, t, d in items) + "</div>"


MAPPING = [
    ("Heat", "Competence: precedents, calibrated policies, resolved anomalies"),
    ("Warm arterial blood", "Trained (“hot”) robots, or knowledge flowing out from the core"),
    ("Cold venous blood", "Naive (“cold”) robots, or raw unresolved experience flowing back"),
    ("Body core and heart", "Cloud: Nemotron Ultra + precedent memory (expensive heat)"),
    ("Foot on ice", "Frontier: new zones and new deployments"),
    ("Heat lost to the ice", "GPU and tokens spent re-deriving what the fleet already knows"),
    ("Countercurrent flow", "Gradient-ordered pairing: every encounter transfers something new"),
    ("Rete mirabile", "Dense peer-to-peer exchange mesh that multiplies contact points"),
    ("Ant antennation", "Handshake when robots pass: “what’s ahead” ⇄ “what’s behind”"),
]


def main(out_html):
    map_table = '<table class="map"><tr><th>Biology</th><th>NemoFleet</th></tr>' + "".join(
        f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in MAPPING) + "</table>"
    p1 = pg(1, "From biology to fleet learning", "Cold feet, warm core",
            '<p class="lead">A duck keeps its core warm and its feet cold by running warm and cold blood side by side in opposite directions. '
            'Ants on a trail swap news every time they pass. Both move value <i>locally, along a gradient</i> instead of through a central pump. '
            'NemoFleet can do the same with knowledge and GPU spend.</p>'
            f'<div class="cols"><div>{map_table}</div><div>{profile_chart()}</div></div>'
            '<div class="breaks"><b>Where the analogy breaks.</b> Heat is used up when it moves; knowledge is not, since sharing a precedent doesn’t make the '
            'trained robot forget it. So the quantity actually conserved is <b>compute and energy</b>: every exchange that settles a question locally is an Ultra call '
            'not made. What is scarce in each encounter is contact time and context budget. That is why the gradient matters: each pass should carry a small, relevant difference.</div>')

    p2 = pg(2, "Option A · learning level", "Countercurrent curriculum",
            option_a() + cards([
                ("", "1 · Enter cold", "New robots enter at the frontier and travel toward the core. Trained robots rotate outward, toward the edge."),
                ("", "2 · Small steps", "Each robot first meets peers only slightly more trained, then progressively more expert ones: a built-in curriculum."),
                ("", "3 · Settle locally", "Peer exchange (Nano + shared precedents) settles low-confidence calls. Only the unresolved residue reaches Ultra."),
                ("metric", "Experiment", "Warm-up speed and Ultra calls per novel event: countercurrent vs. concurrent (random pairing) vs. central-only."),
            ]))

    p3 = pg(3, "Option B · runtime level", "Ant-trail antennation",
            option_b() + cards([
                ("", "Handshake on pass", "Robots moving in opposite directions swap a small payload when they pass: what’s ahead for one, what’s behind for the other."),
                ("", "Pheromone tags", "Hazards are tagged on map cells and fade over time, so stale warnings expire on their own."),
                ("", "Pay once", "Only the first robot to see a spill calls Cosmos; the rest learn it by handshake. The depot sends Ultra a digest, not a raw stream."),
                ("metric", "Experiment", "Cosmos + Ultra calls per hazard, and how fast a new hazard reaches the whole fleet, vs. cloud-broadcast."),
            ]))

    p4 = pg(4, "Option C · organization level", "Mentor mingling with thermal zones",
            option_c() + cards([
                ("", "Cold edge by design", "Edge robots run Nano only. Heavy compute stays in the core, like the duck keeping heat in its body."),
                ("", "System 1.5", "One trained robot per squad answers its peers first. Naive robots learn from the mentor’s decisions and warm up."),
                ("", "Rotate the heat", "When the squad drops below the graduation threshold, the mentor moves to the next cold squad."),
                ("metric", "Experiment", "Compute cost per task by zone, and squad warm-up time vs. rotation interval."),
            ]))

    rows = [
        ("Biological model", "Duck rete mirabile", "Ant trail antennation", "Duck thermal zoning"),
        ("Mechanism", "Gradient-ordered peer exchange", "Handshake when robots pass + fading map tags", "Embedded mentor per squad, rotated"),
        ("What it saves", "Ultra calls on already-solved problems", "Cosmos + Ultra calls per hazard; raw-stream bandwidth", "Compute at the edge"),
        ("Demo visibility", "Medium: shows best as a chart", "High: visible on the map in seconds", "Medium: visible squads + rotation"),
        ("Build effort", "Medium: pairing scheduler + memory sharing", "Medium: proximity trigger + payload + tags", "Low: one extra escalation tier"),
        ("Risk", "Bad precedents spread too", "Stale or conflicting news", "Mentor becomes a bottleneck"),
        ("Headline metric", "Warm-up speed; Ultra calls per novel event", "Calls per hazard; fleet-wide spread time", "$ per task by zone; warm-up time"),
    ]
    cmp_table = ('<table class="cmp"><tr><th></th><th>A · Countercurrent curriculum</th><th>B · Ant-trail antennation</th>'
                 '<th>C · Mentor mingling</th></tr>' + "".join(
                     f"<tr><td>{e(r[0])}</td><td>{e(r[1])}</td><td>{e(r[2])}</td><td>{e(r[3])}</td></tr>" for r in rows) + "</table>")
    p5 = pg(5, "Comparison", "Which one to build",
            cmp_table +
            '<div class="rec"><div class="c pick"><b>Recommendation: B on screen, A in the numbers</b>'
            'Use ant-trail antennation as the visible demo mechanic: judges understand it in five seconds when two robots pass and the hazard spreads. '
            'Back it with Option A’s countercurrent vs. concurrent experiment as the quantitative result. Both run on the existing Serverless Jobs frontier pipeline. '
            'Option C is the simplest fallback if time runs short.</div>'
            '<div class="c"><b>Where it plugs into the architecture</b>'
            '<code>cognition/memory.py</code>: shareable precedents with provenance<br>'
            '<code>cognition/gate.py</code>: ask a peer or mentor before Ultra<br>'
            '<code>sim/world.py</code>: proximity events and fading map tags<br>'
            '<code>jobs/redteam.py</code>: pairing strategy as a sweep dimension</div></div>')

    with open(out_html, "w") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><title>NemoFleet Countercurrent Options</title>'
                f'<style>{CSS}{EXTRA_CSS}</style></head><body>{p1}{p2}{p3}{p4}{p5}</body></html>')


if __name__ == "__main__":
    main(sys.argv[1])
