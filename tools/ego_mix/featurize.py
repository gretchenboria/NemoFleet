"""Tracks files -> training samples (scene as text in, "in the way" JSON out).

  python3 tools/ego_mix/featurize.py OUT.jsonl [--plan] TRACKS.json|TRACKS.jsonl [...]

--plan writes the second prompt format: everything in the ego's frame at decision time, with the ego's own
past path and its planned path for the next 5 s (the recorded future path stands in for the plan). The
label and the samples are identical to the first format, so runs on the two can be compared row by row.

Label (fixed): a listed person is inside the ego's zone (common.ZONES, by embodiment) at
any recorded instant in the next HORIZON_S seconds. It comes from the recorded future, never from a model.
Only people visible now are listed, and only listed people can make the label true.
"""
import json
import math
import sys

from common import HIST_S, HORIZON_S, HZ, MAX_PEOPLE, STRIDE_S, SYSTEM, ZONES, in_zone, read_tracks


def to_frame(x, y, pose):
    """World point -> the frame of an ego at world pose (x, y, yaw)."""
    c, s = math.cos(-pose[2]), math.sin(-pose[2])
    dx, dy = x - pose[0], y - pose[1]
    return c * dx - s * dy, s * dx + c * dy


def to_world(x, y, pose):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return pose[0] + c * x - s * y, pose[1] + s * x + c * y


def plan_lines(doc, frames, i, hist, near, name, now):
    """Prompt body for --plan: ego past, ego plan, and each person's past, all in the ego's frame at step i."""
    e0 = frames[i]["ego"]
    pt = lambda x, y: f"({round(x, 1) + 0.0:.1f},{round(y, 1) + 0.0:.1f})"  # + 0.0 turns -0.0 into 0.0
    past = " ".join(pt(*to_frame(*frames[j]["ego"][:2], e0)) for j in range(i - hist, i, 2))
    plan = []
    for k in range(1, round(HORIZON_S) + 1):
        e = frames[i + k * HZ]["ego"]
        turn = math.degrees((e[2] - e0[2] + math.pi) % (2 * math.pi) - math.pi)
        plan.append(pt(*to_frame(*e[:2], e0))[:-1] + f",{round(turn) + 0})")
    lines = [f"EGO {doc['embodiment']} | site={doc['site']} | every point is in the ego's frame now: ego at (0,0) facing +x, y left, metres",
             f"EGO past, every {2 / HZ:.1f} s, oldest first: {past} now=(0.0,0.0)",
             f"EGO plan, every 1 s for {HORIZON_S:.0f} s, as (x,y,heading deg): {' '.join(plan)}",
             f"PEOPLE past, every {2 / HZ:.1f} s, oldest first, - where not seen:"]
    for k in near:
        pts = []
        for j in range(i - hist, i, 2):
            hit = next((p for p in frames[j]["people"] if p[0] == k), None)
            pts.append(pt(*to_frame(*to_world(hit[1], hit[2], frames[j]["ego"]), e0)) if hit else "-")
        lines.append(f"{name[k]} {' '.join(pts)} now=({now[k][0]:.1f},{now[k][1]:.1f})")
    return lines


def samples(doc, plan=False):
    assert doc["hz"] == HZ, "adapters must resample to common.HZ"
    frames = doc["frames"]
    ahead, half_w, reach = ZONES[doc["embodiment"]]
    hist, horizon, stride = round(HIST_S * HZ), round(HORIZON_S * HZ), round(STRIDE_S * HZ)
    for i in range(hist, len(frames) - horizon, stride):
        now = {p[0]: (p[1], p[2]) for p in frames[i]["people"]}
        near = sorted((k for k, (x, y) in now.items() if math.hypot(x, y) <= reach),
                      key=lambda k: math.hypot(*now[k]))[:MAX_PEOPLE]
        name = {k: f"P{n + 1}" for n, k in enumerate(near)}
        lines = plan_lines(doc, frames, i, hist, near, name, now) if plan else [
            f"EGO {doc['embodiment']} | site={doc['site']} | x forward, y left, metres, ego at (0,0), "
            f"points every {2 / HZ:.1f} s, oldest first"]
        for k in () if plan else near:
            pts = []
            for j in range(i - hist, i, 2):
                hit = next((p for p in frames[j]["people"] if p[0] == k), None)
                if hit:
                    pts.append(f"({hit[1]:.1f},{hit[2]:.1f})")
            lines.append(f"{name[k]} {' '.join(pts)} now=({now[k][0]:.1f},{now[k][1]:.1f})")
        if not near:
            lines.append("(no people in range)")
        lines.append(f"TASK will a person be in the ego's way (within {ahead} m ahead and {half_w} m to "
                     f"either side{' of the ego at any moment as it follows its plan' if plan else ''}) in the next {HORIZON_S:.0f} s?")
        answer = {"in_way": False, "person": None, "t_s": None}
        for j in range(i, i + horizon + 1):
            hits = [p for p in frames[j]["people"] if p[0] in name and in_zone(p[1], p[2], ahead, half_w)]
            if hits:
                first = min(hits, key=lambda p: math.hypot(p[1], p[2]))
                answer = {"in_way": True, "person": name[first[0]], "t_s": round((j - i) / HZ, 1)}
                break
        yield {"seq": doc["seq"], "group": doc["group"], "source": doc["source"], "embodiment": doc["embodiment"], "labels": doc["labels"],
               "split_hint": doc.get("split_hint"), "license": doc["license"], "t": frames[i]["t"], "system": SYSTEM, "prompt": "\n".join(lines),
               "answer": json.dumps(answer, separators=(",", ":"))}


def main(out, paths):
    plan = "--plan" in paths
    paths = [p for p in paths if p != "--plan"]
    n = pos = 0
    with open(out, "w") as f:
        for p in paths:
            for doc in read_tracks(p):
                for s in samples(doc, plan):
                    f.write(json.dumps(s) + "\n")
                    n += 1
                    pos += '"in_way":true' in s["answer"]
    print(f"{n} samples, {pos} positive ({100 * pos / max(n, 1):.1f}%) -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
