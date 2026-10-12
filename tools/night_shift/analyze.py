"""How good is a tuned Nano at deciding like Ultra, and can its own probabilities gate escalation?

  python3 tools/night_shift/analyze.py data/ego_runs/decide-1 [decide_v1]

Reads decide_<tag>_<split>.json written by tools/ego_mix/train.py (TASK=decide or multi). Reports agreement with
Ultra by event kind for the untuned and tuned model, then a risk-coverage table: if Nano only settles the
events where the probability it gave its own actions is highest, how many can it settle and how often is it
wrong? The threshold is picked on val and applied to test.
"""
import glob
import json
import math
import os
import sys

KINDS = ("first", "variant", "repeat", "routine")


def load(run, tag, split):
    p = os.path.join(run, f"decide_{tag}_{split}.json")
    return json.load(open(p))["rows"] if os.path.exists(p) else None


def by_kind(rows):
    out = {}
    for k in KINDS + ("person", "all"):
        mine = [r for r in rows if k == "all" or (k == "person" and r["person"]) or r["kind"] == k]
        out[k] = (sum(r["agree"] for r in mine), len(mine))
    return out


def fmt(p):
    return f"{p[0]}/{p[1]} {100 * p[0] / max(p[1], 1):.0f}%"


def main(run, name="decide_v1"):
    tags = sorted({os.path.basename(p)[7:-10] for p in glob.glob(os.path.join(run, "decide_*_test.json"))})
    for split in ("val", "test"):
        print(f"\nagreement with Ultra, {split}")
        for tag in tags:
            rows = load(run, tag, split)
            if rows:
                b = by_kind(rows)
                print(f"  {tag:14s} " + "  ".join(f"{k} {fmt(b[k])}" for k in b) + f"  valid {sum(r['valid'] for r in rows)}/{len(rows)}")
    for tag in tags:
        val, test = load(run, tag, "val"), load(run, tag, "test")
        if not val or not test:
            continue
        print(f"\nrisk and coverage for {tag}: settle only when the model's probability of its own actions is at least p (p chosen on val)")
        for target in (0.02, 0.05, 0.10):  # tolerated share of settled decisions that differ from Ultra
            best = None
            for thr in sorted({r["actions_logp"] for r in val}):
                kept = [r for r in val if r["actions_logp"] >= thr]
                if kept and 1 - sum(r["agree"] for r in kept) / len(kept) <= target:
                    best = thr
                    break
            if best is None:
                print(f"  target {100 * target:.0f}% wrong: not reachable on val")
                continue
            kept = [r for r in test if r["actions_logp"] >= best]
            wrong = 1 - sum(r["agree"] for r in kept) / max(len(kept), 1)
            people = [r for r in kept if r["person"]]
            print(f"  target {100 * target:.0f}% wrong: p >= {math.exp(best):.2f} | test: settles {len(kept)}/{len(test)} = {100 * len(kept) / len(test):.0f}%, "
                  f"wrong {100 * wrong:.1f}% | of those, {len(people)} involve a person")
        stated = [r for r in test if isinstance(r.get("stated_confidence"), (int, float))]
        hi = [r for r in stated if r["stated_confidence"] >= 0.62]
        if hi:
            print(f"  for comparison, its stated confidence >= 0.62 settles {len(hi)}/{len(test)} with {100 * (1 - sum(r['agree'] for r in hi) / len(hi)):.1f}% wrong")


if __name__ == "__main__":
    main(*sys.argv[1:3])
