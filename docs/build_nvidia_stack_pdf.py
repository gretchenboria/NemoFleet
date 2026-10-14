#!/usr/bin/env python3
"""Build the single-page 16:9 widescreen NemoFleet NVIDIA Stack Architectural Diagram PDF & PNG.

Uses proper systems architecture notation:
  - Hexagons (⬢): NVIDIA GPU / AI Model Engines (CUDA-X CV-CUDA, TensorRT, Cosmos VLM, Nemotron Nano/Super/Ultra, NeMo SFT)
  - Diamonds (◇): Routing & Safety Decision Gates (CUDA-X ROI Gate, Precedent Gate, Autonomy/Safety Gate, Thymus Gate)
  - Cylinders (⛁): Databases, Corpora & Persistent Stores (D1 Precedent Memory, KV Zone Tags / R2 Runs, PhysicalAI-SmartSpaces)
  - Parallelograms (▱): I/O Streams & Wire Payloads (1080p Ego-Camera Frame, Peer Antennation Packet)
  - Process Boxes (▭): Deterministic Runtime Services (Action Executor, A* + CBS Motion Planner, Operator Console)
  - Actor / Robot Nodes (◯): Autonomous Fleet Robots & Operator
  - Dashed Swimlanes: Architectural Subsystem Boundaries
  - Orthogonal Arrows: Solid (synchronous runtime path) & Dashed (asynchronous feedback / Night Shift distillation)
"""
from __future__ import annotations

import html
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
HTML_OUT = Path("/tmp/nemofleet_nvidia_stack_arch.html")
PDF_OUT = ROOT / "docs" / "NemoFleet-NVIDIA-Stack-Architecture.pdf"
PNG_OUT = ROOT / "docs" / "img" / "nvidia-stack-architecture.png"
ARTIFACT_DIR = Path("/Users/dr.gretchenboria/.gemini/antigravity-cli/brain/b35ad0ec-f42c-4e9b-9202-7df8295d262e")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Palette keyed by semantic role
PAL = {
    "nv": ("#3f6212", "#f1f9e4", "#65a30d"),       # NVIDIA Green (CUDA-X, TensorRT, Nemotron Nano)
    "s2": ("#5b21b6", "#f5f3ff", "#7c3aed"),       # Deep Violet (Cosmos VLM, Nemotron Ultra/Super)
    "db": ("#0e7490", "#ecfeff", "#0891b2"),       # Cyan (D1 / KV / R2 / Datasets)
    "rt": ("#1d4ed8", "#eff6ff", "#2563eb"),       # Runtime Blue (Services / Executor / Planner)
    "peer": ("#0f766e", "#f0fdfa", "#0d9488"),     # Teal (System 1.5 Peer Antennation)
    "gate": ("#b45309", "#fffbeb", "#d97706"),     # Amber (Decision Diamonds / Gates)
    "hot": ("#b91c1c", "#fef2f2", "#dc2626"),      # Red (Safety Escalation)
    "ui": ("#334155", "#f8fafc", "#64748b"),       # Slate (Console UI / Hardware)
}


def e(s: str) -> str:
    return html.escape(str(s), quote=True)


def badge(x: float, y: float, text: str, fill: str, text_color: str = "#ffffff") -> str:
    w = len(text) * 6.2 + 12
    return (
        f'<rect x="{x}" y="{y}" width="{w:.1f}" height="16" rx="8" fill="{fill}"/>'
        f'<text x="{x + w / 2:.1f}" y="{y + 11.5:.1f}" class="tag" fill="{text_color}">{e(text)}</text>'
    )


def box(
    x: float,
    y: float,
    w: float,
    h: float,
    kind: str,
    title: str,
    lines: list[str] | None = None,
    tag: str | None = None,
    title_size: int = 12,
) -> str:
    stroke, fill, accent = PAL[kind]
    lines = lines or []
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    ]
    total_h = title_size + 13 * len(lines)
    ty = y + (h - total_h) / 2 + title_size - 1
    out.append(
        f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" class="t" fill="{stroke}" style="font-size:{title_size}px">{e(title)}</text>'
    )
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x + w / 2:.1f}" y="{ty + 14 + 13 * i:.1f}" class="s">{e(ln)}</text>')
    if tag:
        out.append(badge(x + 8, y - 8, tag, stroke))
    return "".join(out)


def hexagon(
    x: float,
    y: float,
    w: float,
    h: float,
    kind: str,
    title: str,
    lines: list[str] | None = None,
    tag: str | None = None,
    title_size: int = 12,
) -> str:
    """Architectural Hexagon (⬢) for NVIDIA GPU / AI Model Compute Engines."""
    stroke, fill, accent = PAL[kind]
    lines = lines or []
    inset = 16
    pts = (
        f"{x + inset},{y} "
        f"{x + w - inset},{y} "
        f"{x + w},{y + h / 2:.1f} "
        f"{x + w - inset},{y + h} "
        f"{x + inset},{y + h} "
        f"{x},{y + h / 2:.1f}"
    )
    out = [
        f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2.2"/>',
        f'<polygon points="{x + inset + 2},{y + 3} {x + w - inset - 2},{y + 3} {x + w - 3},{y + h / 2:.1f} '
        f'{x + w - inset - 2},{y + h - 3} {x + inset + 2},{y + h - 3} {x + 3},{y + h / 2:.1f}" '
        f'fill="none" stroke="{accent}" stroke-opacity="0.35" stroke-width="1"/>',
    ]
    total_h = title_size + 13 * len(lines)
    ty = y + (h - total_h) / 2 + title_size - 1
    out.append(
        f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" class="t" fill="{stroke}" style="font-size:{title_size}px">{e(title)}</text>'
    )
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x + w / 2:.1f}" y="{ty + 14 + 13 * i:.1f}" class="s">{e(ln)}</text>')
    if tag:
        out.append(badge(x + inset, y - 9, tag, stroke))
    return "".join(out)


def cylinder(
    x: float,
    y: float,
    w: float,
    h: float,
    kind: str,
    title: str,
    lines: list[str] | None = None,
    tag: str | None = None,
    title_size: int = 12,
) -> str:
    """Architectural Cylinder (⛁) for Databases, Corpora & Persistent Stores."""
    stroke, fill, accent = PAL[kind]
    lines = lines or []
    ry = 9
    body_top = y + ry
    body_bot = y + h - ry
    out = [
        f'<path d="M {x},{body_top} L {x},{body_bot} A {w / 2:.1f},{ry} 0 0 0 {x + w},{body_bot} L {x + w},{body_top} Z" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
        f'<ellipse cx="{x + w / 2:.1f}" cy="{body_top}" rx="{w / 2:.1f}" ry="{ry}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
        f'<path d="M {x + 6},{body_top + 4} A {w / 2 - 6:.1f},{ry - 3} 0 0 0 {x + w - 6},{body_top + 4}" '
        f'fill="none" stroke="{accent}" stroke-opacity="0.45" stroke-width="1.2"/>',
    ]
    avail_h = h - 2 * ry
    total_h = title_size + 13 * len(lines)
    ty = body_top + ry + (avail_h - total_h) / 2 + title_size - 1
    out.append(
        f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" class="t" fill="{stroke}" style="font-size:{title_size}px">{e(title)}</text>'
    )
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x + w / 2:.1f}" y="{ty + 13.5 + 12.5 * i:.1f}" class="s">{e(ln)}</text>')
    if tag:
        out.append(badge(x + 12, y - 7, tag, stroke))
    return "".join(out)


def diamond(
    cx: float,
    cy: float,
    hw: float,
    hh: float,
    kind: str,
    title: str,
    lines: list[str] | None = None,
    title_size: int = 11,
) -> str:
    """Architectural Decision Diamond (◇) for Routing & Safety Gates."""
    stroke, fill, _ = PAL[kind]
    lines = lines or []
    pts = f"{cx},{cy - hh} {cx + hw},{cy} {cx},{cy + hh} {cx - hw},{cy}"
    out = [f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2.2"/>']
    total_h = title_size + 12 * len(lines)
    ty = cy - total_h / 2 + title_size - 2
    out.append(f'<text x="{cx}" y="{ty:.1f}" class="t" fill="{stroke}" style="font-size:{title_size}px">{e(title)}</text>')
    for i, ln in enumerate(lines):
        out.append(f'<text x="{cx}" y="{ty + 13 + 12 * i:.1f}" class="s" style="font-size:9.8px">{e(ln)}</text>')
    return "".join(out)


def parallelogram(
    x: float,
    y: float,
    w: float,
    h: float,
    kind: str,
    title: str,
    lines: list[str] | None = None,
    tag: str | None = None,
    title_size: int = 11,
) -> str:
    """Architectural I/O Parallelogram (▱) for Data Streams & Wire Payloads."""
    stroke, fill, _ = PAL[kind]
    lines = lines or []
    skew = 12
    pts = f"{x + skew},{y} {x + w},{y} {x + w - skew},{y + h} {x},{y + h}"
    out = [f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>']
    total_h = title_size + 12.5 * len(lines)
    ty = y + (h - total_h) / 2 + title_size - 1
    out.append(
        f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" class="t" fill="{stroke}" style="font-size:{title_size}px">{e(title)}</text>'
    )
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x + w / 2:.1f}" y="{ty + 13 + 12.5 * i:.1f}" class="s">{e(ln)}</text>')
    if tag:
        out.append(badge(x + skew + 4, y - 8, tag, stroke))
    return "".join(out)


def robot_node(cx: float, cy: float, r: float, label: str, sub: str, color: str) -> str:
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" stroke="#ffffff" stroke-width="2.5"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r + 2}" fill="none" stroke="{color}" stroke-opacity="0.4" stroke-width="1.2"/>'
        f'<text x="{cx}" y="{cy + 4}" class="rb">{e(label)}</text>'
        f'<text x="{cx}" y="{cy + r + 13}" class="s" style="font-size:9.5px">{e(sub)}</text>'
    )


def lbl(x: float, y: float, text: str, anchor: str = "middle", color: str = "#334155", bg: str = "#ffffff") -> str:
    w = len(text) * 5.7 + 10
    rx = {"middle": x - w / 2, "start": x - 4, "end": x - w + 4}[anchor]
    return (
        f'<rect x="{rx:.1f}" y="{y - 11:.1f}" width="{w:.1f}" height="15" rx="4" fill="{bg}" stroke="#cbd5e1" stroke-width="0.8"/>'
        f'<text x="{x:.1f}" y="{y:.1f}" class="lbl" fill="{color}" text-anchor="{anchor}">{e(text)}</text>'
    )


def arrow(
    pts: list[tuple[float, float]],
    label: str | None = None,
    lx: float | None = None,
    ly: float | None = None,
    dashed: bool = False,
    color: str = "#475569",
    marker: str = "ah",
    anchor: str = "middle",
) -> str:
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    out = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{dash} marker-end="url(#{marker})"/>'
    if label and lx is not None and ly is not None:
        out += lbl(lx, ly, label, anchor=anchor, color=color)
    return out


def build_svg() -> str:
    b: list[str] = []

    # Arrowhead markers
    b.append(
        """<defs>
        <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#475569"/>
        </marker>
        <marker id="ah-nv" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#3f6212"/>
        </marker>
        <marker id="ah-s2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#5b21b6"/>
        </marker>
        <marker id="ah-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#b91c1c"/>
        </marker>
        <marker id="ah-peer" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#0f766e"/>
        </marker>
        <marker id="ah-db" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#0e7490"/>
        </marker>
        </defs>"""
    )

    # =========================================================================
    # HEADER BAR (y: 10..62)
    # =========================================================================
    b.append('<rect x="12" y="10" width="1576" height="52" rx="10" fill="#0f172a"/>')
    b.append('<rect x="12" y="59" width="1576" height="3" fill="#76b900"/>')
    b.append(
        '<text x="28" y="34" style="font-family:Inter,system-ui,sans-serif;font-size:18px;font-weight:800;fill:#ffffff;letter-spacing:-0.3px">'
        'NemoFleet · End-to-End NVIDIA Stack System Architecture</text>'
    )
    b.append(
        '<text x="28" y="51" style="font-family:Inter,system-ui,sans-serif;font-size:11px;font-weight:500;fill:#a3e635">'
        'NVIDIA CUDA-X (nvImageCodec + CV-CUDA + TensorRT) · Cosmos-Predict2.5 / Cosmos3 VLM · '
        'Nemotron 3 (Nano 30B · Super 120B · Ultra 253B) · PhysicalAI-SmartSpaces · Nebius H200</text>'
    )
    b.append(badge(1395, 20, "16:9 SYSTEM ARCHITECTURE", "#3f6212", "#ffffff"))
    b.append(badge(1265, 20, "NEBIUS × NVIDIA", "#5b21b6", "#ffffff"))

    # =========================================================================
    # SWIMLANE 1: OPERATOR CONSOLE & EDGE STATE LAYER (y: 70..168)
    # =========================================================================
    b.append(
        '<rect x="12" y="70" width="1576" height="98" rx="10" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>'
    )
    b.append(
        '<text x="26" y="86" class="lane" fill="#334155">'
        'LAYER 1 · OPERATOR CONSOLE &amp; CLOUDFLARE EDGE STATE (nemofleet.pages.dev · Workers API)</text>'
    )

    b.append(
        box(
            26,
            102,
            235,
            56,
            "ui",
            "Spatial Command Map & HUD",
            ["Live floor canvas · robot halt/quarantine", "4-cam ego feeds · scenario runner"],
            tag="CONSOLE UI",
        )
    )
    b.append(
        box(
            290,
            102,
            245,
            56,
            "ui",
            "Autonomy & Adapter Controls",
            ["Measured P(actions) >= τ gate selector", "Promote / Hold H200 LoRA adapters"],
            tag="GOVERNANCE",
        )
    )
    b.append(
        box(
            565,
            102,
            245,
            56,
            "ui",
            "Incident & Override Inspector",
            ["Accept / Override / Release alarms", "Operator override writes precedent"],
            tag="HUMAN-IN-LOOP",
        )
    )
    b.append(
        cylinder(
            845,
            98,
            235,
            64,
            "db",
            "Cloudflare D1 (MEMORY)",
            ["decisions · calls · alarms · rules", "1-call-per-cell precedent lookup"],
            tag="SQL STORE",
        )
    )
    b.append(
        cylinder(
            1110,
            98,
            220,
            64,
            "db",
            "Cloudflare KV (TAGS)",
            ["Active quarantine zones & TTLs", "Sub-ms edge broadcast to fleet"],
            tag="KV STORE",
        )
    )
    b.append(
        cylinder(
            1360,
            98,
            210,
            64,
            "db",
            "Cloudflare R2 (RUNS)",
            ["Scenario replay traces & logs", "Night Shift audit artifacts"],
            tag="OBJECT STORE",
        )
    )

    # =========================================================================
    # SWIMLANE 2: PHYSICAL FLEET & STAGE 1 NVIDIA CUDA-X VISION PRE-GATE (x: 12..540, y: 178..648)
    # =========================================================================
    b.append(
        '<rect x="12" y="178" width="528" height="470" rx="10" fill="#f9fbe7" fill-opacity="0.45" stroke="#65a30d" stroke-width="1.8" stroke-dasharray="6 4"/>'
    )
    b.append(
        '<text x="26" y="196" class="lane" fill="#3f6212">'
        'LAYER 2 · EDGE FLEET &amp; STAGE 1 NVIDIA CUDA-X VISION PRE-GATE (0.80 ms on H200)</text>'
    )

    # Robot Fleet Box + Robot Nodes
    b.append(
        '<rect x="26" y="208" width="204" height="154" rx="8" fill="#ffffff" stroke="#64748b" stroke-width="1.8"/>'
    )
    b.append('<text x="128" y="226" class="t" fill="#334155">Autonomous Robot Fleet</text>')
    b.append('<text x="128" y="240" class="s">Warehouse · Data Center · SF</text>')
    b.append(robot_node(60, 270, 15, "R14", "Hazard", "#dc2626"))
    b.append(robot_node(106, 270, 15, "R03", "Person", "#d97706"))
    b.append(robot_node(152, 270, 15, "R12", "Peer", "#0891b2"))
    b.append(robot_node(196, 270, 15, "R07", "Clear", "#16a34a"))
    b.append(
        '<text x="128" y="325" class="s" style="font-family:JetBrains Mono,monospace;font-size:9.5px">'
        'POST /api/events (Bearer)</text>'
    )
    b.append(
        '<text x="128" y="348" class="s" style="font-size:9.5px;fill:#0f766e;font-weight:600">'
        '↔ Countercurrent pass: 0 calls</text>'
    )

    # Input Stream Parallelogram
    b.append(
        parallelogram(
            268,
            214,
            256,
            64,
            "rt",
            "1080p Ego-Camera Stream",
            ["RGB JPEG frame + cell + pose", "tools/ego_mix/cuda_x_pipeline.py"],
            tag="I/O STREAM",
        )
    )

    # Hexagon 1: nvImageCodec + CV-CUDA
    b.append(
        hexagon(
            268,
            306,
            256,
            78,
            "nv",
            "NVIDIA nvImageCodec + CV-CUDA",
            [
                "GPU JPEG decode → NHWC tensor",
                "cvcuda.customcrop ROI [18..82%, 45..92%]",
                "cvcuda.gaussian(5x5) + normalize · 0.38 ms",
            ],
            tag="CUDA-X · CV-CUDA",
        )
    )

    # Hexagon 2: NVIDIA TensorRT
    b.append(
        hexagon(
            268,
            414,
            256,
            78,
            "nv",
            "NVIDIA TensorRT (torch_tensorrt)",
            [
                "Zero-copy DLPack → PyTorch CUDA",
                "CorridorAnomalyHead FP16/BF16",
                "floor_anomaly_score · 0.42 ms",
            ],
            tag="CUDA-X · TENSORRT",
        )
    )

    # Decision Diamond 1: CUDA-X Gate
    b.append(
        diamond(
            396,
            564,
            110,
            52,
            "gate",
            "Gate 1 · CUDA-X ROI",
            ["anomaly_score >= -0.75?", "12/12 frames · 0.80 ms"],
        )
    )

    # Fast-pass clear box on bottom-left of Swimlane 2
    b.append(
        box(
            26,
            532,
            190,
            64,
            "nv",
            "Clear Corridor Fast-Pass",
            ["Skip Cosmos VLM & Ultra (25%)", "Continue patrol · 0 VLM tokens"],
            tag="SCORE < -0.75",
        )
    )

    # System 1.5 Peer Exchange Box in Swimlane 2 (middle-left)
    b.append(
        parallelogram(
            26,
            404,
            190,
            88,
            "peer",
            "System 1.5 · Peer Handshake",
            [
                "Antennation swap on aisle pass",
                "Outbound gets hazards ahead",
                "Inbound gets policy & map tags",
                "0 LLM calls · bounded packet",
            ],
            tag="PEER MEMORY",
        )
    )

    # =========================================================================
    # SWIMLANE 3: STAGE 2 NVIDIA NEMOTRON & COSMOS TIERED REASONING (x: 554..1588, y: 178..648)
    # =========================================================================
    b.append(
        '<rect x="554" y="178" width="1034" height="470" rx="10" fill="#f5f3ff" fill-opacity="0.35" stroke="#7c3aed" stroke-width="1.8" stroke-dasharray="6 4"/>'
    )
    b.append(
        '<text x="568" y="196" class="lane" fill="#5b21b6">'
        'LAYER 3 · STAGE 2 NVIDIA COSMOS PERCEPTION &amp; NEMOTRON TIERED COGNITIVE RUNTIME</text>'
    )

    # Hexagon 3: Cosmos VLM Perception
    b.append(
        hexagon(
            572,
            214,
            268,
            82,
            "s2",
            "NVIDIA Cosmos-Predict2.5 / Cosmos3",
            [
                "Vision-Language Scene Reasoner VLM",
                "Extracts: person, hazard_kind, severity",
                "Woken ONLY when CUDA-X score >= -0.75",
            ],
            tag="COSMOS VLM",
        )
    )

    # Event & Telemetry Bus
    b.append(
        box(
            572,
            326,
            268,
            64,
            "rt",
            "Structured Incident & Track Context",
            [
                "Scene graph + ego/overhead track kin.",
                "functions/api/[[path]].js · runEvent()",
            ],
            tag="EVENT BUS",
        )
    )

    # Decision Diamond 2: Precedent Memory Lookup Gate
    b.append(
        diamond(
            706,
            462,
            112,
            52,
            "gate",
            "Gate 2 · Fleet Memory",
            ["Live D1 decision at cell", "& !person in scene?"],
        )
    )

    # Hexagon 4: Nemotron 3 Nano 30B-A3B (System 1 Reflex)
    b.append(
        hexagon(
            892,
            306,
            304,
            106,
            "nv",
            "NVIDIA Nemotron 3 Nano 30B-A3B-BF16",
            [
                "Hybrid Mamba-2 + Transformer MoE (3.5B active)",
                "Dual LoRA on H200 (tools/ego_mix/serve.py):",
                "• decide-1: JSON actions + P(actions) logprob",
                "• plan-1 (inway): logit(true)-logit(false) >= -0.75",
            ],
            tag="SYSTEM 1 · REFLEX",
        )
    )

    # Decision Diamond 3: Safety & Calibrated Autonomy Gate
    b.append(
        diamond(
            1044,
            492,
            124,
            56,
            "hot",
            "Gate 3 · Safety & Gate τ",
            ["person || in_way >= -0.75", "|| P(actions) < τ (0.80)?"],
        )
    )

    # Hexagon 5: Nemotron 3 Ultra 253B (System 2 Deliberator)
    b.append(
        hexagon(
            1250,
            214,
            322,
            96,
            "s2",
            "NVIDIA Nemotron 3 Ultra 253B-A22B",
            [
                "Deep Deliberator (1,000-tok reasoning budget)",
                "Handles human-in-aisle safety & novel hazards",
                "Writes reusable cell decision to D1 Fleet Memory",
                "Never caches person events (always re-verifies)",
            ],
            tag="SYSTEM 2 · DELIBERATOR",
        )
    )

    # Process Box: Action Executor
    b.append(
        box(
            1262,
            366,
            298,
            68,
            "rt",
            "Validated Fleet Action Executor",
            [
                "halt · reroute · quarantine_zone · broadcast_peer",
                "Writes KV zone tags + D1 call & action audit log",
            ],
            tag="EXECUTOR",
        )
    )

    # Process Box: Motion Planner
    b.append(
        box(
            1262,
            468,
            298,
            68,
            "rt",
            "A* + Conflict-Based Search (CBS)",
            [
                "Deterministic multi-agent pathfinding around",
                "quarantined cells & countercurrent aisle pairing",
            ],
            tag="MOTION PLANNER",
        )
    )

    # =========================================================================
    # SWIMLANE 4: NIGHT SHIFT DISTILLATION & NEBIUS H200 GPU CLUSTER (y: 658..828)
    # =========================================================================
    b.append(
        '<rect x="12" y="658" width="1576" height="170" rx="10" fill="#fffbeb" fill-opacity="0.55" stroke="#d97706" stroke-width="1.8" stroke-dasharray="6 4"/>'
    )
    b.append(
        '<text x="26" y="678" class="lane" fill="#b45309">'
        'LAYER 4 · NIGHT SHIFT SELF-IMPROVEMENT LOOP &amp; NEBIUS H200 SXM (141 GB) INFRASTRUCTURE</text>'
    )

    # Cylinder: PhysicalAI-SmartSpaces + Ego-Mix Corpus
    b.append(
        cylinder(
            26,
            694,
            265,
            118,
            "db",
            "NVIDIA-PhysicalAI-SmartSpaces",
            [
                "+ JRDB + Thör-Magni + Waymo Open",
                "1,594,815 real trajectories",
                "1,458 warehouse/campus 10s windows",
                "Held-out place split (train/val/test)",
            ],
            tag="PHYSICAL AI CORPUS",
        )
    )

    # Process Box: Night Shift Replay
    b.append(
        box(
            325,
            698,
            225,
            110,
            "rt",
            "1 · Night Shift Replay Audit",
            [
                "Ultra 253B re-grades today's Nano",
                "decisions from R2 / D1 call logs",
                "Flags disagreements for SFT",
                "tools/night_shift/distill.cjs",
            ],
            tag="REPLAY",
        )
    )

    # Hexagon 6: Nemotron 3 Super 120B (Dream Generator)
    b.append(
        hexagon(
            584,
            698,
            265,
            110,
            "s2",
            "NVIDIA Nemotron 3 Super 120B",
            [
                "2 · Counterfactual Dream Synthesis",
                "2,048-tok reasoning generates",
                "adversarial multi-hazard drills",
                "Solved by Ultra → training pairs",
            ],
            tag="DREAM GENERATOR",
        )
    )

    # Decision Diamond 4: Thymus Gate
    b.append(
        diamond(
            952,
            753,
            82,
            52,
            "gate",
            "3 · Thymus Gate",
            ["Valid schema &", "!unsafe / !dup?"],
        )
    )

    # Hexagon 7: NeMo / TRL SFT on Nebius H200
    b.append(
        hexagon(
            1068,
            694,
            285,
            118,
            "nv",
            "NeMo / HF TRL LoRA SFT on H200",
            [
                "1x Nebius H200 SXM (141 GB BF16)",
                "LoRA r=16 α=32 on Mamba-2 + Attn:",
                "• decide-1: 35.1% → 98.5% exact (+63.4 pt)",
                "• plan-1: 27.6% → 85.7% exact · 76.9% recall",
            ],
            tag="NEBIUS H200 TRAINING",
        )
    )

    # Architectural Notation Legend Box (Bottom Right: x=1374..1576, y=686..818)
    b.append(
        '<rect x="1374" y="686" width="202" height="132" rx="8" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5"/>'
    )
    b.append('<text x="1475" y="703" class="t" fill="#0f172a" style="font-size:11px">ARCHITECTURAL NOTATION</text>')
    # Mini Hexagon
    b.append('<polygon points="1390,713 1404,713 1410,720 1404,727 1390,727 1384,720" fill="#f1f9e4" stroke="#3f6212" stroke-width="1.5"/>')
    b.append('<text x="1418" y="724" class="leg">NVIDIA GPU / Model Engine</text>')
    # Mini Diamond
    b.append('<polygon points="1397,732 1409,740 1397,748 1385,740" fill="#fffbeb" stroke="#b45309" stroke-width="1.5"/>')
    b.append('<text x="1418" y="744" class="leg">Routing / Safety Gate</text>')
    # Mini Cylinder
    b.append('<rect x="1387" y="755" width="20" height="12" rx="2" fill="#ecfeff" stroke="#0e7490" stroke-width="1.5"/>')
    b.append('<ellipse cx="1397" cy="755" rx="10" ry="3" fill="#ecfeff" stroke="#0e7490" stroke-width="1.5"/>')
    b.append('<text x="1418" y="764" class="leg">Database / Training Corpus</text>')
    # Mini Parallelogram
    b.append('<polygon points="1389,775 1409,775 1405,786 1385,786" fill="#eff6ff" stroke="#1d4ed8" stroke-width="1.5"/>')
    b.append('<text x="1418" y="784" class="leg">I/O Stream / Peer Packet</text>')
    # Sync vs Async arrows
    b.append('<line x1="1385" y1="798" x2="1410" y2="798" stroke="#475569" stroke-width="2" marker-end="url(#ah)"/>')
    b.append('<text x="1418" y="802" class="leg">Sync Runtime Flow</text>')
    b.append('<line x1="1385" y1="812" x2="1410" y2="812" stroke="#5b21b6" stroke-width="2" stroke-dasharray="4 3" marker-end="url(#ah-s2)"/>')
    b.append('<text x="1418" y="815" class="leg">Async / Distillation Loop</text>')

    # =========================================================================
    # ARROWS & DATAFLOW CONNECTIONS (Orthogonal, Labeled, Non-Overlapping)
    # =========================================================================
    # 1. Robot Fleet -> 1080p Ego-Camera Stream
    b.append(arrow([(230, 246), (272, 246)], "JPEG", 250, 232))

    # 2. 1080p Stream -> nvImageCodec + CV-CUDA
    b.append(arrow([(396, 278), (396, 304)], "raw bytes", 442, 294, color="#3f6212", marker="ah-nv"))

    # 3. CV-CUDA -> TensorRT
    b.append(arrow([(396, 384), (396, 412)], "DLPack (0-copy)", 452, 401, color="#3f6212", marker="ah-nv"))

    # 4. TensorRT -> Gate 1 (CUDA-X ROI Gate)
    b.append(arrow([(396, 492), (396, 512)], color="#3f6212", marker="ah-nv"))

    # 5. Gate 1 -> Clear Corridor Fast-Pass (< -0.75)
    b.append(arrow([(286, 564), (218, 564)], "< -0.75", 256, 548, color="#3f6212", marker="ah-nv"))
    # Fast-Pass back to Robot Fleet
    b.append(arrow([(26, 564), (18, 564), (18, 284), (24, 284)], dashed=True, color="#3f6212", marker="ah-nv"))

    # 6. Gate 1 -> Cosmos VLM (score >= -0.75 wakes VLM)
    b.append(
        arrow(
            [(506, 564), (547, 564), (547, 255), (570, 255)],
            "score >= -0.75 (wake VLM)",
            482,
            512,
            color="#5b21b6",
            marker="ah-s2",
        )
    )

    # 7. Cosmos VLM -> Structured Incident & Track Context
    b.append(arrow([(706, 296), (706, 324)], "hazard · person JSON", 706, 312, color="#5b21b6", marker="ah-s2"))

    # 8. Event Bus -> Gate 2 (Precedent Lookup)
    b.append(arrow([(706, 390), (706, 410)]))

    # 9. D1 Precedent Memory <-> Gate 2 Lookup (routed cleanly in the x=868 channel)
    b.append(
        arrow(
            [(900, 162), (900, 204), (868, 204), (868, 424), (762, 424)],
            "cell precedent",
            812,
            414,
            dashed=True,
            color="#0e7490",
            marker="ah-db",
        )
    )

    # 10. System 1.5 Peer Handshake <-> Robot Fleet & Gate 2
    b.append(arrow([(121, 362), (121, 402)], "pass-by", 156, 385, color="#0f766e", marker="ah-peer"))
    b.append(
        arrow(
            [(210, 448), (228, 448), (228, 624), (706, 624), (706, 514)],
            "peer-shared cell decisions (0 model calls)",
            475,
            618,
            dashed=True,
            color="#0f766e",
            marker="ah-peer",
        )
    )

    # 11. Gate 2 -> Action Executor (HIT: reuse stored decision, 0 model calls)
    b.append(
        arrow(
            [(706, 514), (706, 598), (1234, 598), (1234, 400), (1260, 400)],
            "HIT: reuse stored cell decision (0 model calls)",
            965,
            592,
            color="#0e7490",
            marker="ah-db",
        )
    )

    # 12. Gate 2 -> Nemotron 3 Nano (MISS: novel cell -> System 1 Reflex)
    b.append(
        arrow(
            [(818, 462), (868, 462), (868, 359), (890, 359)],
            "MISS",
            843,
            454,
            color="#3f6212",
            marker="ah-nv",
        )
    )

    # 13. Nemotron 3 Nano -> Gate 3 (Safety & Gate τ)
    b.append(
        arrow(
            [(1044, 412), (1044, 436)],
            "actions + P(actions)",
            1115,
            426,
            color="#3f6212",
            marker="ah-nv",
        )
    )

    # 14. Gate 3 -> Action Executor (PASS: P(actions) >= τ & !person)
    b.append(
        arrow(
            [(1168, 492), (1202, 492), (1202, 385), (1260, 385)],
            "PASS (>= τ)",
            1156,
            452,
            color="#3f6212",
            marker="ah-nv",
        )
    )

    # 15. Gate 3 -> Nemotron 3 Ultra 253B (ESCALATE: person || P < τ)
    b.append(
        arrow(
            [(1044, 548), (1044, 570), (1218, 570), (1218, 262), (1248, 262)],
            "ESCALATE (person || P < τ)",
            1105,
            564,
            color="#b91c1c",
            marker="ah-hot",
        )
    )

    # 16. Nemotron 3 Ultra -> Action Executor
    b.append(
        arrow(
            [(1411, 310), (1411, 364)],
            "deliberated actions",
            1472,
            338,
            color="#5b21b6",
            marker="ah-s2",
        )
    )

    # 17. Nemotron 3 Ultra -> D1 Precedent Memory (stores new precedent if !person)
    b.append(
        arrow(
            [(1330, 214), (1330, 172), (985, 172), (985, 162)],
            "store cell decision (!person)",
            1115,
            172,
            dashed=True,
            color="#5b21b6",
            marker="ah-s2",
        )
    )

    # 18. Action Executor -> KV Zone Tags (routed cleanly via x=1234 channel, starting right of EXECUTOR badge)
    b.append(
        arrow(
            [(1356, 366), (1356, 336), (1234, 336), (1234, 162)],
            "quarantine tag",
            1234,
            204,
            dashed=True,
            color="#0e7490",
            marker="ah-db",
        )
    )

    # 19. Action Executor -> A* + CBS Motion Planner
    b.append(arrow([(1411, 434), (1411, 466)], "goals + constraints", 1474, 453))

    # 20. Motion Planner -> Robot Fleet (trajectories)
    b.append(
        arrow(
            [(1411, 536), (1411, 638), (128, 638), (128, 598)],
            "collision-free trajectories & quarantine avoidance",
            830,
            636,
        )
    )

    # 21. Night Shift Flow (Layer 4):
    # Corpus -> Replay & SFT
    b.append(arrow([(291, 753), (323, 753)], "tracks", 307, 740, color="#0e7490", marker="ah-db"))
    # Replay -> Super 120B Dream
    b.append(arrow([(550, 753), (582, 753)], "hard cases", 566, 740, color="#5b21b6", marker="ah-s2"))
    # Super 120B Dream -> Thymus Gate
    b.append(arrow([(849, 753), (870, 753)], color="#5b21b6", marker="ah-s2"))
    # Thymus Gate -> NeMo / TRL SFT on H200
    b.append(arrow([(1034, 753), (1066, 753)], "verified", 1050, 738, color="#3f6212", marker="ah-nv"))
    # NeMo / TRL SFT -> Hot-swap LoRA weights into Nemotron 3 Nano
    b.append(
        arrow(
            [(1180, 694), (1180, 414)],
            "Promote LoRA (decide-1 + plan-1)",
            1180,
            650,
            dashed=True,
            color="#3f6212",
            marker="ah-nv",
        )
    )

    return (
        '<svg viewBox="0 0 1600 840" width="1600" height="840" xmlns="http://www.w3.org/2000/svg">'
        + "".join(b)
        + "</svg>"
    )


HTML_DOC = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NemoFleet · NVIDIA Stack System Architecture</title>
<style>
  @page {{
    size: 1600px 840px;
    margin: 0;
  }}
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}
  html, body {{
    width: 1600px;
    height: 840px;
    overflow: hidden;
    background: #ffffff;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  svg {{
    display: block;
    width: 1600px;
    height: 840px;
  }}
  .lane {{
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.6px;
  }}
  .t {{
    font-weight: 700;
    text-anchor: middle;
  }}
  .s {{
    font-size: 10.2px;
    fill: #334155;
    text-anchor: middle;
  }}
  .tag {{
    font-size: 8.8px;
    font-weight: 800;
    letter-spacing: 0.5px;
    text-anchor: middle;
  }}
  .lbl {{
    font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 9.2px;
    font-weight: 600;
  }}
  .rb {{
    font-size: 10px;
    font-weight: 800;
    fill: #ffffff;
    text-anchor: middle;
  }}
  .leg {{
    font-size: 9.6px;
    font-weight: 600;
    fill: #1e293b;
  }}
</style>
</head>
<body>
{build_svg()}
</body>
</html>
"""


def main() -> None:
    HTML_OUT.write_text(HTML_DOC, encoding="utf-8")
    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    PNG_OUT.parent.mkdir(parents=True, exist_ok=True)

    # Render single-page 16:9 landscape PDF via headless Chrome
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF_OUT}",
            f"file://{HTML_OUT}",
        ],
        check=True,
    )

    # Render crisp 2x retina PNG screenshot via headless Chrome
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--hide-scrollbars",
            "--window-size=1600,840",
            "--force-device-scale-factor=2",
            f"--screenshot={PNG_OUT}",
            f"file://{HTML_OUT}",
        ],
        check=True,
    )

    if ARTIFACT_DIR.exists():
        shutil.copy2(PDF_OUT, ARTIFACT_DIR / "NemoFleet-NVIDIA-Stack-Architecture.pdf")
        shutil.copy2(PNG_OUT, ARTIFACT_DIR / "nvidia-stack-architecture.png")

    print(f"Wrote {PDF_OUT} ({PDF_OUT.stat().st_size:,} bytes)")
    print(f"Wrote {PNG_OUT} ({PNG_OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
