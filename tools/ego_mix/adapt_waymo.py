"""Waymo Open Motion Dataset (vehicle ego, annotated pedestrian tracks) -> tracks .jsonl, one per shard.

  python3 tools/ego_mix/adapt_waymo.py OUT_DIR --official-split training|validation SHARD.tfrecord [...]

A shard may be a local file or a gs:// URL. URLs are streamed through `gcloud storage cat` and never
written to disk, so no raw Waymo data is kept and a 450 MB shard needs no free space.

Input: the "scenario" TFRecord shards (uncompressed/scenario/training or .../validation), 9.1 s at 10 Hz
each. The self-driving car is the ego; pedestrians (and cyclists with --cyclists) are the people.
Scenarios where nobody comes within listing range are skipped. Waymo's own training/validation split is
kept as a hint, so mix.py never moves a validation scenario into train.

This file was made using the Waymo Open Dataset, provided by Waymo LLC under license terms available at
waymo.com/open. Non-commercial use only: the shards, anything this script writes, and any model trained
on it stay private and out of the public repo, site and video.

No TensorFlow or protobuf install needed: the record framing and the few fields used are decoded here.
Field numbers are from waymo_open_dataset/protos/scenario.proto (Scenario, Track, ObjectState).
"""
import json
import math
import os
import struct
import subprocess
import sys

from common import HZ, ZONES, tracks_doc

SRC_HZ = 10
PEDESTRIAN, CYCLIST = 2, 3


def records(path):
    """TFRecord framing: u64 length, u32 crc, payload, u32 crc."""
    proc = subprocess.Popen(["gcloud", "storage", "cat", path], stdout=subprocess.PIPE) if path.startswith("gs://") else None
    f = proc.stdout if proc else open(path, "rb")

    def take(n):  # a pipe may return fewer bytes than asked for
        buf = f.read(n)
        while buf and len(buf) < n and (more := f.read(n - len(buf))):
            buf += more
        return buf

    while head := take(12):
        (n,) = struct.unpack("<Q", head[:8])
        payload = take(n)
        take(4)
        if len(head) < 12 or len(payload) < n:
            raise IOError(f"{path}: stream ended mid-record")
        yield payload
    f.close()
    if proc and proc.wait():
        raise IOError(f"{path}: gcloud storage cat failed")


def fields(buf):
    """Protobuf wire format -> (field number, value); bytes for length-delimited, int for the rest."""
    i, n = 0, len(buf)
    while i < n:
        key = shift = 0
        while True:
            b = buf[i]; i += 1
            key |= (b & 0x7F) << shift; shift += 7
            if b < 0x80:
                break
        num, wire = key >> 3, key & 7
        if wire == 0:
            val = shift = 0
            while True:
                b = buf[i]; i += 1
                val |= (b & 0x7F) << shift; shift += 7
                if b < 0x80:
                    break
            yield num, val
        elif wire == 1:
            yield num, buf[i:i + 8]; i += 8
        elif wire == 5:
            yield num, buf[i:i + 4]; i += 4
        elif wire == 2:
            size = shift = 0
            while True:
                b = buf[i]; i += 1
                size |= (b & 0x7F) << shift; shift += 7
                if b < 0x80:
                    break
            yield num, buf[i:i + size]; i += size
        else:
            raise ValueError(f"unsupported wire type {wire}")


def state(buf):
    """ObjectState -> (x, y, heading) or None when not valid. center_x=2, center_y=3, heading=8, valid=11."""
    x = y = h = 0.0
    valid = False
    for num, v in fields(buf):
        if num == 2:
            (x,) = struct.unpack("<d", v)
        elif num == 3:
            (y,) = struct.unpack("<d", v)
        elif num == 8:
            (h,) = struct.unpack("<f", v)
        elif num == 11:
            valid = bool(v)
    return (x, y, h) if valid else None


def scenario(buf):
    """Scenario -> (scenario_id, sdc_track_index, [(track id, object type, [state, ...]), ...])."""
    sid, sdc, tracks = "", -1, []
    for num, v in fields(buf):
        if num == 5:    # scenario_id
            sid = v.decode()
        elif num == 6:  # sdc_track_index
            sdc = v
        elif num == 2:  # tracks
            tid, kind, states = 0, 0, []
            for n2, v2 in fields(v):
                if n2 == 1:
                    tid = v2
                elif n2 == 2:
                    kind = v2
                elif n2 == 3:
                    states.append(state(v2))
            tracks.append((tid, kind, states))
    return sid, sdc, tracks


def convert(buf, kinds):
    sid, sdc, tracks = scenario(buf)
    if not 0 <= sdc < len(tracks):
        return None
    ego = tracks[sdc][2][::SRC_HZ // HZ]
    if any(s is None for s in ego):
        return None  # the label needs the ego at every step
    people = [(tid, states[::SRC_HZ // HZ]) for tid, kind, states in tracks if kind in kinds]
    reach, frames, seen = ZONES["vehicle"][2], [], False
    for f, (ex, ey, yaw) in enumerate(ego):
        c, s = math.cos(-yaw), math.sin(-yaw)
        row = []
        for tid, states in people:
            p = states[f] if f < len(states) else None
            if p:
                dx, dy = p[0] - ex, p[1] - ey
                x, y = c * dx - s * dy, s * dx + c * dy
                row.append([tid, round(x, 2), round(y, 2)])
                seen = seen or math.hypot(x, y) <= reach
        frames.append({"t": round(f / HZ, 2), "ego": [round(ex, 3), round(ey, 3), round(yaw, 4)], "people": row})
    return (sid, frames) if seen else None


def main():
    a = sys.argv[1:]
    official = a[a.index("--official-split") + 1]
    hint = {"training": "train", "validation": "eval"}[official]
    kinds = {PEDESTRIAN, CYCLIST} if "--cyclists" in a else {PEDESTRIAN}
    os.makedirs(a[0], exist_ok=True)
    for shard in (p for p in a[1:] if "tfrecord" in p):
        kept = total = 0
        out = os.path.join(a[0], f"waymo-{official}-{os.path.basename(shard).replace('.', '_')}.tracks.jsonl")
        with open(out + ".part", "w") as f:  # renamed only when the whole shard was read
            for buf in records(shard):
                total += 1
                got = convert(buf, kinds)
                if got:
                    sid, frames = got
                    f.write(json.dumps(tracks_doc(f"waymo-{sid}", "waymo", frames, site="road", split_hint=hint)) + "\n")
                    kept += 1
        os.replace(out + ".part", out)
        print(f"{os.path.basename(shard)}: {kept} of {total} scenarios have a person in range -> {out}")


if __name__ == "__main__":
    main()
