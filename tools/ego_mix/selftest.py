"""Checks the label, the JRDB adapter and the mixer on made-up tracks. No downloads.  python3 tools/ego_mix/selftest.py"""
import json
import math
import os
import struct
import subprocess
import sys
import tempfile

import adapt_jrdb
import adapt_waymo
from common import HZ, write_tracks
from featurize import samples

HERE = os.path.dirname(os.path.abspath(__file__))


def walk(start, vel, n=60):
    """One person walking at a constant ego-relative velocity."""
    return [{"t": i / HZ, "people": [[1, start[0] + vel[0] * i / HZ, start[1] + vel[1] * i / HZ]]} for i in range(n)]


def varint(n):
    out = b""
    while True:
        out += bytes([(n & 0x7F) | (0x80 if n > 0x7F else 0)])
        n >>= 7
        if not n:
            return out


def pb(num, value):
    """Encode one protobuf field: int -> varint, float -> double, ("f", x) -> float, bytes -> length-delimited."""
    if isinstance(value, bytes):
        return varint(num << 3 | 2) + varint(len(value)) + value
    if isinstance(value, tuple):
        return varint(num << 3 | 5) + struct.pack("<f", value[1])
    if isinstance(value, float):
        return varint(num << 3 | 1) + struct.pack("<d", value)
    return varint(num << 3) + varint(value)


def waymo_scenario(sid, ped_ahead):
    """A car driving north (+y) at 5 m/s for 9.1 s, one pedestrian standing ped_ahead metres up the road."""
    car = b"".join(pb(3, pb(2, 100.0) + pb(3, 0.5 * i) + pb(8, ("f", math.pi / 2)) + pb(11, 1)) for i in range(91))
    ped = b"".join(pb(3, pb(2, 100.3) + pb(3, ped_ahead) + pb(8, ("f", 0.0)) + pb(11, 1)) for i in range(91))
    return (pb(1, 0.0) + pb(5, sid.encode()) + pb(2, pb(1, 7) + pb(2, 1) + car) + pb(8, b"map feature, skipped")
            + pb(2, pb(1, 9) + pb(2, adapt_waymo.PEDESTRIAN) + ped) + pb(6, 0) + pb(10, 10))


def main():
    tmp = tempfile.mkdtemp(prefix="ego_mix_")
    files = []
    for emb in ("robot", "human"):
        for i in range(40):
            # even: walks straight at the ego from 8 m; odd: passes 3 m to the side. Two recordings per place.
            frames = walk((8.06, 0.2), (-1.0, 0.0)) if i % 2 == 0 else walk((8.06, 3.0), (-1.0, 0.0))
            p = os.path.join(tmp, f"{emb}{i}.tracks.json")
            write_tracks(p, f"syn-{emb}-{i}", "synthetic", frames, embodiment=emb, site="selftest", group=f"{emb}-place{i // 2}")
            files.append(p)

    head_on = list(samples(json.load(open(files[0]))))
    passing = list(samples(json.load(open(files[1]))))
    first = json.loads(head_on[0]["answer"])
    # at t=2 s the person is 6.06 m ahead closing at 1 m/s: first sampled inside 2.5 m after 3.6 s
    assert first == {"in_way": True, "person": "P1", "t_s": 3.6}, first
    assert "now=(6.1,0.2)" in head_on[0]["prompt"], head_on[0]["prompt"]
    assert all(json.loads(s["answer"])["in_way"] is False for s in passing)

    jr = adapt_jrdb.convert({f"{n:06d}.pcd": [{"label_id": "pedestrian:4", "box": {"cx": 3.0, "cy": -1.0, "cz": 0}},
                                              {"label_id": "bicycle:9", "box": {"cx": 1.0, "cy": 0.0, "cz": 0}}]
                             for n in range(30)})
    assert len(jr) == 10 and jr[0]["people"] == [[4, 3.0, -1.0]], jr[:1]

    # Waymo: TFRecord framing + protobuf decoding + rotation into the car's frame + the vehicle-sized zone
    for split, n in (("training", 30), ("validation", 10)):
        shard = os.path.join(tmp, f"{split}.tfrecord-00000-of-00001")
        with open(shard, "wb") as f:
            for k in range(n):  # even: pedestrian on the road ahead; odd: 200 m behind the start, never in range
                buf = waymo_scenario(f"{split[:2]}{k}", 20.0 if k % 2 == 0 else -200.0)
                f.write(struct.pack("<Q", len(buf)) + b"crc_" + buf + b"crc_")
        subprocess.run([sys.executable, os.path.join(HERE, "adapt_waymo.py"), tmp, "--official-split", split, shard],
                       check=True, stdout=subprocess.DEVNULL)
        files.append(os.path.join(tmp, f"waymo-{split}-{os.path.basename(shard).replace('.', '_')}.tracks.jsonl"))
    docs = [json.loads(line) for line in open(files[-2])]
    assert len(docs) == 15 and docs[0]["split_hint"] == "train" and docs[0]["embodiment"] == "vehicle", len(docs)
    # 2 s in, the car has driven 10 m: the pedestrian is 10 m ahead and 0.3 m to its right (y is left)
    assert docs[0]["frames"][10]["people"] == [[9, 10.0, -0.3]], docs[0]["frames"][10]
    veh = list(samples(docs[0]))
    assert json.loads(veh[0]["answer"]) == {"in_way": True, "person": "P1", "t_s": 0.6}, veh[0]["answer"]
    assert "within 7.5 m ahead and 1.5 m" in veh[0]["prompt"] and "within 2.5 m ahead and 0.6 m" in head_on[0]["prompt"]

    feats = os.path.join(tmp, "samples.jsonl")
    subprocess.run([sys.executable, os.path.join(HERE, "featurize.py"), feats, *files], check=True, stdout=subprocess.DEVNULL)
    out = os.path.join(tmp, "mix")
    subprocess.run([sys.executable, os.path.join(HERE, "mix.py"), out, feats], check=True, stdout=subprocess.DEVNULL)
    man = json.load(open(os.path.join(out, "manifest.json")))
    groups = man["splits"]["train"]["by_source"]
    n = {k.split("/")[0]: v["n"] for k, v in groups.items()}
    assert n["human"] == n["robot"] == n["vehicle"] > 0, groups
    meta = {s: [json.loads(line)["meta"] for line in open(os.path.join(out, f"{s}.jsonl"))] for s in ("train", "val", "test")}
    places = {s: {m["group"] for m in meta[s]} for s in meta}
    assert not (places["train"] & places["val"]) and not (places["train"] & places["test"]) and not (places["val"] & places["test"])
    for s in ("val", "test"):  # both embodiments, near 10% each, same positive rate as train
        assert {m["embodiment"] for m in meta[s]} == {"human", "robot", "vehicle"}, s
        assert all(m["seq"].startswith("waymo-va") for m in meta[s] if m["embodiment"] == "vehicle"), s  # official split kept
        nat = man["split_before_train_balancing"]
        for emb in ("human", "robot"):
            assert abs(nat[emb][s]["share"] - 0.10) < 0.03, nat
        for emb in nat:
            assert abs(nat[emb][s]["positive_rate"] - nat[emb]["train"]["positive_rate"]) < 0.05, nat
    assert all(m["seq"].startswith("waymo-tr") for m in meta["train"] if m["embodiment"] == "vehicle")
    assert man["warnings"] == [] and man["shareable"] is False, man  # Waymo makes the set non-commercial
    print("ego_mix selftest ok:", {s: v["n"] for s, v in man["splits"].items()})


if __name__ == "__main__":
    main()
