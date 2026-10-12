"""Serve a tuned Nemotron 3 Nano adapter behind a minimal OpenAI-compatible endpoint.

  ADAPTER_DIR=/path/to/adapter SERVE_TOKEN=... PORT=8000 python tools/ego_mix/serve.py

POST /v1/chat/completions {"messages": [...]} with "Authorization: Bearer <SERVE_TOKEN>" returns the usual
choices[0].message.content plus "actions_probability": the probability the model gave to the actions it wrote
(everything before "confidence"). The console's autonomy gate uses that number instead of the confidence the
model states. One request at a time; this is for one site's reflex tier, not a public service.
"""
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from peft import PeftModel

import train

TOKEN, PORT, ADAPTER = os.environ.get("SERVE_TOKEN", ""), int(os.environ.get("PORT", "8000")), os.environ.get("ADAPTER_DIR", "")
tok, model = train.load_model()
if ADAPTER:
    model = PeftModel.from_pretrained(model, ADAPTER)
model.eval()
LOCK = threading.Lock()


@torch.no_grad()
def decide(messages, max_new_tokens=220):
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = torch.tensor([tok(text, add_special_tokens=False).input_ids], device=train.DEV)
    with torch.autocast(train.DEV, dtype=torch.bfloat16, enabled=train.DEV == "cuda"):
        gen = model.generate(input_ids=ids, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tok.pad_token_id or 0,
                             output_scores=True, return_dict_in_generate=True)
    new, logp = gen.sequences[0, ids.shape[1]:], 0.0
    for k, (tok_id, step) in enumerate(zip(new.tolist(), gen.scores)):
        if '"confidence"' in tok.decode(new[:k + 1], skip_special_tokens=True):
            break
        logp += torch.log_softmax(step[0].float(), -1)[tok_id].item()
    return tok.decode(new, skip_special_tokens=True).strip(), math.exp(logp), ids.shape[1], len(new)


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply(200, {"status": "ok", "model": train.MODEL, "adapter": os.path.basename(ADAPTER.rstrip("/")) or None})

    def do_POST(self):
        if TOKEN and self.headers.get("authorization") != f"Bearer {TOKEN}":
            return self.reply(401, {"error": "unauthorized"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
            t0 = time.time()
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
    print(f"serving on :{PORT} adapter={ADAPTER or 'none'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
