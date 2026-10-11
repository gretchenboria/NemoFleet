"""The bar a fine-tuned model has to beat: constant-velocity extrapolation of each listed person.

  python3 tools/ego_mix/baseline.py data/ego_mix/test.jsonl

Uses only what the model is shown (the points in the prompt). Predicts "in the way" if any person, carried
forward at their last velocity, enters the zone within the horizon. For prompts made with featurize --plan
the zone moves along the ego's planned path (interpolated between the 1 s plan points).
"""
import collections
import json
import math
import re
import sys

from common import HORIZON_S, HZ, in_zone

STEP_S = 2 / HZ  # spacing of the history points in the prompt


def ego_at(plan, t):
    """Planned ego pose (x, y, heading rad) at t seconds, linear between the 1 s plan points."""
    pts = [(0.0, 0.0, 0.0)] + plan
    k = min(int(t), len(pts) - 2)
    a, b, f = pts[k], pts[k + 1], t - k
    return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), math.radians(a[2] + f * ((b[2] - a[2] + 180) % 360 - 180))


def predict_plan(prompt, ahead, half_w):
    line = next(l for l in prompt.split("\n") if l.startswith("EGO plan"))
    plan = [tuple(map(float, m)) for m in re.findall(r"\((-?[\d.]+),(-?[\d.]+),(-?[\d.]+)\)", line)]
    for line in prompt.split("\n"):
        if not re.match(r"P\d+ ", line):
            continue
        toks = line.split()[1:]
        cur = tuple(map(float, re.findall(r"-?[\d.]+", toks[-1])))
        prev = tuple(map(float, re.findall(r"-?[\d.]+", toks[-2]))) if len(toks) > 1 and toks[-2] != "-" else cur
        vx, vy = (cur[0] - prev[0]) / STEP_S, (cur[1] - prev[1]) / STEP_S
        for k in range(round(HORIZON_S * HZ) + 1):
            ex, ey, eh = ego_at(plan, k / HZ)
            dx, dy = cur[0] + vx * k / HZ - ex, cur[1] + vy * k / HZ - ey
            c, s = math.cos(-eh), math.sin(-eh)
            if in_zone(c * dx - s * dy, s * dx + c * dy, ahead, half_w):
                return True
    return False


def predict(prompt):
    ahead, half_w = map(float, re.search(r"within ([\d.]+) m ahead and ([\d.]+) m", prompt).groups())
    if "EGO plan" in prompt:
        return predict_plan(prompt, ahead, half_w)
    for line in prompt.split("\n"):
        if not re.match(r"P\d+ ", line):
            continue
        pts = [(float(x), float(y)) for x, y in re.findall(r"\((-?[\d.]+),(-?[\d.]+)\)", line)]
        (x, y), prev = pts[-1], pts[-2] if len(pts) > 1 else pts[-1]
        vx, vy = (x - prev[0]) / STEP_S, (y - prev[1]) / STEP_S
        if any(in_zone(x + vx * k / HZ, y + vy * k / HZ, ahead, half_w) for k in range(round(HORIZON_S * HZ) + 1)):
            return True
    return False


def main(path):
    c = collections.defaultdict(collections.Counter)
    for line in open(path):
        d = json.loads(line)
        user, truth = d["messages"][1]["content"], json.loads(d["messages"][2]["content"])["in_way"]
        for key in ("all", d["meta"]["embodiment"]):
            c[key][(truth, predict(user))] += 1
    for key, k in sorted(c.items()):
        tp, fn, fp, tn = k[(True, True)], k[(True, False)], k[(False, True)], k[(False, False)]
        print(f"{key:6s} n={tp + fn + fp + tn:5d}  recall {tp / max(tp + fn, 1):.3f}  precision {tp / max(tp + fp, 1):.3f}  "
              f"false-alarm rate {fp / max(fp + tn, 1):.3f}  accuracy {(tp + tn) / max(tp + fn + fp + tn, 1):.3f}")


if __name__ == "__main__":
    main(sys.argv[1])
