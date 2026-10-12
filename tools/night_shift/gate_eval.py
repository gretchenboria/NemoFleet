"""Measure the autonomy gate through a running tuned-adapter server (tools/ego_mix/serve.py).

  python3 tools/night_shift/gate_eval.py http://HOST:8000/v1 TOKEN data/night_shift/decide_v1 data/ego_runs/decide-1

Posts every val and test event and saves served_<split>.json: agreement with Ultra and the server's
actions_probability per event. tools/night_shift/publish.py turns these into the gate levels.
"""
import json
import os
import sys
import urllib.request

base, token, data, out = sys.argv[1:5]
types = lambda t: "+".join(sorted({a["type"] for a in json.loads(t[:t.rindex("}") + 1])["actions"]}))
for split in ("val", "test"):
    rows = []
    for n, line in enumerate(open(os.path.join(data, f"{split}.jsonl"))):
        d = json.loads(line)
        req = urllib.request.Request(base + "/chat/completions", data=json.dumps({"messages": d["messages"][:2], "max_tokens": 220}).encode(),
                                     headers={"content-type": "application/json", "authorization": f"Bearer {token}"})
        r = json.load(urllib.request.urlopen(req, timeout=120))
        text = r["choices"][0]["message"]["content"]
        try:
            got = types(text)
        except (ValueError, KeyError, TypeError):
            got = None
        rows.append({"id": d["meta"]["id"], "kind": d["meta"]["kind"], "person": d["meta"]["person"], "valid": got is not None,
                     "agree": got == types(d["messages"][2]["content"]), "got": got, "p": r["actions_probability"], "latency_ms": r["latency_ms"]})
        if n % 50 == 49:
            print(split, n + 1, "done", flush=True)
    json.dump({"rows": rows}, open(os.path.join(out, f"served_{split}.json"), "w"))
    print(split, "agree", sum(x["agree"] for x in rows), "of", len(rows), flush=True)
