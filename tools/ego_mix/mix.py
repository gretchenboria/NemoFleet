"""Mix human-ego, robot-ego and vehicle-ego samples into train/val/test chat JSONL plus a manifest.

  python3 tools/ego_mix/mix.py OUT_DIR SAMPLES.jsonl [...] [--split 80,10,10] [--mix human:1,robot:1,vehicle:1]
                               [--neg-per-pos 3] [--open-only] [--seed 7] [--train-extra FILE:EMBODIMENT:N:POS_FRAC]

How the split is made, and why:
- By group, not by sample. Windows overlap (one per second, 7 s long) and one place is recorded several
  times, so a random split would put near-copies of training samples in val and test. A whole group
  (place, run or scenario) goes to exactly one split.
- A group keeps all its viewpoints together: a run seen from the robot and from each person is one event,
  so it must not be trained on from one viewpoint and tested on from another.
- A dataset's own official split is respected: groups hinted "train" stay in train and groups hinted
  "eval" go only to val or test (Waymo training vs validation shards).
- Within those limits the assignment is searched (seeded, repeatable) so that, for each embodiment
  separately, each split is close to its target share of samples and to the overall positive rate.
  Val and test therefore contain every embodiment and can be scored per embodiment.
- --neg-per-pos N caps train negatives at N per positive within each embodiment. Cars rarely have a
  person in their way (about 1 sample in 20), so without it "vehicle" alone would predict the answer.
- Only train is then balanced to --mix (default: equal parts of every embodiment present). Val and test
  keep the natural mix, because they are for measuring, and are never resampled.
The manifest lists warnings when a split rests on a single group, or misses its target share or the
overall positive rate by more than 5 points.
--open-only drops non-commercial and unverified sources so the result can be shared.
--train-extra appends N samples of one embodiment from another samples file to train only, at the given
positive fraction (for simulated data). Those rows never take part in the split, so val and test are unchanged.
"""
import collections
import json
import os
import random
import sys

SPLITS = ("train", "val", "test")
EMBS = ("human", "robot", "vehicle")
ALLOWED = {"train": ("train",), "eval": ("val", "test"), None: SPLITS}


def restricted(lic):
    return "NC" in lic or "UNVERIFIED" in lic


def is_pos(r):
    return '"in_way":true' in r["answer"]


def assign(rows, shares, seed, tries=40000):
    """group -> split. Searches for the assignment whose splits best match, for each embodiment, the target
    share of samples and the overall positive rate. Seeded, so the same inputs give the same split."""
    width = 2 * len(EMBS)
    tally = collections.defaultdict(lambda: [0] * width)  # group -> [n, positives] per embodiment
    allowed = {}
    for r in rows:
        i = 2 * EMBS.index(r["embodiment"])
        tally[r["group"]][i] += 1
        tally[r["group"]][i + 1] += is_pos(r)
        allowed[r["group"]] = ALLOWED[r.get("split_hint")]
    groups = sorted(tally)
    total = [sum(tally[g][i] for g in groups) for i in range(width)]
    # an embodiment with official-split hints has its train share fixed by the data, so only rates are matched
    hinted = [any(tally[g][i] and len(allowed[g]) < 3 for g in groups) for i in range(0, width, 2)]

    def loss(sums):
        out = 0.0
        for e, i in enumerate(range(0, width, 2)):
            if not total[i]:
                continue
            base = total[i + 1] / total[i]
            for s in SPLITS:
                n, p = sums[s][i], sums[s][i + 1]
                if not n:
                    out += 1.0  # an embodiment missing from a split is the worst outcome
                    continue
                out += (p / n - base) ** 2
                if not hinted[e]:
                    out += (n / total[i] - shares[s]) ** 2
            if hinted[e]:  # val and test should still be the same size as each other
                out += ((sums["val"][i] - sums["test"][i]) / total[i]) ** 2
        return out

    rng = random.Random(seed)
    free = [g for g in groups if len(allowed[g]) > 1]
    # propose moves evenly across sources, or thousands of Waymo scenarios would crowd out 22 lab runs
    pools = collections.defaultdict(list)
    for g in free:
        pools[g.split(":")[0]].append(g)
    pools = list(pools.values())
    best, best_loss = None, 1e9
    for _ in range(8):  # restarts
        where = {g: rng.choices(allowed[g], [shares[s] for s in allowed[g]])[0] for g in groups}
        sums = {s: [sum(tally[g][i] for g in groups if where[g] == s) for i in range(width)] for s in SPLITS}
        cur = loss(sums)
        for _ in range(tries // 8 if free else 0):
            g = rng.choice(rng.choice(pools))
            s, old = rng.choice(allowed[g]), where[g]
            if s == old:
                continue
            for i in range(width):
                sums[old][i] -= tally[g][i]
                sums[s][i] += tally[g][i]
            new = loss(sums)
            if new < cur:
                where[g], cur = s, new
            else:
                for i in range(width):
                    sums[old][i] += tally[g][i]
                    sums[s][i] -= tally[g][i]
        if cur < best_loss:
            best, best_loss = dict(where), cur
    return best


def main():
    a = sys.argv[1:]
    opt = lambda name, d: a[a.index(name) + 1] if name in a else d
    seed = int(opt("--seed", "7"))
    parts = [float(x) for x in opt("--split", "80,10,10").split(",")]
    shares = {s: p / sum(parts) for s, p in zip(SPLITS, parts)}
    rows = [json.loads(line) for p in a[1:] if p.endswith(".jsonl") for line in open(p)]
    if "--open-only" in a:
        rows = [r for r in rows if not restricted(r["license"])]
    present = [e for e in EMBS if any(r["embodiment"] == e for r in rows)]
    if "human" not in present or "robot" not in present:
        sys.exit(f"the mix needs human-ego and robot-ego samples; found {present}")
    weights = {k: float(v) for k, v in (kv.split(":") for kv in opt("--mix", ",".join(f"{e}:1" for e in present)).split(","))}

    by, warnings, natural = collections.defaultdict(list), [], {}
    where = assign(rows, shares, seed)
    for r in rows:
        by[where[r["group"]]].append(r)
    for emb in present:
        mine = [r for r in rows if r["embodiment"] == emb]
        hinted = any(r.get("split_hint") for r in mine)
        natural[emb] = {}
        for s in SPLITS:
            in_s = [r for r in mine if where[r["group"]] == s]
            groups = sorted({r["group"] for r in in_s})
            got = len(in_s) / len(mine)
            rate, base = sum(map(is_pos, in_s)) / max(len(in_s), 1), sum(map(is_pos, mine)) / len(mine)
            natural[emb][s] = {"groups": len(groups), "share": round(got, 3), "positive_rate": round(rate, 3)}
            if not groups:
                warnings.append(f"{emb}/{s}: empty")
                continue
            if len(groups) == 1 and s != "train":
                warnings.append(f"{emb}/{s}: rests on one group ({groups[0]}), so its score is that group's score")
            if abs(rate - base) > 0.05:
                warnings.append(f"{emb}/{s}: positive rate {100 * rate:.0f}%, overall {100 * base:.0f}%")
            if not hinted and abs(got - shares[s]) > 0.05:
                warnings.append(f"{emb}/{s}: {100 * got:.0f}% of samples, target {100 * shares[s]:.0f}%")

    rng = random.Random(seed)
    train = {e: [r for r in by["train"] if r["embodiment"] == e] for e in weights if weights[e] > 0}
    cap = float(opt("--neg-per-pos", "0"))
    for e in train if cap else ():
        pos, neg = [r for r in train[e] if is_pos(r)], [r for r in train[e] if not is_pos(r)]
        train[e] = pos + rng.sample(neg, min(len(neg), int(cap * len(pos))))
    unit = min(len(train[e]) / weights[e] for e in train)  # the scarcest embodiment sets the size
    by["train"] = [r for e in train for r in rng.sample(train[e], int(unit * weights[e]))]
    if "--train-extra" in a:
        path, emb, n, pos_frac = a[a.index("--train-extra") + 1].split(":")
        extra = [r for r in map(json.loads, open(path)) if r["embodiment"] == emb]
        pos, neg = [r for r in extra if is_pos(r)], [r for r in extra if not is_pos(r)]
        n_pos = round(int(n) * float(pos_frac))
        by["train"] += rng.sample(pos, min(len(pos), n_pos)) + rng.sample(neg, min(len(neg), int(n) - n_pos))
    rng.shuffle(by["train"])

    os.makedirs(a[0], exist_ok=True)
    manifest = {"split_target": shares, "train_mix": weights, "train_neg_per_pos_cap": cap or None, "seed": seed, "open_only": "--open-only" in a,
                "split_before_train_balancing": natural, "splits": {}, "warnings": warnings}
    for name in SPLITS:
        with open(os.path.join(a[0], f"{name}.jsonl"), "w") as f:
            for r in by[name]:
                f.write(json.dumps({"messages": [{"role": "system", "content": r["system"]},
                                                 {"role": "user", "content": r["prompt"]},
                                                 {"role": "assistant", "content": r["answer"]}],
                                    "meta": {k: r[k] for k in ("seq", "group", "source", "embodiment", "labels", "t")}}) + "\n")
        groups = collections.defaultdict(lambda: [0, 0])
        for r in by[name]:
            g = groups[f"{r['embodiment']}/{r['source']}/{r['labels']}"]
            g[0] += 1
            g[1] += is_pos(r)
        n = len(by[name])
        manifest["splits"][name] = {"n": n, "groups": len({r["group"] for r in by[name]}),
                                    "positive_rate": round(sum(map(is_pos, by[name])) / max(n, 1), 3),
                                    "by_source": {k: {"n": c, "positive": p} for k, (c, p) in sorted(groups.items())}}
    lic = sorted({r["license"] for rs in by.values() for r in rs})
    manifest["licenses"] = lic
    manifest["shareable"] = not any(restricted(x) for x in lic)
    json.dump(manifest, open(os.path.join(a[0], "manifest.json"), "w"), indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
