#!/usr/bin/env python3
"""Build a minimal, zero-clutter 16:9 widescreen NemoFleet NVIDIA Stack Architectural Diagram PDF & PNG.

Every shape has ONLY a short title + 1-line subtitle, using proper architectural notation:
  - Hexagons (⬢): NVIDIA GPU / Model Engines
  - Diamonds (◇): Routing / Safety Gates
  - Cylinders (⛁): Data Stores & Datasets
  - Parallelogram (▱): Camera I/O Stream
  - Process Boxes (▭): Console & Action Executor
"""
from __future__ import annotations

import html
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
HTML_OUT = Path("/tmp/nemofleet_nvidia_stack_arch.html")
PDF_OUT = ROOT / "docs" / "NemoFleet-NVIDIA-Stack-Architecture.pdf"
PNG_OUT = ROOT / "docs" / "img" / "nvidia-stack-architecture.png"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

PAL = {
    "nv": ("#3f6212", "#f1f9e4", "#65a30d"),     # NVIDIA Green
    "s2": ("#5b21b6", "#f5f3ff", "#7c3aed"),     # Deep Violet
    "db": ("#0e7490", "#ecfeff", "#0891b2"),     # Cyan Store
    "rt": ("#1d4ed8", "#eff6ff", "#2563eb"),     # Runtime Blue
    "gate": ("#b45309", "#fffbeb", "#d97706"),   # Amber Gate
    "ui": ("#334155", "#f8fafc", "#64748b"),     # Slate UI
}


def e(s: str) -> str:
    return html.escape(str(s), quote=True)


def badge(x: float, y: float, text: str, fill: str) -> str:
    w = len(text) * 7.2 + 16
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="20" rx="10" fill="{fill}"/>'
        f'<text x="{x + w / 2:.1f}" y="{y + 13.8:.1f}" class="tag" fill="#ffffff">{e(text)}</text>'
    )


def box(x: float, y: float, w: float, h: float, kind: str, title: str, sub: str = "", tag: str | None = None) -> str:
    stroke, fill, _ = PAL[kind]
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>']
    ty = y + h / 2 - (4 if sub else -6)
    out.append(f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" class="t" fill="{stroke}">{e(title)}</text>')
    if sub:
        out.append(f'<text x="{x + w / 2:.1f}" y="{ty + 21:.1f}" class="s">{e(sub)}</text>')
    if tag:
        out.append(badge(x + 14, y - 10, tag, stroke))
    return "".join(out)


def hexagon(x: float, y: float, w: float, h: float, kind: str, title: str, sub: str = "", tag: str | None = None) -> str:
    stroke, fill, accent = PAL[kind]
    inset = 24
    pts = f"{x + inset},{y} {x + w - inset},{y} {x + w},{y + h / 2:.1f} {x + w - inset},{y + h} {x + inset},{y + h} {x},{y + h / 2:.1f}"
    out = [
        f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2.8"/>',
        f'<polygon points="{x + inset + 3},{y + 4} {x + w - inset - 3},{y + 4} {x + w - 4},{y + h / 2:.1f} '
        f'{x + w - inset - 3},{y + h - 4} {x + inset + 3},{y + h - 4} {x + 4},{y + h / 2:.1f}" '
        f'fill="none" stroke="{accent}" stroke-opacity="0.35" stroke-width="1.2"/>',
    ]
    ty = y + h / 2 - (4 if sub else -6)
    out.append(f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" class="t" fill="{stroke}">{e(title)}</text>')
    if sub:
        out.append(f'<text x="{x + w / 2:.1f}" y="{ty + 21:.1f}" class="s">{e(sub)}</text>')
    if tag:
        out.append(badge(x + inset + 2, y - 10, tag, stroke))
    return "".join(out)


def cylinder(x: float, y: float, w: float, h: float, kind: str, title: str, sub: str = "", tag: str | None = None) -> str:
    stroke, fill, _ = PAL[kind]
    ry = 12
    top = y + ry
    bot = y + h - ry
    out = [
        f'<path d="M {x},{top} L {x},{bot} A {w / 2:.1f},{ry} 0 0 0 {x + w},{bot} L {x + w},{top} Z" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>',
        f'<ellipse cx="{x + w / 2:.1f}" cy="{top}" rx="{w / 2:.1f}" ry="{ry}" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>',
    ]
    ty = top + (h - 2 * ry) / 2 + 2
    out.append(f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" class="t" fill="{stroke}">{e(title)}</text>')
    if sub:
        out.append(f'<text x="{x + w / 2:.1f}" y="{ty + 20:.1f}" class="s">{e(sub)}</text>')
    if tag:
        out.append(badge(x + 16, y - 9, tag, stroke))
    return "".join(out)


def diamond(cx: float, cy: float, hw: float, hh: float, kind: str, title: str, sub: str = "") -> str:
    stroke, fill, _ = PAL[kind]
    pts = f"{cx},{cy - hh} {cx + hw},{cy} {cx},{cy + hh} {cx - hw},{cy}"
    out = [
        f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2.6"/>',
        f'<text x="{cx}" y="{cy - 2}" class="t" fill="{stroke}" style="font-size:15px">{e(title)}</text>',
    ]
    if sub:
        out.append(f'<text x="{cx}" y="{cy + 17}" class="s" style="font-size:12px">{e(sub)}</text>')
    return "".join(out)


def parallelogram(x: float, y: float, w: float, h: float, kind: str, title: str, sub: str = "", tag: str | None = None) -> str:
    stroke, fill, _ = PAL[kind]
    skew = 16
    pts = f"{x + skew},{y} {x + w},{y} {x + w - skew},{y + h} {x},{y + h}"
    ty = y + h / 2 - 4
    out = [
        f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>',
        f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" class="t" fill="{stroke}">{e(title)}</text>',
        f'<text x="{x + w / 2:.1f}" y="{ty + 21:.1f}" class="s">{e(sub)}</text>',
    ]
    if tag:
        out.append(badge(x + skew + 4, y - 10, tag, stroke))
    return "".join(out)


def lbl(x: float, y: float, text: str, color: str = "#334155") -> str:
    w = len(text) * 7.2 + 14
    return (
        f'<rect x="{x - w / 2:.1f}" y="{y - 13:.1f}" width="{w:.1f}" height="20" rx="6" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>'
        f'<text x="{x:.1f}" y="{y + 1:.1f}" class="lbl" fill="{color}" text-anchor="middle">{e(text)}</text>'
    )


def arrow(
    pts: list[tuple[float, float]],
    label: str | None = None,
    lx: float | None = None,
    ly: float | None = None,
    dashed: bool = False,
    color: str = "#475569",
    marker: str = "ah",
) -> str:
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    out = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5"{dash} marker-end="url(#{marker})"/>'
    if label and lx is not None and ly is not None:
        out += lbl(lx, ly, label, color=color)
    return out


def build_svg() -> str:
    b: list[str] = []

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
        <marker id="ah-db" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#0e7490"/>
        </marker>
        </defs>"""
    )

    # HEADER
    b.append('<rect x="20" y="16" width="1560" height="58" rx="12" fill="#0f172a"/>')
    b.append('<rect x="20" y="70" width="1560" height="4" fill="#76b900"/>')
    b.append(
        '<text x="40" y="45" style="font-family:Inter,system-ui,sans-serif;font-size:22px;font-weight:800;fill:#ffffff">'
        'NemoFleet · NVIDIA Stack Architecture</text>'
    )
    b.append(
        '<text x="485" y="45" style="font-family:Inter,system-ui,sans-serif;font-size:13.5px;font-weight:600;fill:#a3e635">'
        'CUDA-X (CV-CUDA + TensorRT) · Cosmos VLM · Nemotron 3 (Nano · Super · Ultra) · Nebius H200</text>'
    )

    # TIER 1: CONSOLE, MEMORY, EXECUTOR (y: 92..224)
    b.append('<rect x="20" y="92" width="1560" height="132" rx="14" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.8" stroke-dasharray="7 5"/>')
    b.append('<text x="40" y="116" class="lane" fill="#334155">CONTROL &amp; MEMORY LAYER</text>')

    b.append(box(44, 132, 420, 74, "ui", "Ops Console", "Live Map · Autonomy Gate τ", tag="CONSOLE UI"))
    b.append(cylinder(560, 126, 440, 82, "db", "Fleet Memory (D1 / KV / R2)", "1 Decision / Cell · Peer Sync", tag="STATE STORE"))
    b.append(box(1096, 132, 456, 74, "rt", "Action Executor & A* Planner", "Halt · Reroute · Quarantine", tag="EXECUTOR"))

    # TIER 2: NVIDIA REAL-TIME PIPELINE (y: 246..614)
    b.append('<rect x="20" y="246" width="1560" height="368" rx="14" fill="#f9fbe7" fill-opacity="0.4" stroke="#65a30d" stroke-width="2" stroke-dasharray="7 5"/>')
    b.append('<text x="40" y="272" class="lane" fill="#3f6212">REAL-TIME NVIDIA PERCEPTION &amp; REASONING PIPELINE</text>')

    b.append(parallelogram(44, 355, 220, 92, "rt", "Robot Camera", "1080p RGB + Pose", tag="I/O STREAM"))
    b.append(hexagon(325, 345, 285, 112, "nv", "NVIDIA CUDA-X", "CV-CUDA + TensorRT (0.8 ms)", tag="VISION PRE-GATE"))
    b.append(diamond(745, 401, 92, 62, "gate", "Anomaly?", "score >= -0.75"))
    b.append(hexagon(905, 290, 315, 112, "nv", "Cosmos VLM + Nano 30B", "Scene Parse + Dual LoRA Reflex", tag="SYSTEM 1"))
    b.append(diamond(1062, 512, 98, 62, "gate", "Safe & >= τ?", "!person & P >= τ"))
    b.append(hexagon(1275, 345, 275, 112, "s2", "Nemotron Ultra 253B", "System 2 Deep Deliberator", tag="SYSTEM 2"))

    # TIER 3: NIGHT SHIFT & LEGEND (y: 636..816)
    b.append('<rect x="20" y="636" width="1170" height="180" rx="14" fill="#f5f3ff" fill-opacity="0.45" stroke="#7c3aed" stroke-width="1.8" stroke-dasharray="7 5"/>')
    b.append('<text x="40" y="662" class="lane" fill="#5b21b6">NIGHT SHIFT DISTILLATION ON NEBIUS H200</text>')

    b.append(cylinder(44, 684, 315, 110, "db", "PhysicalAI-SmartSpaces", "1.59M Real Trajectories", tag="CORPUS"))
    b.append(hexagon(425, 684, 330, 110, "s2", "Nemotron Super 120B", "Replay Audit + Dream Drills", tag="SYNTHESIS"))
    b.append(hexagon(820, 684, 340, 110, "nv", "NeMo / TRL LoRA SFT", "Nebius H200 (35% → 98.5%)", tag="H200 GPU"))

    # NOTATION LEGEND
    b.append('<rect x="1212" y="636" width="368" height="180" rx="14" fill="#ffffff" stroke="#94a3b8" stroke-width="1.8"/>')
    b.append('<text x="1396" y="664" class="t" fill="#0f172a" style="font-size:14px">ARCHITECTURAL NOTATION</text>')
    b.append('<polygon points="1248,682 1268,682 1276,692 1268,702 1248,702 1240,692" fill="#f1f9e4" stroke="#3f6212" stroke-width="2"/>')
    b.append('<text x="1292" y="696" class="leg">NVIDIA GPU / Model Engine</text>')
    b.append('<polygon points="1258,712 1274,723 1258,734 1242,723" fill="#fffbeb" stroke="#b45309" stroke-width="2"/>')
    b.append('<text x="1292" y="727" class="leg">Routing / Safety Gate</text>')
    b.append('<rect x="1244" y="744" width="28" height="15" rx="2" fill="#ecfeff" stroke="#0e7490" stroke-width="2"/>')
    b.append('<ellipse cx="1258" cy="744" rx="14" ry="4" fill="#ecfeff" stroke="#0e7490" stroke-width="2"/>')
    b.append('<text x="1292" y="756" class="leg">State Store / Dataset</text>')
    b.append('<polygon points="1246,770 1274,770 1268,785 1240,785" fill="#eff6ff" stroke="#1d4ed8" stroke-width="2"/>')
    b.append('<text x="1292" y="782" class="leg">Telemetry Stream (I/O)</text>')
    b.append('<line x1="1240" y1="802" x2="1274" y2="802" stroke="#3f6212" stroke-width="2.5" marker-end="url(#ah-nv)"/>')
    b.append('<text x="1288" y="806" class="leg">Sync Flow</text>')
    b.append('<line x1="1380" y1="802" x2="1414" y2="802" stroke="#5b21b6" stroke-width="2.5" stroke-dasharray="6 4" marker-end="url(#ah-s2)"/>')
    b.append('<text x="1428" y="806" class="leg">Async Loop</text>')

    # ARROWS
    b.append(arrow([(256, 401), (322, 401)], "frames", 289, 378, color="#3f6212", marker="ah-nv"))
    b.append(arrow([(610, 401), (650, 401)], color="#3f6212", marker="ah-nv"))
    b.append(arrow([(745, 463), (745, 594), (1566, 594), (1566, 169), (1555, 169)], "clear (skip VLM)", 860, 592, color="#3f6212", marker="ah-nv"))
    b.append(arrow([(837, 401), (872, 401), (872, 346), (902, 346)], "hazard", 872, 372, color="#3f6212", marker="ah-nv"))
    b.append(arrow([(940, 208), (940, 287)], "precedent", 885, 232, dashed=True, color="#0e7490", marker="ah-db"))
    b.append(arrow([(1062, 402), (1062, 447)], color="#3f6212", marker="ah-nv"))
    b.append(arrow([(1160, 512), (1245, 512), (1245, 208)], "pass", 1245, 265, color="#3f6212", marker="ah-nv"))
    b.append(arrow([(1130, 490), (1272, 415)], "escalate", 1200, 440, color="#5b21b6", marker="ah-s2"))
    b.append(arrow([(1412, 345), (1412, 208)], "action", 1412, 285, color="#5b21b6", marker="ah-s2"))
    b.append(arrow([(1330, 345), (1330, 232), (990, 232), (990, 208)], "store cell", 1125, 232, dashed=True, color="#5b21b6", marker="ah-s2"))
    b.append(arrow([(464, 169), (557, 169)]))
    b.append(arrow([(1000, 169), (1093, 169)]))
    b.append(arrow([(359, 739), (422, 739)], color="#0e7490", marker="ah-db"))
    b.append(arrow([(755, 739), (817, 739)], color="#5b21b6", marker="ah-s2"))
    b.append(arrow([(935, 684), (935, 405)], "LoRA weights", 935, 626, dashed=True, color="#3f6212", marker="ah-nv"))

    return '<svg viewBox="0 0 1600 840" width="1600" height="840" xmlns="http://www.w3.org/2000/svg">' + "".join(b) + "</svg>"


HTML_DOC = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NemoFleet · NVIDIA Stack Architecture</title>
<style>
  @page {{ size: 1600px 840px; margin: 0; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 1600px; height: 840px; overflow: hidden; background: #ffffff;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }}
  svg {{ display: block; width: 1600px; height: 840px; }}
  .lane {{ font-size: 12px; font-weight: 800; letter-spacing: 0.8px; }}
  .t {{ font-size: 16.5px; font-weight: 800; text-anchor: middle; }}
  .s {{ font-size: 13px; fill: #334155; text-anchor: middle; font-weight: 500; }}
  .tag {{ font-size: 9.5px; font-weight: 800; letter-spacing: 0.6px; text-anchor: middle; }}
  .lbl {{ font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; font-weight: 700; }}
  .leg {{ font-size: 12px; font-weight: 600; fill: #1e293b; }}
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

    subprocess.run([CHROME, "--headless=new", "--no-pdf-header-footer", f"--print-to-pdf={PDF_OUT}", f"file://{HTML_OUT}"], check=True)
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--window-size=1600,840", "--force-device-scale-factor=2", f"--screenshot={PNG_OUT}", f"file://{HTML_OUT}"], check=True)

    print(f"Wrote {PDF_OUT} ({PDF_OUT.stat().st_size:,} bytes)")
    print(f"Wrote {PNG_OUT} ({PNG_OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
