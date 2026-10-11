"""ROS1 bag with a 3D lidar + odometry (MuSoHu helmet rig, SCAND robots) -> tracks file with PSEUDO labels.

  uv run --no-project --python 3.12 --with rosbags --with numpy \
    python tools/ego_mix/adapt_bag.py FILE.bag OUT_DIR --source musohu [--sensor-height 1.7] [--site campus]

These datasets carry no people annotations, so people are found geometrically: person-sized lidar clusters
that move in the world frame. Standing or crouching people are missed and other moving objects of that size
are kept. Treat the output as noisy until it is scored against JRDB's annotated tracks (same sensor class).
"""
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore, get_types_from_msg

from common import HZ, RANGE_M, write_tracks

CELL = 0.15           # clustering grid, metres
MIN_PTS, MAX_EXTENT, MIN_TALL = 8, 1.0, 0.5
GATE = 0.8            # max jump between frames for the same track, metres
MIN_LIFE_S, MIN_MOVE_M = 1.5, 0.7
MAX_SPEED = 2.5       # m/s; faster "people" are tracking errors


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def read(path, cloud_topic, odom_topic):
    ts = get_typestore(Stores.ROS1_NOETIC)
    clouds, poses = [], []
    with Reader(Path(path)) as r:
        for c in r.connections:
            try:
                ts.register(get_types_from_msg(c.msgdef.data if hasattr(c.msgdef, "data") else c.msgdef, c.msgtype))
            except Exception:
                pass  # already known to the store
        for c, t, raw in r.messages():
            if c.topic == cloud_topic:
                m = ts.deserialize_ros1(raw, c.msgtype)
                a = np.frombuffer(m.data, dtype=np.uint8).reshape(-1, m.point_step)
                xyz = np.frombuffer(a[:, :12].tobytes(), dtype="<f4").reshape(-1, 3)
                clouds.append((t / 1e9, xyz[np.isfinite(xyz).all(1)]))
            elif c.topic == odom_topic:
                m = ts.deserialize_ros1(raw, c.msgtype)
                if c.msgtype.endswith("Path"):
                    if not m.poses:
                        continue
                    p = m.poses[-1].pose
                else:  # nav_msgs/Odometry
                    p = m.pose.pose
                poses.append((t / 1e9, p.position.x, p.position.y, yaw_of(p.orientation)))
    return clouds, poses


def clusters(xyz, zlo, zhi):
    r = np.hypot(xyz[:, 0], xyz[:, 1])
    pts = xyz[(r > 0.4) & (r < RANGE_M + 2) & (xyz[:, 2] > zlo) & (xyz[:, 2] < zhi)]
    cells = {}
    for i, (cx, cy) in enumerate(np.floor(pts[:, :2] / CELL).astype(int)):
        cells.setdefault((cx, cy), []).append(i)
    out, seen = [], set()
    for start in cells:
        if start in seen:
            continue
        seen.add(start)
        stack, idx = [start], []
        while stack:
            cx, cy = stack.pop()
            idx += cells[(cx, cy)]
            for n in ((cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                if n in cells and n not in seen:
                    seen.add(n)
                    stack.append(n)
        p = pts[idx]
        ext = p.max(0) - p.min(0)
        if len(p) >= MIN_PTS and max(ext[0], ext[1]) <= MAX_EXTENT and ext[2] >= MIN_TALL:
            out.append(p[:, :2].mean(0))
    return out


def convert(clouds, poses, sensor_height):
    pt = np.array([p[0] for p in poses])
    px, py = np.array([p[1] for p in poses]), np.array([p[2] for p in poses])
    pyaw = np.unwrap([p[3] for p in poses])
    t0, step = clouds[0][0], 1.0 / HZ
    scans, next_t = [], clouds[0][0]
    for t, xyz in clouds:  # resample to HZ
        if t + 1e-6 >= next_t and pt[0] <= t <= pt[-1]:
            scans.append((t, xyz))
            next_t = t + step * 0.9
    tracks, live, nid = {}, {}, 0  # id -> [(frame, wx, wy)], id -> (frame, wx, wy)
    ego = []
    for f, (t, xyz) in enumerate(scans):
        ex, ey, eyaw = np.interp(t, pt, px), np.interp(t, pt, py), np.interp(t, pt, pyaw)
        ego.append((t, ex, ey, eyaw))
        c, s = math.cos(eyaw), math.sin(eyaw)
        det = [(ex + c * x - s * y, ey + s * x + c * y) for x, y in clusters(xyz, 0.3 - sensor_height, 1.9 - sensor_height)]
        free = {k: v for k, v in live.items() if f - v[0] <= 3}
        for wx, wy in det:
            k = min(free, key=lambda k: math.hypot(free[k][1] - wx, free[k][2] - wy), default=None)
            if k is None or math.hypot(free[k][1] - wx, free[k][2] - wy) > GATE:
                k, nid = nid, nid + 1
                tracks[k] = []
            else:
                del free[k]
            tracks[k].append((f, wx, wy))
            live[k] = (f, wx, wy)
    moving = {k: v for k, v in tracks.items()
              if (v[-1][0] - v[0][0]) / HZ >= MIN_LIFE_S and MIN_MOVE_M <= math.hypot(v[-1][1] - v[0][1], v[-1][2] - v[0][2]) <= MAX_SPEED * (v[-1][0] - v[0][0]) / HZ}
    frames = [{"t": round(t - t0, 2), "people": []} for t, *_ in ego]
    for k, v in moving.items():
        for f, wx, wy in v:
            _, ex, ey, eyaw = ego[f]
            c, s = math.cos(-eyaw), math.sin(-eyaw)
            dx, dy = wx - ex, wy - ey
            frames[f]["people"].append([k, round(float(c * dx - s * dy), 2), round(float(s * dx + c * dy), 2)])
    return frames, len(tracks), len(moving)


def main():
    a = sys.argv[1:]
    opt = lambda name, d: a[a.index(name) + 1] if name in a else d
    source = opt("--source", "musohu")
    clouds, poses = read(a[0], opt("--cloud", "/velodyne_points"), opt("--odom", "/zed2/zed_node/path_odom"))
    if not clouds or len(poses) < 2:
        sys.exit(f"need lidar and odometry: {len(clouds)} clouds, {len(poses)} poses")
    frames, n_all, n_moving = convert(clouds, poses, float(opt("--sensor-height", "1.7")))
    seq = f"{source}-{Path(a[0]).stem}"
    os.makedirs(a[1], exist_ok=True)
    # 07172023_HE_RTC_3_neutral -> RTC: drop the date, the wearer's initials, the trial number and what follows
    group = re.sub(r"_\d+(_[A-Za-z]+)?$", "", re.sub(r"^\d+_([A-Z]{2}_)?", "", Path(a[0]).stem))
    write_tracks(os.path.join(a[1], f"{seq}.tracks.json"), seq, source, frames, site=opt("--site", "unknown"),
                 group=opt("--group", group))
    print(f"{seq}: {len(frames)} frames at {HZ} Hz, {n_all} person-sized clusters tracked, {n_moving} kept as moving")


if __name__ == "__main__":
    main()
