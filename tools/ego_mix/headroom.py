"""Does knowing the ego's own motion and planned path create headroom over constant velocity?

  uv run --no-project --python 3.12 --with scikit-learn --with numpy \
    python tools/ego_mix/headroom.py THOR-Magni_ICRA_Subset/human_motion CACHE.pkl      (run from the repo root)

A small gradient-boosted model per person, leave-runs-out over all 22 THÖR-MAGNI runs, with three feature sets:
what today's prompt holds, plus ego speed/turn and world-frame person velocity, plus the ego's planned path.
The "planned path" is the ego's recorded future path, which already contains its reaction to people, so the
v3 numbers are an upper bound on what a real planner's path would give.
"""
import glob, math, os, pickle, sys
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
sys.path.insert(0, "tools/ego_mix")
import adapt_magni

HZ, HIST, HOR, STRIDE, AHEAD, HALF, REACH = 5, 10, 25, 5, 2.5, 0.6, 10.0
SRC, CACHE = sys.argv[1], sys.argv[2]

def to_ego(p, e):
    c, s = math.cos(-e[2]), math.sin(-e[2]); dx, dy = p[0] - e[0], p[1] - e[1]
    return c * dx - s * dy, s * dx + c * dy
def zdist(x, y):
    return math.hypot(max(0.0, -x, x - AHEAD), max(0.0, abs(y) - HALF))
def sweep(rel):  # list of (x,y) per future step -> (enters, first time s, min zone distance)
    d = [zdist(x, y) for x, y in rel]
    hit = [k for k, v in enumerate(d) if v == 0.0]
    return (1.0 if hit else 0.0, hit[0] / HZ if hit else 9.0, min(d))
def vel(pts, k):  # pts: list of (x,y) or None, newest last; velocity over up to k steps
    if pts[-1] is None: return (math.nan, math.nan)
    for j in range(k, 0, -1):
        if len(pts) > j and pts[-1 - j] is not None:
            return ((pts[-1][0] - pts[-1 - j][0]) * HZ / j, (pts[-1][1] - pts[-1 - j][1]) * HZ / j)
    return (0.0, 0.0)

def build():
    rows = []
    for path in sorted(glob.glob(os.path.join(SRC, "*.csv"))):
        run = os.path.basename(path).split("Magni_")[-1][:-4]
        bodies = adapt_magni.load(path)
        helmets = [b for b in bodies if b.startswith("Helmet")]
        for ego in bodies:
            emb = "robot" if "Robot" in ego else "human" if ego.startswith("Helmet") else None
            if not emb: continue
            E = bodies[ego]
            for i in range(HIST, len(E) - HOR, STRIDE):
                if any(E[j] is None for j in range(i - HIST, i + HOR + 1)): continue
                e0 = E[i]
                # ego motion (history only)
                def ego_rate(k):
                    a = E[i - k]; fx, fy = to_ego((e0[0], e0[1]), a)  # displacement in the OLD ego frame ~ forward/lateral
                    dyaw = (e0[2] - a[2] + math.pi) % (2 * math.pi) - math.pi
                    return fx * HZ / k, fy * HZ / k, dyaw * HZ / k
                vf2, vl2, w2 = ego_rate(2); vf10, vl10, w10 = ego_rate(10)
                fut_ego = [E[i + k] for k in range(HOR + 1)]
                # ego constant speed + turn rate rollout (history only)
                ctrv, (x, y, th) = [], e0
                for k in range(HOR + 1):
                    ctrv.append((x, y, th)); th2 = th + w2 / HZ
                    x += (vf2 * math.cos(th) - vl2 * math.sin(th)) / HZ; y += (vf2 * math.sin(th) + vl2 * math.cos(th)) / HZ; th = th2
                plan_len = sum(math.hypot(fut_ego[k + 1][0] - fut_ego[k][0], fut_ego[k + 1][1] - fut_ego[k][1]) for k in range(HOR))
                plan_turn = (fut_ego[-1][2] - e0[2] + math.pi) % (2 * math.pi) - math.pi
                people = []
                for b in helmets:
                    if b == ego or bodies[b][i] is None: continue
                    rx, ry = to_ego(bodies[b][i], e0)
                    if math.hypot(rx, ry) <= REACH: people.append((math.hypot(rx, ry), b))
                people = [b for _, b in sorted(people)[:8]]
                for b in people:
                    P = bodies[b]
                    relh = [to_ego(P[j], E[j]) if P[j] is not None else None for j in range(i - HIST, i + 1)]      # as in the current prompt
                    wh = [(P[j][0], P[j][1]) if P[j] is not None else None for j in range(i - HIST, i + 1)]
                    label = any(P[j] is not None and zdist(*to_ego(P[j], E[j])) == 0.0 for j in range(i, i + HOR + 1))
                    t_s = next((j - i for j in range(i, i + HOR + 1) if P[j] is not None and zdist(*to_ego(P[j], E[j])) == 0.0), -1) / HZ
                    rx, ry = relh[-1]
                    rv2, rv10 = vel(relh, 2), vel(relh, 10)
                    f1 = [rx, ry, math.hypot(rx, ry), math.atan2(ry, rx), *rv2, *rv10,
                          *sweep([(rx + rv2[0] * k / HZ, ry + rv2[1] * k / HZ) for k in range(HOR + 1)]), len(people)]
                    base1 = f1[8]
                    wv2, wv10 = vel(wh, 2), vel(wh, 10)
                    c, s = math.cos(-e0[2]), math.sin(-e0[2])
                    cvw = [(wh[-1][0] + wv2[0] * k / HZ, wh[-1][1] + wv2[1] * k / HZ) for k in range(HOR + 1)]
                    f2 = [vf2, vl2, w2, vf10, vl10, w10, c * wv2[0] - s * wv2[1], s * wv2[0] + c * wv2[1], c * wv10[0] - s * wv10[1], s * wv10[0] + c * wv10[1],
                          math.hypot(*wv2), *sweep([to_ego(cvw[k], ctrv[k]) for k in range(HOR + 1)])]
                    sw_plan = sweep([to_ego(cvw[k], fut_ego[k]) for k in range(HOR + 1)])
                    f3 = [*sw_plan, *sweep([to_ego(wh[-1], fut_ego[k]) for k in range(HOR + 1)]), plan_len, plan_turn]
                    rows.append((run, emb, f"{ego}@{i}", label, t_s, base1, sw_plan[0], f1, f2, f3))
        print(run, len(rows), flush=True)
    return rows

rows = pickle.load(open(CACHE, "rb")) if os.path.exists(CACHE) else build()
if not os.path.exists(CACHE): pickle.dump(rows, open(CACHE, "wb"))
RUN = np.array([r[0] for r in rows]); EMB = np.array([r[1] for r in rows]); SID = np.array([r[0] + r[1] + r[2] for r in rows])
Y = np.array([r[3] for r in rows]); TS = np.array([r[4] for r in rows]); B1 = np.array([r[5] for r in rows]) > 0; B3 = np.array([r[6] for r in rows]) > 0
F = {"v1 ego-relative only (today's prompt)": np.array([r[7] for r in rows], float)}
F["v2 + ego speed/turn, person world velocity"] = np.hstack([F["v1 ego-relative only (today's prompt)"], np.array([r[8] for r in rows], float)])
F["v3 + ego planned path"] = np.hstack([F["v2 + ego speed/turn, person world velocity"], np.array([r[9] for r in rows], float)])
runs = sorted(set(RUN)); perm = np.random.default_rng(1).permutation(len(runs)); folds = [[runs[i] for i in perm[k::11]] for k in range(11)]

def sample_level(mask, score):  # max over people in a sample
    ids, inv = np.unique(SID[mask], return_inverse=True)
    out = np.full(len(ids), -np.inf); np.maximum.at(out, inv, score)
    y = np.zeros(len(ids), bool); np.logical_or.at(y, inv, Y[mask])
    later = np.ones(len(ids), bool); now = np.zeros(len(ids), bool); np.logical_or.at(now, inv, Y[mask] & (TS[mask] == 0)); later = y & ~now
    run = np.empty(len(ids), object); run[inv] = RUN[mask]
    return out, y, later, run
def at_far(s, y, far):
    neg = np.sort(s[~y])[::-1]; thr = neg[min(len(neg) - 1, int(far * len(neg)))]
    return s > thr
def run_ci(hit_a, hit_b, y, run):
    d = np.array([hit_a[(run == g) & y].mean() - hit_b[(run == g) & y].mean() for g in runs if ((run == g) & y).any()])
    bs = [np.random.default_rng(k).choice(d, len(d)).mean() for k in range(2000)]
    return d.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)

for emb in ("robot", "human"):
    m = EMB == emb
    b1, y, later, run = sample_level(m, B1[m].astype(float)); b1 = b1 > 0
    b3 = sample_level(m, B3[m].astype(float))[0] > 0
    far1, far3 = b1[~y].mean(), b3[~y].mean()
    print(f"\n{emb} ego: {len(y)} samples, {y.sum()} positives ({later.sum()} not yet in zone), {len(runs)} runs, leave-runs-out CV")
    print(f"  baseline A  constant velocity in the ego frame (today's bar):      recall {b1[y].mean():.3f} at {far1:.3f} false alarms | later-only {b1[later].mean():.3f}")
    print(f"  baseline B  person constant velocity against the ego's planned path: recall {b3[y].mean():.3f} at {far3:.3f} false alarms | later-only {b3[later].mean():.3f}")
    for name, X in F.items():
        S = np.full(m.sum(), np.nan); Xm, Ym, Rm = X[m], Y[m], RUN[m]
        for f in folds:
            te = np.isin(Rm, f)
            S[te] = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0).fit(Xm[~te], Ym[~te]).predict_proba(Xm[te])[:, 1]
        s = sample_level(m, S)[0]
        h1, h3 = at_far(s, y, far1), at_far(s, y, far3)
        pos, neg = s[y], s[~y]; auc = (np.searchsorted(np.sort(neg), pos, "left").sum() + 0.5 * (np.searchsorted(np.sort(neg), pos, "right") - np.searchsorted(np.sort(neg), pos, "left")).sum()) / (len(pos) * len(neg))
        d, lo, hi = run_ci(h1, b1, y, run)
        print(f"  model {name:44s} AUROC {auc:.3f} | at A's false alarms: recall {h1[y].mean():.3f}, later-only {h1[later].mean():.3f}, per-run diff vs A {d:+.3f} [{lo:+.3f}, {hi:+.3f}] | at B's false alarms: recall {h3[y].mean():.3f} vs {b3[y].mean():.3f}")
