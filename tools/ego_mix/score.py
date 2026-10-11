"""Compare tuned-model scores with the constant-velocity baseline at the same false-alarm rate.

  python3 tools/ego_mix/score.py data/ego_runs/main-1 [data/ego_mix]

For each run and embodiment: the threshold is set on val so the model's false-alarm rate equals the
baseline's val false-alarm rate, then applied unchanged to test. The interval is a 95% bootstrap over test
samples of (model recall - baseline recall). "later" counts only positives where the person is not yet in
the zone at decision time.
"""
import glob
import json
import os
import random
import sys

from baseline import predict

EMBS = ("human", "robot", "vehicle")


def load(run_dir, tag, split, data):
    prompts = {}
    for line in open(os.path.join(data, f"{split}.jsonl")):
        d = json.loads(line)
        prompts[(d["meta"]["seq"], d["meta"]["t"])] = d["messages"][1]["content"]
    rows = json.load(open(os.path.join(run_dir, f"scores_{tag}_{split}.json")))["rows"]
    for r in rows:
        r["base"] = predict(prompts[(r["seq"], r["t"])])
    return rows


def rates(rows, flag):
    pos, neg = [r for r in rows if r["label"]], [r for r in rows if not r["label"]]
    return sum(flag(r) for r in pos) / max(len(pos), 1), sum(flag(r) for r in neg) / max(len(neg), 1)


def main(run_dir, data="data/ego_mix"):
    tags = sorted({os.path.basename(p)[7:-10] for p in glob.glob(os.path.join(run_dir, "scores_*_test.json"))})
    rng = random.Random(7)
    for emb in EMBS:
        print(f"\n{emb} ego, test")
        for tag in tags:
            val = [r for r in load(run_dir, tag, "val", data) if r["embodiment"] == emb]
            test = [r for r in load(run_dir, tag, "test", data) if r["embodiment"] == emb]
            _, base_far_val = rates(val, lambda r: r["base"])
            neg = sorted((r["score"] for r in val if not r["label"]), reverse=True)
            thr = neg[min(len(neg) - 1, int(base_far_val * len(neg)))]  # lets through the baseline's share of val negatives
            hit = lambda r: r["score"] > thr
            m_rec, m_far = rates(test, hit)
            b_rec, b_far = rates(test, lambda r: r["base"])
            later = [r for r in test if not (r["label"] and r["now"])]
            ml, _ = rates(later, hit)
            bl, _ = rates(later, lambda r: r["base"])
            diffs = []
            for _ in range(1000):
                s = [rng.choice(test) for _ in test]
                diffs.append(rates(s, hit)[0] - rates(s, lambda r: r["base"])[0])
            diffs.sort()
            print(f"  {tag:18s} recall {m_rec:.3f} at {m_far:.3f} false alarms | baseline {b_rec:.3f} at {b_far:.3f} | "
                  f"diff {m_rec - b_rec:+.3f} [{diffs[25]:+.3f}, {diffs[974]:+.3f}] | later-only {ml:.3f} vs {bl:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
