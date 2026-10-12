"""NVIDIA PhysicalAI-SmartSpaces (Omniverse-simulated warehouses, CC BY 4.0) -> robot-ego and human-ego tracks.

  uv run --no-project --python 3.12 --with ijson python tools/ego_mix/adapt_smartspaces.py OUT_DIR SCENE [...]

SCENE is a path inside the dataset such as MTMC_Tracking_2025/train/Warehouse_000 (its ground_truth.json is
streamed from Hugging Face, about 330 MB per scene, nothing is written to disk) or a local ground_truth.json.
Each 5 min scene has about 50 people, a few NovaCarter robots and a Transporter with exact 3D positions.
Robots are robot egos; --human-egos N (default 8) also takes N people per scene as human egos.
Checked on Warehouse_000: units are metres; a robot's box yaw is its direction of travel; a person faces
box yaw - 90 degrees. The people follow scripted routes, so this data is for training only: every track is
hinted "train" and never enters val or test.
Cite: NVIDIA, Physical AI Smart Spaces Dataset, huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces.
"""
import math
import os
import sys
import urllib.request

import ijson

from adapt_magni import ego_view
from common import HZ, write_tracks

SRC_HZ = 30
ROBOTS = ("NovaCarter", "Transporter")
BASE = "https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces/resolve/main/"


def load(scene):
    """body name -> list of (x, y, heading) or None per kept frame."""
    if os.path.exists(scene):
        stream = open(scene, "rb")
    else:
        stream = urllib.request.urlopen(urllib.request.Request(BASE + scene + "/ground_truth.json",
                                                               headers={"User-Agent": "NemoFleet/1.0"}), timeout=120)
    seen, last = {}, -1
    for fid, objs in ijson.kvitems(stream, "", use_float=True):
        f = int(fid)
        if f % (SRC_HZ // HZ):
            continue
        k = f // (SRC_HZ // HZ)
        last = max(last, k)
        for o in objs:
            o = {key.replace(" ", "_"): v for key, v in o.items()}  # 2025 files say "object type", the README "object_type"
            kind = o["object_type"]
            if kind != "Person" and kind not in ROBOTS:
                continue
            yaw = o["3d_bounding_box_rotation"][2] - (math.pi / 2 if kind == "Person" else 0.0)
            seen.setdefault(f"{kind}_{o['object_id']}", {})[k] = (o["3d_location"][0], o["3d_location"][1], yaw)
    return {b: [d.get(k) for k in range(last + 1)] for b, d in seen.items()}


def main():
    a = sys.argv[1:]
    n_human = int(a[a.index("--human-egos") + 1]) if "--human-egos" in a else 8
    scenes = [s for i, s in enumerate(a[1:], 1) if not s.startswith("--") and a[i - 1] != "--human-egos"]
    os.makedirs(a[0], exist_ok=True)
    for scene in scenes:
        name = "-".join(scene.rstrip("/").replace("/ground_truth.json", "").split("/")[-3:])
        bodies = load(scene)
        people = sorted(b for b in bodies if b.startswith("Person"))
        egos = [(b, "robot") for b in sorted(bodies) if b.startswith(ROBOTS)] + [(b, "human") for b in people[::max(1, len(people) // n_human)][:n_human]]
        secs = {"robot": 0, "human": 0}
        for ego, emb in egos:
            for k, frames in enumerate(ego_view(bodies, ego, people="Person")):
                seq = f"smart-{name}-{ego}-{k}"
                write_tracks(os.path.join(a[0], f"{seq}.tracks.json"), seq, "smartspaces", frames, embodiment=emb,
                             site="warehouse-sim", group=name, split_hint="train")
                secs[emb] += len(frames) / HZ
        print(f"{name}: {len(people)} people, robot-ego {secs['robot']:.0f} s, human-ego {secs['human']:.0f} s", flush=True)


if __name__ == "__main__":
    main()
