"""NemoFleet architecture, today vs. next: a multi-page PDF drawn with matplotlib.

Usage (matplotlib in any env; the repo's pip is not used):
    uv venv /tmp/nf-venv && VIRTUAL_ENV=/tmp/nf-venv uv pip install matplotlib
    /tmp/nf-venv/bin/python docs/build_arch_compare_pdf.py docs/NemoFleet-Architecture-Today-vs-Next.pdf [--png DIR]

Status of every component reflects the repo and live site on 2026-10-08.
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "pdf.fonttype": 42,
})

W, H = 160, 90                      # drawing units per page (16 x 9 in)
INK, MUTED, LINE, BG = "#16202a", "#5b6670", "#d5dbe1", "#f7f8f5"
NV, NB, CF = "#5f8f00", "#a3c400", "#f38020"   # NVIDIA green, Nebius lime, Cloudflare orange
STATUS = {                          # status -> (edge, fill, label)
    "live": ("#2e8a4a", "#e9f6ee", "LIVE"),
    "wired": ("#2563eb", "#eaf1ff", "WIRED"),
    "progress": ("#c27c0e", "#fff4dc", "IN PROGRESS"),
    "planned": ("#8a94a0", "#f3f4f6", "PLANNED"),
    "sim": ("#7c5cc4", "#f1ecfb", "SIMULATED"),
}
LAYER = {"robot": "#7c5cc4", "cf": CF, "nebius": NB, "nvidia": NV, "store": "#0e8579", "tool": "#5b6670", "ext": "#b45309"}


def page(title, kicker, sub=None):
    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    fig.patch.set_facecolor(BG)
    ax.add_patch(Rectangle((0, H - 1.0), W * 0.5, 1.0, color=NV, lw=0))
    ax.add_patch(Rectangle((W * 0.5, H - 1.0), W * 0.5, 1.0, color=NB, lw=0))
    ax.text(4, H - 5.2, kicker.upper(), fontsize=10, color=MUTED, fontweight="bold", family="monospace")
    ax.text(4, H - 9.6, title, fontsize=25, color=INK, fontweight="bold")
    if sub:
        ax.text(4, H - 13.2, sub, fontsize=11.5, color=MUTED)
    ax.text(W - 4, 2.2, "NemoFleet · Nebius × NVIDIA Global AI Hackathon · Physical AI · 2026-10-08", fontsize=8.5, color=MUTED, ha="right")
    return fig, ax


def badge(ax, x, y, status, size=6.6):
    edge, fill, label = STATUS[status]
    ax.text(x, y, label, fontsize=size, color=edge, fontweight="bold", ha="right", va="center", family="monospace",
            bbox=dict(boxstyle="round,pad=0.25,rounding_size=0.6", fc=fill, ec=edge, lw=0.8))


def box(ax, x, y, w, h, title, lines=(), status=None, layer=None, title_size=10.5, line_size=8.2, dashed=False, badge_at="top"):
    edge, fill, _ = STATUS[status] if status else (LINE, "#ffffff", "")
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2", fc="#ffffff" if status != "planned" else "#fbfbfc",
                                ec=edge, lw=1.3, ls=(0, (4, 3)) if dashed or status == "planned" else "-"))
    if layer:
        ax.add_patch(FancyBboxPatch((x, y), 0.9, h, boxstyle="round,pad=0,rounding_size=0.45", fc=LAYER[layer], ec="none"))
    ax.text(x + 2.0, y + h - 2.3, title, fontsize=title_size, color=INK, fontweight="bold", va="center")
    for i, ln in enumerate(lines):
        ax.text(x + 2.0, y + h - 5.1 - i * 2.45, ln, fontsize=line_size, color=MUTED, va="center")
    if status:
        badge(ax, x + w - 1.0, y + h - 2.3 if badge_at == "top" else y + 1.9, status)


def region(ax, x, y, w, h, label, color, sub=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.8", fc=color + "14", ec=color + "88", lw=1.1))
    ax.text(x + 1.6, y + h - 1.9, label.upper(), fontsize=8.6, color=color, fontweight="bold", family="monospace", va="center")
    if sub:
        ax.text(x + w - 1.6, y + h - 1.9, sub, fontsize=7.6, color=MUTED, ha="right", va="center")


def arrow(ax, a, b, label=None, color=INK, style="-|>", rad=0.0, dashed=False, lw=1.3, lpos=0.5, loff=(0, 0.9)):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=11, color=color, lw=lw,
                                 connectionstyle=f"arc3,rad={rad}", ls=(0, (4, 3)) if dashed else "-", shrinkA=2, shrinkB=2))
    if label:
        mx, my = a[0] + (b[0] - a[0]) * lpos + loff[0], a[1] + (b[1] - a[1]) * lpos + loff[1]
        ax.text(mx, my, label, fontsize=7.4, color=color, ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.18", fc=BG, ec="none"))


def legend(ax, x, y):
    for i, k in enumerate(["live", "wired", "progress", "planned", "sim"]):
        badge(ax, x + 13 * i + 11, y, k, size=7.2)


# ---------------------------------------------------------------- pages
def cover(pdf):
    fig, ax = page("Architecture: today and next", "NemoFleet · system design", None)
    ax.texts[-1].remove()
    ax.text(4, 62, "One hazard. One Ultra call.\nThe whole fleet knows.", fontsize=40, color=INK, fontweight="bold", va="top", linespacing=1.1)
    ax.text(4, 41, "Decision-making for robot fleets in warehouses and data centers: Nemotron 3 Ultra decides a new hazard once,\n"
                   "fleet memory stores the decision by map cell, and every robot after that reuses it through Nemotron 3 Nano.\n"
                   "People in the lane are never reused. Night Shift turns each day's decisions into tomorrow's reflexes.",
            fontsize=13, color=MUTED, va="top", linespacing=1.55)
    stats = [("Ultra decision", "1.1–1.9 s", "per call, live site"), ("Gemma 4 perception", "0.7–1.2 s", "per frame, own H200 endpoint"),
             ("Schema-valid", "100%", "Nano + Ultra decisions"), ("Repeat sighting", "0 Ultra calls", "settled by fleet memory")]
    for i, (k, v, s) in enumerate(stats):
        x = 4 + i * 38
        ax.add_patch(FancyBboxPatch((x, 14), 35, 13, boxstyle="round,pad=0,rounding_size=1.2", fc="#ffffff", ec=LINE, lw=1))
        ax.text(x + 2, 24.2, k.upper(), fontsize=8.5, color=MUTED, fontweight="bold", family="monospace")
        ax.text(x + 2, 19.6, v, fontsize=22, color=INK, fontweight="bold")
        ax.text(x + 2, 16.0, s, fontsize=9, color=MUTED)
    ax.text(4, 9.0, "Measured 2026-10-08 on nemofleet.pages.dev, both scenarios. Robots, floors and camera frames are simulated; every model call is real.", fontsize=9.5, color=MUTED)
    ax.text(4, 6.4, "STATUS KEY", fontsize=8, color=MUTED, fontweight="bold", family="monospace")
    legend(ax, 14, 6.6)
    pdf.savefig(fig); return fig


def today(pdf):
    fig, ax = page("Today: what runs, end to end", "Current architecture · 2026-10-08",
                   "Every box is in the repo or the live deployment. Arrows follow one scenario event from the robot to a fleet action.")
    legend(ax, 92, H - 9.4)

    # left: simulated world + operator
    region(ax, 3, 18, 27, 56, "Robots & operator", LAYER["robot"])
    box(ax, 5, 61, 23, 10, "Scenario events", ["scenarios/*.json · 7 events", "warehouse spill · DC coolant leak"], "sim", "robot")
    box(ax, 5, 48.5, 23, 10, "Camera frames", ["rendered 1024×572 JPEGs", "4 per site · map cell per event"], "sim", "robot")
    box(ax, 5, 36, 23, 10, "Floor simulation", ["canvas 2D · A* + CBS planner", "zones/halts drawn from KV"], "sim", "robot")
    box(ax, 5, 20.5, 23, 13, "Operator", ["landing page · /console", "Run scenario · alarms · actions", "Night Shift · τ slider"], "live", "robot")

    # cloudflare
    region(ax, 33, 18, 26, 56, "Cloudflare", LAYER["cf"], "Pages · Functions")
    box(ax, 35, 58, 22, 13, "Pages static site", ["landing · console · video · docs", "build.cjs (Node) → site/dist", "live numbers via /api/state"], "live", "cf")
    box(ax, 35, 36, 22, 19, "Pages Functions API", ["functions/api/[[path]].js", "scenario start / step / finish", "state · alarms · actions", "episodes · night-shift/replay", "health · 15 s perception timeout"], "live", "cf")
    box(ax, 35, 20.5, 22, 12.5, "Fleet memory stores", ["D1  precedents by map cell · calls", "KV  hazard tags · zones · halts (TTL)", "R2  raw call + perception bodies"], "live", "store")

    # decision pipeline
    region(ax, 62, 18, 40, 56, "Decision pipeline (per event)", INK)
    steps = [
        ("1  See", ["Gemma 4 26B-A4B → hazards, person, path, action"], "live", 63.5),
        ("2  Recall", ["fleet memory: non-safety Ultra precedent for this cell?"], "live", 55.5),
        ("3  Reflex", ["Nemotron 3 Nano · precedent in prompt · confidence"], "live", 47.5),
        ("4  Gate", ["person / new hazard / conf < τ  →  Ultra"], "live", 39.5),
        ("5  Deliberate", ["Nemotron 3 Ultra · stores precedent by cell"], "live", 31.5),
        ("6  Act", ["strict schema + validate · retry once · safe stop", "actions → D1/KV · alarms · peer handoff copies"], "live", 20.5),
    ]
    for t, ls, st, y in steps:
        box(ax, 64, y, 36, 6.6 if len(ls) == 1 else 9.0, t, ls, st, "nvidia" if t[3] in "35" else None, title_size=10)
    for y0, y1 in [(63.5, 62.1), (55.5, 54.1), (47.5, 46.1), (39.5, 38.1), (31.5, 29.5)]:
        arrow(ax, (82, y0), (82, y1), lw=1.1)

    # nebius
    region(ax, 105, 18, 52, 56, "Nebius", "#6e8a00", "Token Factory · Serverless AI")
    box(ax, 107, 54.5, 23.5, 16.5, "Token Factory", ["Nemotron 3 Ultra 550B-A55B", "Nemotron 3 Nano 30B-A3B", "Responses API · strict json_schema", "Gemma 3 27B (fallback option)"], "live", "nebius", line_size=7.9)
    box(ax, 132, 54.5, 23, 16.5, "Serverless AI Endpoint", ["google/gemma-4-26B-A4B-it", "vLLM v0.30.0 · 1× H200", "token auth · per-hour billing", "use_perception.cjs switch"], "live", "nebius", line_size=7.9)
    box(ax, 107, 36, 23.5, 15.5, "Cosmos3 Reasoner", ["Token Factory dedicated", "4× H200 · $0.37/min", "config option; endpoint", "stuck \"starting\" (HTTP 429)"], "wired", "nvidia", line_size=7.9)
    box(ax, 132, 36, 23, 15.5, "Dream job", ["Nebius Serverless Job", "Cosmos-Predict2.5-2B · 1× H200", "6 clips · 5.8 s · 1280×704", "→ private HF dataset"], "progress", "nvidia", line_size=7.9)
    box(ax, 107, 20.5, 48, 12.5, "Night Shift (today)", ["Replay: Ultra re-judges Nano decisions → verdicts + disagreement rate in D1   ·   LIVE",
                                                         "Dream: first Cosmos futures generated; not yet scored by the gate   ·   IN PROGRESS",
                                                         "Gate · Consolidate (LoRA) · MLflow lineage   ·   PLANNED"], None, "nebius", line_size=8)

    # flows
    arrow(ax, (28, 66), (35, 64.5), "events", LAYER["robot"])
    arrow(ax, (28, 26), (35, 62), "UI", LAYER["robot"], rad=-0.25, lpos=0.35, loff=(-1.5, 0))
    arrow(ax, (57, 46), (64, 66.5), "step i", INK, rad=-0.15)
    arrow(ax, (100, 68.5), (141, 71), "camera frame → Gemma 4", "#6e8a00", rad=-0.18, lpos=0.62, loff=(0, 2.2))
    arrow(ax, (100, 51), (107, 62), "Nano", NV, rad=-0.2, lpos=0.4)
    arrow(ax, (100, 35), (107, 59), "Ultra", NV, rad=-0.25, lpos=0.4, loff=(1.6, 0))
    arrow(ax, (64, 58.5), (57, 26), "D1 lookup", LAYER["store"], rad=0.18, lpos=0.62, loff=(-2.5, 0))
    arrow(ax, (64, 24), (57, 24), "write", LAYER["store"])

    # tooling strip
    ax.add_patch(FancyBboxPatch((3, 5.5), 154, 9.5, boxstyle="round,pad=0,rounding_size=1.4", fc="#ffffff", ec=LINE, lw=1))
    ax.text(5, 12.5, "TOOLING & OPS", fontsize=8.6, color=MUTED, fontweight="bold", family="monospace", va="center")
    tools = ["Node 20+ (tools/*.cjs)", "wrangler (Pages · D1 · KV · R2)", "nebius CLI (endpoints · jobs)", "uv · Python 3.10/3.12",
             "Hugging Face (weights · dataset)", "puppeteer-core + Chrome (QA: 87 checks)", "preflight.cjs · use_perception.cjs", "GitHub (private until ready)"]
    for i, t in enumerate(tools):
        ax.text(5 + (i % 4) * 38.5, 9.6 - (i // 4) * 2.6, "▸ " + t, fontsize=8.6, color=INK, va="center")
    pdf.savefig(fig); return fig


def future(pdf):
    fig, ax = page("Next: the fleet that learns overnight", "Future state",
                   "Same decision core. The robot gets the reflex on-device, memory gets smarter, and Night Shift closes the loop on Nebius every night.")
    legend(ax, 92, H - 9.4)

    region(ax, 3, 18, 34, 56, "Robot edge", LAYER["robot"], "Jetson-class device")
    box(ax, 5, 59.5, 30, 11.5, "On-device reflex", ["Nemotron Nano + nightly LoRA from Night Shift", "runs without the network", "(today: Nano on Token Factory)"], "planned", "nvidia")
    box(ax, 5, 45.5, 30, 11.5, "Offline peer cache", ["dead-zone mode: only what peers", "handed over · hop count · TTL", "A/B: with vs. without handshakes"], "planned", "robot")
    box(ax, 5, 31.5, 30, 11.5, "Sensors & bridge", ["real camera + lidar via ROS 2", "map cell from localization", "replaces rendered frames"], "planned", "robot")
    box(ax, 5, 20.5, 30, 8.5, "Planner", ["A* + CBS on robot · owns all motion"], "sim", "robot")

    region(ax, 40, 18, 40, 56, "Fleet core (cloud)", INK, "Cloudflare · Token Factory")
    box(ax, 42, 59.5, 36, 11.5, "Perception", ["Gemma 4 (live) · Cosmos Reason2 / Cosmos3", "video clips, not single frames", "auto-failover between endpoints"], "progress", "nvidia")
    box(ax, 42, 45.5, 36, 11.5, "Fleet memory v2", ["cell key + embedding match", "Qwen3-Embedding-8B on Token Factory", "precedent conflicts → Ultra"], "planned", "store")
    box(ax, 42, 31.5, 36, 11.5, "Gate + Ultra", ["Nemotron 3 Ultra for new / unsafe / unsure", "τ set nightly from replay disagreement", "Super as latency fallback"], "live", "nvidia")
    box(ax, 42, 20.5, 36, 8.5, "Ops", ["MLflow lineage · budget + idle-GPU alarms"], "planned", "tool")

    region(ax, 83, 18, 74, 56, "Night Shift on Nebius (every night)", "#6e8a00", "Serverless Jobs fan-out")
    stages = [
        ("01 Replay", ["Token Factory batch", "Ultra re-judges every", "Nano decision"], "live"),
        ("02 Dream", ["Cosmos-Predict2.5 futures", "Cosmos-Transfer2.5", "sim → photoreal variants"], "progress"),
        ("03 Gate", ["variants → perception →", "Nano/Ultra; keep lessons", "with 0 safety regressions"], "planned"),
        ("04 Consolidate", ["LoRA fine-tune of Nano", "H200 job · MLflow", "promote only if better"], "planned"),
    ]
    for i, (t, ls, st) in enumerate(stages):
        x = 85 + i * 18
        box(ax, x, 50, 16.5, 19, t, ls, st, "nebius", title_size=10, line_size=7.8, badge_at="bottom")
        if i < 3:
            arrow(ax, (x + 16.5, 59.5), (x + 18, 59.5), lw=1.4, color="#6e8a00")
    box(ax, 85, 33.5, 34, 12.5, "Promote", ["new Nano adapter → Serverless Endpoint (vLLM)", "and pushed to robots before the morning shift", "rollback = previous adapter (one click)"], "planned", "nebius", line_size=7.9)
    box(ax, 121, 33.5, 34, 12.5, "Measured every night", ["Ultra calls per 100 events (should fall)", "confident-mistake rate (must not rise)", "safety incidents: 0 in both arms"], "planned", "tool", line_size=7.9)
    box(ax, 85, 20.5, 70, 10, "Data", ["D1 call log + precedents → batch inputs · R2 raw bodies · HF dataset of Dream clips · MLflow runs and adapters"], None, "store", line_size=8.3)

    arrow(ax, (35, 65), (42, 65), "frames / clips", LAYER["robot"])
    arrow(ax, (42, 36), (35, 36), "actions", NV, loff=(0, 1.2))
    arrow(ax, (78, 37), (85, 59), "day's calls", "#6e8a00", rad=-0.2, lpos=0.45)
    arrow(ax, (85, 41), (78, 41), "adapter", "#6e8a00", dashed=True, loff=(0, 1.2))

    ax.add_patch(FancyBboxPatch((3, 5.5), 154, 9.5, boxstyle="round,pad=0,rounding_size=1.4", fc="#ffffff", ec=LINE, lw=1))
    ax.text(5, 12.4, "WHAT CHANGES", fontsize=8.6, color=MUTED, fontweight="bold", family="monospace", va="center")
    ax.text(5, 9.4, "Today the fleet remembers within a day (precedents with a 24 h expiry). Next, Night Shift turns those decisions — plus thousands of Cosmos-imagined variants —\n"
                    "into a better reflex model, so tomorrow Nano settles more on its own, Ultra is called less, and nothing about people is ever learned away.",
            fontsize=9.6, color=INK, va="center", linespacing=1.5)
    pdf.savefig(fig); return fig


def compare(pdf):
    fig, ax = page("Today vs. next, component by component", "Comparison")
    rows = [
        ("Perception", "Gemma 4 26B-A4B on own Serverless Endpoint (vLLM, H200); Cosmos3 wired", "live", "Video clips; Cosmos Reason2 / Cosmos3 with auto-failover", "progress"),
        ("Reflex", "Nemotron 3 Nano 30B-A3B on Token Factory, strict schema", "live", "Nano + nightly LoRA on-device and on a vLLM endpoint", "planned"),
        ("Deliberation", "Nemotron 3 Ultra 550B-A55B; new / person / conf < τ", "live", "Same, τ tuned nightly; Super as latency fallback", "planned"),
        ("Fleet memory", "Precedents keyed by map cell in D1, 24 h expiry, cross-run", "live", "Cell + embedding match (Qwen3-Embedding-8B); conflict → Ultra", "planned"),
        ("Peer handoff", "Copies precedents with hop count in D1 + KV tags", "live", "Offline dead-zone cache on the robot; measured A/B", "planned"),
        ("Safety", "Person → Ultra always; schema + retry + safe stop; never reused", "live", "Unchanged; plus gate: zero safety regressions per adapter", "planned"),
        ("Night Shift replay", "Ultra re-judges Nano decisions, verdicts in D1", "live", "Token Factory batch over the whole day", "planned"),
        ("Night Shift dream", "Cosmos-Predict2.5-2B job: 6 futures from camera frames", "progress", "Fan-out of hundreds of variants + Cosmos-Transfer2.5", "planned"),
        ("Gate & consolidate", "—", "planned", "Score variants; LoRA fine-tune of Nano; MLflow; promote/rollback", "planned"),
        ("Robots & sensors", "Simulated robots, rendered frames, canvas floor", "sim", "ROS 2 bridge, real camera + lidar, Jetson-class edge", "planned"),
        ("Operator UX", "Console: runs, alarms, actions, memory KPIs; landing with live stats", "live", "Clip playback, Dream verdicts, budget + idle-GPU alarms", "progress"),
        ("Ops & QA", "QA suite (87 checks), preflight, perception switch, wrangler, nebius CLI", "live", "MLflow lineage, nightly report, cost dashboard", "planned"),
    ]
    x0, x1, x2, x3, x4 = 4, 30, 82, 96, 148
    y = H - 17
    for x, t in [(x0, "COMPONENT"), (x1, "TODAY"), (x3, "NEXT")]:
        ax.text(x, y, t, fontsize=9, color=MUTED, fontweight="bold", family="monospace", va="center")
    y -= 2.2
    for i, (c, t, ts, n, ns) in enumerate(rows):
        rh = 5.45
        if i % 2 == 0:
            ax.add_patch(Rectangle((3, y - rh + 0.6), 154, rh, fc="#ffffff", ec="none"))
        cy = y - rh / 2 + 0.6
        ax.text(x0, cy, c, fontsize=10.2, color=INK, fontweight="bold", va="center")
        ax.text(x1, cy, t, fontsize=9, color=INK, va="center")
        badge(ax, x2 + 11, cy, ts, size=6.8)
        ax.text(x3, cy, n, fontsize=9, color=INK, va="center")
        badge(ax, x4 + 9, cy, ns, size=6.8)
        y -= rh
    pdf.savefig(fig); return fig


def stack(pdf):
    fig, ax = page("The whole tech stack", "Inventory", "Everything NemoFleet uses today, grouped by layer. Status as of 2026-10-08.")
    groups = [
        ("NVIDIA models", NV, [("Nemotron 3 Ultra 550B-A55B", "deliberation · replay", "live"), ("Nemotron 3 Nano 30B-A3B", "reflex · memory reuse", "live"),
                                ("Nemotron 3 Super 120B-A12B", "preflight · scenario gen", "wired"), ("Cosmos-Predict2.5-2B", "Dream: futures", "progress"),
                                ("Cosmos3 Super Reasoner", "perception option", "wired"), ("Cosmos-Guardrail1", "Cosmos safety filter", "progress")]),
        ("Other models", "#b45309", [("Gemma 4 26B-A4B-it", "perception (active)", "live"), ("Gemma 3 27B-it", "perception fallback", "wired"),
                                      ("Qwen3-Embedding-8B", "memory v2 matching", "planned"), ("Cosmos-Transfer2.5-2B", "sim → real variants", "planned")]),
        ("Nebius", "#6e8a00", [("Token Factory", "Responses API · strict schema", "live"), ("Serverless AI Endpoint", "Gemma 4 · vLLM · H200", "live"),
                                ("Serverless AI Job", "Cosmos Dream · H200", "progress"), ("Dedicated endpoint", "Cosmos3 · 4× H200", "wired"),
                                ("Managed MLflow", "adapter lineage", "planned"), ("nebius CLI", "endpoints · jobs · logs", "live")]),
        ("Cloudflare", CF, [("Pages", "landing · console · docs", "live"), ("Pages Functions", "API (JS, Workers runtime)", "live"),
                            ("D1 (SQLite)", "precedents · calls · alarms", "live"), ("KV", "TTL hazard tags · zones", "live"),
                            ("R2", "raw call + perception bodies", "live"), ("wrangler", "deploy · migrations · secrets", "live")]),
        ("Serving & ML runtime", "#2563eb", [("vLLM v0.30.0", "Gemma 4 OpenAI-compatible API", "live"), ("CUDA 12.8 · cuDNN", "Cosmos job image", "live"),
                                              ("PyTorch · flash-attn", "Cosmos inference", "progress"), ("uv · Python 3.10", "Cosmos env", "live"),
                                              ("Hugging Face Hub", "weights · private dataset", "live"), ("LoRA (PEFT)", "Nano fine-tune", "planned")]),
        ("App & tooling", "#5b6670", [("Node 20+ / CommonJS", "tools · build · QA", "live"), ("HTML · CSS · Canvas 2D", "console + floor sim", "live"),
                                       ("puppeteer-core + Chrome", "QA: 87 checks", "live"), ("marked", "docs PDFs", "live"),
                                       ("matplotlib", "this PDF", "live"), ("ffmpeg", "explainer video · clip frames", "live")]),
    ]
    cw, gap = 24.5, 1.4
    for gi, (name, color, items) in enumerate(groups):
        x = 3 + gi * (cw + gap)
        top = H - 18
        ax.add_patch(FancyBboxPatch((x, 6), cw, top - 6, boxstyle="round,pad=0,rounding_size=1.4", fc="#ffffff", ec=LINE, lw=1))
        ax.add_patch(FancyBboxPatch((x, top - 4.2), cw, 4.2, boxstyle="round,pad=0,rounding_size=1.4", fc=color, ec="none"))
        ax.text(x + 1.5, top - 2.1, name, fontsize=11, color="#ffffff", fontweight="bold", va="center")
        for i, (t, s, st) in enumerate(items):
            y = top - 8 - i * 10.0
            ax.text(x + 1.5, y, t, fontsize=9.6, color=INK, fontweight="bold", va="center")
            ax.text(x + 1.5, y - 2.6, s, fontsize=8.1, color=MUTED, va="center")
            badge(ax, x + cw - 1.2, y - 5.4, st, size=6.4)
            if i < len(items) - 1:
                ax.plot([x + 1.5, x + cw - 1.5], [y - 7.6, y - 7.6], color=LINE, lw=0.8)
    pdf.savefig(fig); return fig


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/NemoFleet-Architecture-Today-vs-Next.pdf")
    png = Path(sys.argv[sys.argv.index("--png") + 1]) if "--png" in sys.argv else None
    with PdfPages(out) as pdf:
        for i, fn in enumerate([cover, today, future, compare, stack], 1):
            fig = fn(pdf)
            if png:
                png.mkdir(parents=True, exist_ok=True); fig.savefig(png / f"page{i}.png", dpi=70)
            plt.close(fig)
        d = pdf.infodict(); d["Title"] = "NemoFleet architecture: today and next"; d["Author"] = "NemoFleet"
    print("wrote", out)


if __name__ == "__main__":
    main()
