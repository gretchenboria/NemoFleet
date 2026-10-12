"""Shared schema and constants for the mixed human-ego + robot-ego "person in the way" set.

Every adapter writes one tracks file per recording:
  {"seq", "group", "source", "embodiment": "robot"|"human"|"vehicle", "labels": "annotated"|"pseudo", "license", "site", "hz": 5,
   "frames": [{"t": seconds, "ego": [x, y, yaw] (world pose, optional), "people": [[track_id, x, y], ...]}, ...]}
Positions are in the ego frame at that instant: ego at (0,0), x forward, y left, metres.
"group" is the place the recording was made; the mixer keeps a whole group in one split.
Because positions are ego-relative, the label needs no odometry and means the same thing for a robot
base, a person wearing a sensor helmet and a car; only the size of the zone changes (ZONES).
"""
import json

HZ = 5            # all adapters resample to this rate
HIST_S = 2.0      # history shown to the model
HORIZON_S = 5.0   # how far ahead the label looks
STRIDE_S = 1.0    # one sample per second of recording
MAX_PEOPLE = 8    # nearest N people listed per sample
RANGE_M = 10.0    # lidar adapters ignore clusters beyond this

# embodiment -> ("in the way" zone: metres ahead of the ego centre, metres to either side; listing range).
# The zone is stated in every prompt, so the model reads it rather than memorising one size.
# A car's centre is ~2.5 m behind its bumper and it is ~2.1 m wide, hence the larger vehicle zone.
ZONES = {"robot": (2.5, 0.6, 10.0), "human": (2.5, 0.6, 10.0), "vehicle": (7.5, 1.5, 30.0)}

# source -> (embodiment, label kind, licence). Licences: JRDB from jrdb.erc.monash.edu/dataset,
# MuSoHu from its Dataverse record (doi:10.13021/orc2020/HZI4LJ); SCAND's is NOT verified yet.
SOURCES = {
    "magni": (None, "annotated", "CC BY 4.0"),        # motion capture; embodiment set per viewpoint
    "smartspaces": (None, "simulated", "CC BY 4.0"),  # NVIDIA Omniverse-generated; exact positions, scripted people
    "waymo": ("vehicle", "annotated", "Waymo Dataset License Agreement for Non-Commercial Use (NC)"),
    "jrdb": ("robot", "annotated", "CC BY-NC-SA 3.0"),
    "musohu": ("human", "pseudo", "CC0 1.0"),
    "scand": ("robot", "pseudo", "UNVERIFIED"),
    "synthetic": (None, "annotated", "CC0 1.0"),  # selftest fixtures only
}

SYSTEM = ("You watch the people around a moving ego (a robot or a person) in a data center or AI factory. "
          "Answer with one JSON object and nothing else.")


def in_zone(x, y, ahead, half_w):
    return 0.0 < x <= ahead and abs(y) <= half_w


def tracks_doc(seq, source, frames, embodiment=None, site="unknown", group=None, split_hint=None):
    """split_hint "train" or "eval" pins the group to the dataset's own official split (see mix.py)."""
    emb, kind, lic = SOURCES[source]
    return {"seq": seq, "group": f"{source}:{group or seq}", "source": source, "embodiment": embodiment or emb,
            "labels": kind, "license": lic, "site": site, "split_hint": split_hint, "hz": HZ, "frames": frames}


def write_tracks(path, seq, source, frames, **kw):
    doc = tracks_doc(seq, source, frames, **kw)
    with open(path, "w") as f:
        json.dump(doc, f)
    return doc


def read_tracks(path):
    """One document per .json file, or one per line of a .jsonl file."""
    with open(path) as f:
        if path.endswith(".jsonl"):
            for line in f:
                yield json.loads(line)
        else:
            yield json.load(f)
