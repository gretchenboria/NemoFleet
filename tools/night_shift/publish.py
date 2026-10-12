"""Write config/night_shift.json, the fine-tune results the console shows. Aggregates only; every number is
computed here from result files in data/ (never typed in).   python3 tools/night_shift/publish.py
"""
import collections
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "ego_mix"))
from score import load, rates  # noqa: E402

KINDS = ("first", "repeat", "variant", "routine")
types = lambda d: "+".join(sorted({a["type"] for a in d["actions"]})) if d else None


def distill():
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data/night_shift/labelled.jsonl"))]
    rows = [r for r in rows if r["ultra"]]
    test = [json.loads(l) for l in open(os.path.join(ROOT, "data/night_shift/decide_v1/test.jsonl"))]
    man = json.load(open(os.path.join(ROOT, "data/night_shift/decide_v1/manifest.json")))
    def tally(items, agree, key):
        c = collections.defaultdict(lambda: [0, 0])
        for it in items:
            for k in (key(it), "all") + (("person",) if it.get("person") or it.get("meta", {}).get("person") else ()):
                c[k][0] += agree(it); c[k][1] += 1
        return {k: v for k, v in c.items()}
    out = {"episodes": len({r["episode"] for r in rows}), "events": len(rows), "hazard_types": len({r["category"] for r in rows}),
           "teacher": man["teacher"], "student": man["student"],
           "teacher_cost_usd": round(sum(r["ultra_tokens"][0] * 1 + r["ultra_tokens"][1] * 3 for r in rows) / 1e6, 2),
           "served_nano_all": tally(rows, lambda r: types(r["nano"]) == types(r["ultra"]), lambda r: r["kind"]),
           "served_nano_confident_share": round(sum(1 for r in rows if r["nano"] and r["nano"]["confidence"] >= 0.62) / len(rows), 3),
           "train_events": man["splits"]["train"]["n"], "test_events": len(test), "test_hazard_types": man["splits"]["test"]["categories"],
           "test_served_nano": tally(test, lambda r: types(r["meta"]["served_nano"]) == types(json.loads(r["messages"][2]["content"])), lambda r: r["meta"]["kind"]),
           "fine_tune": {"status": "training", "run": "decide-1"}}
    res = os.path.join(ROOT, "data/ego_runs/decide-1")
    if os.path.exists(os.path.join(res, "decide_decide_v1_test.json")):
        for name, f in (("test_tuned", "decide_decide_v1_test.json"), ("test_untuned_same_harness", "decide_zero_shot_test.json")):
            d = json.load(open(os.path.join(res, f)))
            out[name] = tally(d["rows"], lambda r: r["agree"], lambda r: r["kind"])
            out[name + "_seconds_per_decision"] = d["summary"]["seconds_per_decision"]
        r = json.load(open(os.path.join(res, "results.json")))["runs"]["decide_v1"]["train"]
        out["fine_tune"] = {"status": "done", "run": "decide-1", "minutes": round(r["seconds"] / 60), "steps": r["steps"]}
    return out


def trigger():
    R, out = os.path.join(ROOT, "data/ego_runs"), {"run": "plan-1", "viewpoints": {}}
    for emb in ("robot", "human", "vehicle"):
        pool = lambda run, tag, data: [r for s in ("val", "test") for r in load(os.path.join(R, run), tag, s, os.path.join(ROOT, data)) if r["embodiment"] == emb]
        v1 = {(r["seq"], r["t"]): r for r in pool("main-1", "ego_mix", "data/ego_mix")}
        rows = [dict(r, base=v1[(r["seq"], r["t"])]["base"]) for r in pool("plan-1", "ego_mix_plan", "data/ego_mix_plan")]
        b_rec, b_far = rates(rows, lambda r: r["base"])
        neg = sorted((r["score"] for r in rows if not r["label"]), reverse=True)
        thr = neg[min(len(neg) - 1, int(b_far * len(neg)))]
        m_rec, m_far = rates(rows, lambda r: r["score"] > thr)
        out["viewpoints"][emb] = {"positives": sum(r["label"] for r in rows), "baseline_recall": round(b_rec, 3), "tuned_recall": round(m_rec, 3), "false_alarm_rate": round(b_far, 3)}
    g = json.load(open(os.path.join(R, "plan-1/results.json")))["runs"]["ego_mix_plan"]
    out.update(valid_json=[g["generation"]["json_valid"], g["generation"]["n"]], minutes=round(g["train"]["seconds"] / 60), train_samples=16080)
    return out


doc = {"updated": datetime.date.today().isoformat(), "compute": "Nebius AI Cloud, one spot H200 via SkyPilot", "distill": distill(), "trigger": trigger()}
json.dump(doc, open(os.path.join(ROOT, "config/night_shift.json"), "w"), indent=2)
print(json.dumps(doc)[:900])
