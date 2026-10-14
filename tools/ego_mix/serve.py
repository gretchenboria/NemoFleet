"""Serve a tuned Nemotron 3 Nano adapter behind a minimal OpenAI-compatible endpoint.

  ADAPTER_DIR=/path/to/adapter SERVE_TOKEN=... PORT=8000 python tools/ego_mix/serve.py

POST /v1/chat/completions {"messages": [...]} with "Authorization: Bearer <SERVE_TOKEN>" returns the usual
choices[0].message.content plus "actions_probability": the probability the model gave to the action types it
chose and to how many actions it wrote (free text such as alert messages is not counted). The console's autonomy gate uses that number instead of the confidence the
model states. One request at a time; this is for one site's reflex tier, not a public service.
"""
import json
import math
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from peft import PeftModel

import cuda_x_pipeline
import train

TOKEN, PORT, ADAPTER = os.environ.get("SERVE_TOKEN", ""), int(os.environ.get("PORT", "8000")), os.environ.get("ADAPTER_DIR", "")
# ADAPTERS="decide=/path,inway=/path" serves both tuned adapters from one copy of the base model.
ADAPTERS = dict(kv.split("=", 1) for kv in os.environ.get("ADAPTERS", "").split(",") if kv) or ({"decide": ADAPTER} if ADAPTER else {})
tok, model = train.load_model()
for name, path in ADAPTERS.items():
    model = PeftModel.from_pretrained(model, path, adapter_name=name) if not isinstance(model, PeftModel) else (model.load_adapter(path, adapter_name=name), model)[1]
model.eval()
_t, _f = tok('{"in_way":true', add_special_tokens=False).input_ids, tok('{"in_way":false', add_special_tokens=False).input_ids
_k = next(i for i, (a, b) in enumerate(zip(_t, _f)) if a != b)
IN_WAY_HEAD, TRUE_ID, FALSE_ID = _t[:_k], _t[_k], _f[_k]


@torch.no_grad()
def in_way(messages):
    """Person-in-the-way score: the gap between the logits of true and false right after {"in_way": ."""
    if "inway" in ADAPTERS:
        model.set_adapter("inway")
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = torch.tensor([tok(text, add_special_tokens=False).input_ids + IN_WAY_HEAD], device=train.DEV)
    with torch.autocast(train.DEV, dtype=torch.bfloat16, enabled=train.DEV == "cuda"):
        logits = model(input_ids=ids, logits_to_keep=1, use_cache=False).logits[0, -1].float()
    return (logits[TRUE_ID] - logits[FALSE_ID]).item()


LOCK = threading.Lock()


@torch.no_grad()
def decide(messages, max_new_tokens=220):
    if "decide" in ADAPTERS:
        model.set_adapter("decide")
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = torch.tensor([tok(text, add_special_tokens=False).input_ids], device=train.DEV)
    with torch.autocast(train.DEV, dtype=torch.bfloat16, enabled=train.DEV == "cuda"):
        gen = model.generate(input_ids=ids, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tok.pad_token_id or 0,
                             output_scores=True, return_dict_in_generate=True)
    new = gen.sequences[0, ids.shape[1]:]
    # Probability of the action choices only: the tokens that spell each action "type" and the tokens that
    # continue or close the actions list. Free text (alert messages, rationale) is left out, otherwise any
    # decision that writes a message looks improbable however sure the model is about what to do.
    pieces, spans, prev = [], [], ""
    for k, (tok_id, step) in enumerate(zip(new.tolist(), gen.scores)):
        cur = tok.decode(new[:k + 1], skip_special_tokens=True)
        pieces.append((len(prev), len(cur), torch.log_softmax(step[0].float(), -1)[tok_id].item()))
        prev = cur
    head = prev.split('"confidence"')[0]
    for m in re.finditer(r'"type"\s*:\s*"([a-z_]+)"', head):
        spans.append(m.span(1))
    for m in re.finditer(r'\}\s*([,\]])', head):
        spans.append(m.span(1))
    logp = sum(lp for a, b, lp in pieces if any(a < e and b > s for s, e in spans))
    return prev.strip(), (math.exp(logp) if spans else 0.0), ids.shape[1], len(new)


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply(200, {"status": "ok", "model": train.MODEL, "adapters": sorted(ADAPTERS), "cuda_x": cuda_x_pipeline.runtime_info()})

    def do_POST(self):
        if TOKEN and self.headers.get("authorization") != f"Bearer {TOKEN}":
            return self.reply(401, {"error": "unauthorized"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
            t0 = time.time()
            if body.get("task") == "vision":  # {"task": "vision", "scene": "datacenter", "frame": "cam-r14-leak"} -> CV-CUDA + TensorRT ROI score
                with LOCK:
                    res = cuda_x_pipeline.analyze_payload(body)
                return self.reply(200, res)
            if body.get("task") == "in_way":  # {"task": "in_way", "messages": [system, user]} -> score only
                with LOCK:
                    score = in_way(body["messages"])
                return self.reply(200, {"object": "in_way", "score": round(score, 4), "probability": round(1 / (1 + math.exp(-score)), 4), "latency_ms": round(1000 * (time.time() - t0))})
            with LOCK:
                content, prob, n_in, n_out = decide(body["messages"], int(body.get("max_tokens", 220)))
            self.reply(200, {"object": "chat.completion", "model": body.get("model") or "nemotron-3-nano-tuned",
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                             "actions_probability": round(prob, 4), "latency_ms": round(1000 * (time.time() - t0)),
                             "usage": {"prompt_tokens": n_in, "completion_tokens": n_out}})
        except Exception as e:  # noqa: BLE001
            self.reply(400, {"error": repr(e)[:300]})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"serving on :{PORT} adapters={sorted(ADAPTERS) or 'none'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
