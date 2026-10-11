"""JRDB (robot ego, human-annotated 3D boxes) -> tracks files.

  python3 tools/ego_mix/adapt_jrdb.py JRDB/train_dataset/labels/labels_3d OUT_DIR [--site indoor]

JRDB is CC BY-NC-SA 3.0 and needs an account (jrdb.erc.monash.edu). Anything derived from it, including a
mixed set or an adapter trained on one, stays private and non-commercial.
Expected layout, one file per scene: {"labels": {"000000.pcd": [{"label_id": "pedestrian:12",
"box": {"cx", "cy", "cz", ...}}, ...]}} at 15 Hz in the robot frame (x forward, y left).
NOT yet checked against a real download: confirm the keys and axes on the first file.
"""
import glob
import json
import os
import re
import sys

from common import HZ, write_tracks

SRC_HZ = 15


def convert(labels):
    frames, step = [], SRC_HZ // HZ
    for n, key in enumerate(sorted(labels)):
        if n % step:
            continue
        people = [[int(b["label_id"].split(":")[1]), round(b["box"]["cx"], 2), round(b["box"]["cy"], 2)]
                  for b in labels[key] if b["label_id"].startswith("pedestrian")]
        frames.append({"t": round(n / SRC_HZ, 2), "people": people})
    return frames


def main(src, out, site="unknown"):
    os.makedirs(out, exist_ok=True)
    for p in sorted(glob.glob(os.path.join(src, "*.json"))):
        seq = os.path.splitext(os.path.basename(p))[0]
        frames = convert(json.load(open(p))["labels"])
        write_tracks(os.path.join(out, f"jrdb-{seq}.tracks.json"), f"jrdb-{seq}", "jrdb", frames, site=site,
                     group=re.sub(r"-\d{4}-\d{2}-\d{2}_\d+$", "", seq))  # bytes-cafe-2019-02-07_0 -> bytes-cafe
        print(seq, len(frames), "frames")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[a.index("--site") + 1] if "--site" in a else "unknown")
