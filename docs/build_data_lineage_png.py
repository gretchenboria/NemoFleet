"""Build the NemoFleet Data & Model Lineage diagram (docs/img/data-lineage.png).

Usage:
    python3 docs/build_data_lineage_png.py [out.png]
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "pdf.fonttype": 42,
})

W, H = 160, 92
INK, MUTED, LINE, BG = "#16202a", "#52606d", "#d5dbe1", "#f7f8f5"
NV, NB, CF, PURP, TEAL, AMBER = "#5f8f00", "#a3c400", "#f38020", "#6d4aff", "#0e8579", "#b45309"

BADGES = {
    "shipped": ("#1f7a3f", "#e6f6ec", "PROMOTED"),
    "live": ("#2563eb", "#eaf1ff", "LIVE"),
    "ccby": ("#0e8579", "#e6f7f5", "CC BY 4.0"),
    "nc": ("#b45309", "#fff4dc", "NON-COMM"),
    "ablation": ("#52606d", "#eef1f4", "ABLATION"),
}


def pill(ax, x, y, kind, size=6.6):
    edge, fill, label = BADGES[kind]
    ax.text(
        x, y, label, fontsize=size, color=edge, fontweight="bold", ha="right", va="center",
        family="monospace", bbox=dict(boxstyle="round,pad=0.24,rounding_size=0.55", fc=fill, ec=edge, lw=0.8),
    )


def card(ax, x, y, w, h, title, lines=(), stripe=NV, badge_kind=None, title_size=9.6, line_size=7.7, highlight=False):
    ec = NV if highlight else LINE
    fc = "#ffffff" if not highlight else "#f9fdf2"
    lw = 1.6 if highlight else 1.15
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.1", fc=fc, ec=ec, lw=lw))
    if stripe:
        ax.add_patch(FancyBboxPatch((x, y), 0.85, h, boxstyle="round,pad=0,rounding_size=0.4", fc=stripe, ec="none"))
    ax.text(x + 1.8, y + h - 2.1, title, fontsize=title_size, color=INK, fontweight="bold", va="center")
    step = (h - 4.0) / max(len(lines), 1)
    step = min(step, 2.35)
    for i, ln in enumerate(lines):
        bold = ln.startswith("★") or ln.startswith("•")
        col = "#1f7a3f" if ln.startswith("★") else INK if bold else MUTED
        ax.text(
            x + 1.8, y + h - 4.6 - i * step, ln,
            fontsize=line_size, color=col, fontweight="bold" if ln.startswith("★") else "normal", va="center",
        )
    if badge_kind:
        pill(ax, x + w - 0.9, y + h - 2.1, badge_kind)


def region(ax, x, y, w, h, label, color, sub=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.6", fc=color + "12", ec=color + "80", lw=1.15))
    ax.text(x + 1.6, y + h - 1.8, label.upper(), fontsize=8.4, color=color, fontweight="bold", family="monospace", va="center")
    if sub:
        ax.text(x + w - 1.6, y + h - 1.8, sub, fontsize=7.6, color=MUTED, ha="right", va="center")


def arrow(ax, a, b, color=INK, rad=0.0, dashed=False, lw=1.35):
    ax.add_patch(
        FancyArrowPatch(
            a, b, arrowstyle="-|>", mutation_scale=11, color=color, lw=lw,
            connectionstyle=f"arc3,rad={rad}", ls=(0, (4, 3)) if dashed else "-", shrinkA=1.5, shrinkB=1.5,
        )
    )


def build(out_path: Path):
    fig = plt.figure(figsize=(16, 9.2), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    fig.patch.set_facecolor(BG)

    # Top accent bar
    ax.add_patch(Rectangle((0, H - 1.0), W * 0.5, 1.0, color=NV, lw=0))
    ax.add_patch(Rectangle((W * 0.5, H - 1.0), W * 0.5, 1.0, color=NB, lw=0))

    # Header
    ax.text(3.5, H - 4.5, "NEMOFLEET · DATA & MODEL LINEAGE · PHYSICAL AI", fontsize=9.5, color=MUTED, fontweight="bold", family="monospace")
    ax.text(3.5, H - 8.5, "Training Data, Splits & Dual-LoRA Lineage on Nebius + NVIDIA Nemotron", fontsize=21.5, color=INK, fontweight="bold")
    ax.text(
        3.5, H - 11.7,
        "Two single-task LoRA adapters trained on Nebius spot H200 GPUs via SkyPilot and co-served on one NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 base model.",
        fontsize=10.5, color=MUTED,
    )

    # =========================================================================
    # TRACK 1: DECISION DISTILLATION (decide-1) — y = 47..77
    # =========================================================================
    region(
        ax, 3.0, 47.0, 127.5, 30.0,
        "Track 1 · Night Shift Decision Distillation (Adapter: decide-1 · \"Decide like Ultra\")",
        NV, "tools/night_shift/distill.cjs  →  tools/ego_mix/train.py  →  tools/night_shift/gate_eval.py",
    )

    card(
        ax, 4.5, 49.0, 28.5, 24.2,
        "1. Incident Episode Generator",
        [
            "Model: Nemotron 3 Super 120B",
            "Runs on: Nebius Token Factory",
            "• 519 multi-step episodes",
            "• 2,076 events across 24 hazard types",
            "• 4 beats per cell: first sighting,",
            "  repeat (memory), variant, routine",
            "• Data halls & fulfillment warehouses",
        ],
        stripe=NB, badge_kind="live",
    )

    card(
        ax, 35.5, 49.0, 29.5, 24.2,
        "2. Teacher & Baseline Labels",
        [
            "Teacher: Nemotron 3 Ultra 550B",
            "• 2,076 strict-schema JSON decisions",
            "• Production prompt + FleetAction schema",
            "• Teacher cost: $3.34 (433 in / 425 out tok)",
            "Baseline student: Nemotron 3 Nano 30B",
            "• Served w/ reasoning: 81% agreement",
            "• Untuned direct answer: 65% agreement",
        ],
        stripe=NV, badge_kind="live",
    )

    card(
        ax, 67.5, 49.0, 28.5, 24.2,
        "3. Category-Disjoint Split",
        [
            "Path: data/night_shift/decide_v1/",
            "Zero hazard-category leakage:",
            "• Train: 1,360 events (16 hazard types)",
            "• Val:   384 events (4 unseen types)",
            "• Test:  332 events (4 unseen types)",
            "Unseen test hazards include categories",
            "Nano never saw during LoRA training",
        ],
        stripe=TEAL,
    )

    card(
        ax, 98.5, 49.0, 30.5, 24.2,
        "4. Fine-Tune & Gate (decide-1)",
        [
            "LoRA r=16 · 3 epochs · 6 min spot H200",
            "★ Test agreement: 88% (291 / 332)",
            "• First sighting: 46% → 81% (+35 pt)",
            "• Scene variant:  48% → 77% (+29 pt)",
            "• Repeat w/ mem:  72% → 96% (+24 pt)",
            "★ Action-token probability gate:",
            "  Settles 64% (212/332) w/ 1.9% error",
        ],
        stripe=NV, badge_kind="shipped", highlight=True,
    )

    arrow(ax, (33.0, 61.1), (35.5, 61.1), color=NV)
    arrow(ax, (65.0, 61.1), (67.5, 61.1), color=NV)
    arrow(ax, (96.0, 61.1), (98.5, 61.1), color=NV)

    # =========================================================================
    # TRACK 2: SAFETY TRIGGER (plan-1 & ablations) — y = 5.5..44.5
    # =========================================================================
    region(
        ax, 3.0, 5.5, 127.5, 39.0,
        "Track 2 · 5-Second Path-Aware Safety Trigger (Adapter: plan-1 · \"Is a person in the way?\")",
        PURP, "tools/ego_mix/{adapt_magni,adapt_waymo,adapt_smartspaces,featurize,train,score}.py",
    )

    # 3 stacked dataset source cards on left (x = 4.5..36.5)
    card(
        ax, 4.5, 31.2, 32.0, 9.8,
        "A. THÖR-MAGNI Motion Capture",
        [
            "Vicon 100 Hz · DARKO_Robot + Helmet_1..10",
            "Scenarios 1–2 (22 runs, plan-1) · SC1–5 (48 runs, magni-1)",
            "Robot & Human ego viewpoints in industrial layout",
        ],
        stripe=TEAL, badge_kind="ccby", title_size=8.9, line_size=7.2,
    )

    card(
        ax, 4.5, 18.2, 32.0, 11.6,
        "B. Waymo Open Motion v1.3.1 (Scenario)",
        [
            "gs://waymo_open_dataset_motion_v_1_3_1/",
            "• training.tfrecord-00000..00069-of-01000 (70 shards)",
            "  → 16,359 scenarios → 6,432 train rows (1,608 pos)",
            "• validation.tfrecord-00000..00019-of-00150 (20 shards)",
            "  → 1,404 val + 1,404 test scenarios (9.1 s @ 10 Hz)",
        ],
        stripe=AMBER, badge_kind="nc", title_size=8.8, line_size=7.0,
    )

    card(
        ax, 4.5, 7.2, 32.0, 9.6,
        "C. NVIDIA PhysicalAI-SmartSpaces",
        [
            "19 Omniverse warehouse/smart-space scenes",
            "NovaCarter & Transporter AMRs (3–120 people)",
            "14,613 robot-ego samples (train-only in sim-1)",
        ],
        stripe=NV, badge_kind="ccby", title_size=8.9, line_size=7.2,
    )

    # Card 2: Featurization & Split (x = 39.0..68.0)
    card(
        ax, 39.0, 7.2, 28.5, 33.8,
        "2. Featurization & Split",
        [
            "featurize.py --plan (ego frame):",
            "• Nearby people: last 2.0 s (x, y)",
            "• Ego past path + 5.0 s planned path",
            "• Collision zone: 2.5×1.2m (robot)",
            "",
            "2 : 1 : 2 Training Mix (16,080 rows):",
            "• 6,435 Human ego (THÖR-MAGNI)",
            "• 3,213 Robot ego (THÖR-MAGNI)",
            "• 6,432 Vehicle ego (Waymo)",
            "",
            "Run-Disjoint Val & Test Splits:",
            "• SHA-256: 445780d9 val / ab6cdeb3 test",
            "• Robot: 441 val + 339 test (216 pos)",
            "• Human: 922 val + 890 test (798 pos)",
            "• Vehicle: 1,636 val + 1,635 test",
        ],
        stripe=PURP,
    )

    # Card 3: 5-Run Ablation Tournament (x = 70.0..99.0)
    card(
        ax, 70.0, 7.2, 28.5, 33.8,
        "3. Spot-H200 Ablation Suite",
        [
            "Pooled Val+Test Robot Recall",
            "(at constant-velocity false-alarm rate):",
            "• Const-velocity baseline: 74.1%",
            "• Untuned Nano 30B: chance (0.57 AUC)",
            "• main-1 (positions only): 74.5%",
            "• no-waymo / equal-thirds: 74.5% / 75.5%",
            "★ plan-1 (+ planned path): 80.1%",
            "  (+6.0 pt, CI +0.5..+11.7 · 70m · $0.95)",
            "• sim-1 (+3.2k SmartSpaces): 81.5%",
            "  (rejected: -3.3 pt on human ego)",
            "• plan-r32 (LoRA rank 32): 78.7%",
            "• magni-1 (all 48 MAGNI runs): 78.7%",
            "  (82.4% test recall · 0.0593 val loss)",
            "• multi-1 (joint adapter): 0.868 AUC",
        ],
        stripe=NB, badge_kind="ablation",
    )

    # Card 4: Promoted Trigger Adapter (x = 101.0..129.0)
    card(
        ax, 101.0, 7.2, 28.0, 33.8,
        "4. Shipped Trigger (plan-1)",
        [
            "LoRA r=16 · 2 epochs · 16,080 rows",
            "★ Robot recall:   74.1% → 80.1%",
            "★ Human recall:   53.9% → 68.5%",
            "★ Vehicle recall: 87.8% → 90.0%",
            "• Test AUROC: 0.92 robot · 0.995 veh",
            "• Valid JSON output: 300 / 300 (100%)",
            "• Timing MAE: 0.21 s on t_s",
            "",
            "Live Calibrated Threshold:",
            "• Chosen on val at baseline val FAR:",
            "★ Score cut = -0.75 (logit gap)",
            "• Test recall: 76.9% (91 positives)",
            "• Test false-alarm rate: 13.7%",
        ],
        stripe=NV, badge_kind="shipped", highlight=True,
    )

    arrow(ax, (36.5, 35.9), (39.0, 32.0), color=TEAL)
    arrow(ax, (36.5, 24.1), (39.0, 24.1), color=AMBER)
    arrow(ax, (36.5, 12.3), (39.0, 16.0), color=NV, dashed=True)
    arrow(ax, (67.5, 24.1), (70.0, 24.1), color=PURP)
    arrow(ax, (98.5, 24.1), (101.0, 24.1), color=PURP)

    # =========================================================================
    # RIGHT COLUMN: PRODUCTION SERVING & CONSOLE — x = 133.0..157.0
    # =========================================================================
    region(
        ax, 132.5, 5.5, 24.5, 71.5,
        "Production Loop",
        CF, "Live",
    )

    card(
        ax, 133.8, 43.5, 21.9, 29.7,
        "Dual-LoRA + CUDA-X",
        [
            "tools/ego_mix/serve.py",
            "sky_serve.yaml (1× H200)",
            "Base: Nemotron 3 Nano",
            "      30B-A3B-BF16",
            "• CUDA-X Vision Pre-Gate:",
            "  CV-CUDA + TensorRT ROI",
            "• Adapter 1: decide",
            "  (decide-1/adapter)",
            "  + actions_probability",
            "• Adapter 2: inway",
            "  (plan-1/adapter)",
            "  + true/false logit gap",
            "• Fallback: Token Factory",
        ],
        stripe=NV, badge_kind="live", title_size=9.2, line_size=7.2,
    )

    card(
        ax, 133.8, 7.2, 21.9, 33.8,
        "Edge API & Console",
        [
            "publish.py writes:",
            "  config/night_shift.json",
            "",
            "Cloudflare Pages + D1/KV:",
            "functions/api/[[path]].js",
            "• POST /api/events",
            "• In-way score >= -0.75",
            "  → Safety escalate Ultra",
            "• Action prob >= gate",
            "  → Settle on Nano",
            "• Else → Nemotron Ultra",
            "• Stores cell precedent",
            "• Enforces Alarm Rules",
            "• Spatial Command Map",
        ],
        stripe=CF, badge_kind="live", title_size=9.2, line_size=7.4,
    )

    arrow(ax, (129.0, 61.1), (133.8, 61.1), color=NV, lw=1.6)
    arrow(ax, (129.0, 24.1), (133.8, 50.0), color=PURP, lw=1.6, rad=-0.12)
    arrow(ax, (129.0, 18.0), (133.8, 22.0), color=CF, lw=1.4, dashed=True)
    arrow(ax, (144.7, 43.5), (144.7, 41.0), color=CF, lw=1.5)

    # Footer
    ax.text(
        3.5, 2.1,
        "Lineage & artifacts: private HF repo gretchenboria/nemofleet-ego-lora (adapters & raw predictions) · config/night_shift.json (aggregates published to console)",
        fontsize=8.2, color=MUTED, family="monospace",
    )
    ax.text(
        W - 3.5, 2.1,
        "NemoFleet · Nebius × NVIDIA Global AI Hackathon · Physical AI Track",
        fontsize=8.5, color=MUTED, ha="right",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "img" / "data-lineage.png"
    build(out)
