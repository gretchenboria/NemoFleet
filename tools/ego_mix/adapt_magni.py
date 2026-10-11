"""THÖR-MAGNI motion capture (CC BY 4.0, Zenodo, no sign-up) -> robot-ego AND human-ego tracks files.

  python3 tools/ego_mix/adapt_magni.py THOR-Magni_ICRA_Subset/human_motion OUT_DIR

Each run tracks one robot and up to ten people wearing marker helmets in a lab laid out as a shared
workspace. The same run is re-expressed from the robot's pose (robot ego) and from each helmet's pose
(human ego); the other helmets are the people. Positions are measured, so labels are ground truth and
standing people are kept. Checked on the demo subset: body x-axis is forward for helmets (0 +/- 4 deg
against direction of travel) and for the robot. The robot itself is not listed as a person.
Every viewpoint of one run shares one group, so a run never straddles train/val/test.
Cite: Schreiter et al., "THÖR-MAGNI", IJRR 2024. Demo subset: doi 10.5281/zenodo.7974709.
"""
import csv
import glob
import math
import os
import sys

from common import HZ, HIST_S, HORIZON_S, write_tracks

SRC_HZ = 100
MIN_FRAMES = round((HIST_S + HORIZON_S) * HZ) + 2  # shortest stretch that yields a sample


def load(path):
    """body -> list of (x m, y m, yaw) or None, at HZ."""
    with open(path, newline="", errors="replace") as fh:
        rd = csv.reader(fh)
        for row in rd:
            if row and row[0] == "Frame":
                col = {h: i for i, h in enumerate(row)}
                break
        bodies = sorted(h.split(" ")[0] for h in col if h.endswith(" Centroid_X"))
        out = {b: [] for b in bodies}
        for n, row in enumerate(rd):
            if n % (SRC_HZ // HZ):
                continue
            for b in bodies:
                try:
                    x, y, r0, r1 = (float(row[col[f"{b} {k}"]]) for k in ("Centroid_X", "Centroid_Y", "R0", "R1"))
                    out[b].append((x / 1000, y / 1000, math.atan2(r1, r0)))  # mm -> m; (R0, R1) is the body x-axis
                except (ValueError, KeyError, IndexError):
                    out[b].append(None)  # "N/A": not tracked in this frame
    return out


def ego_view(bodies, ego):
    """Contiguous stretches where the ego is tracked, as lists of frames in its own frame."""
    helmets = [b for b in bodies if b.startswith("Helmet") and b != ego]
    runs, cur = [], []
    for f, pose in enumerate(bodies[ego]):
        if pose is None:
            if len(cur) >= MIN_FRAMES:
                runs.append(cur)
            cur = []
            continue
        ex, ey, yaw = pose
        c, s = math.cos(-yaw), math.sin(-yaw)
        people = []
        for b in helmets:
            p = bodies[b][f]
            if p:
                dx, dy = p[0] - ex, p[1] - ey
                people.append([int(b.split("_")[1]), round(c * dx - s * dy, 2), round(s * dx + c * dy, 2)])
        cur.append({"t": round(f / HZ, 2), "ego": [round(ex, 3), round(ey, 3), round(yaw, 4)], "people": people})
    if len(cur) >= MIN_FRAMES:
        runs.append(cur)
    return runs


def main(src, out):
    os.makedirs(out, exist_ok=True)
    for path in sorted(glob.glob(os.path.join(src, "*.csv"))):
        run = os.path.splitext(os.path.basename(path))[0].split("Magni_")[-1]
        bodies = load(path)
        n = {"robot": 0, "human": 0}
        for ego in bodies:
            emb = "robot" if "Robot" in ego else "human" if ego.startswith("Helmet") else None
            if not emb:
                continue  # LO1 and other tracked objects
            for k, frames in enumerate(ego_view(bodies, ego)):
                seq = f"magni-{run}-{ego}-{k}"
                write_tracks(os.path.join(out, f"{seq}.tracks.json"), seq, "magni", frames, embodiment=emb,
                             site="indoor-workspace", group=run)
                n[emb] += len(frames)
        print(f"{run}: robot-ego {n['robot'] / HZ:.0f} s, human-ego {n['human'] / HZ:.0f} s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
