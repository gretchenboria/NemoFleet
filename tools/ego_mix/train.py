"""LoRA fine-tune and scoring of Nemotron 3 Nano on the ego_mix sets. Runs inside job_train.sh.

Environment:
  MODE       smoke | full          smoke: tiny eval subset, SMOKE_STEPS (50) steps, 3 generations, then stop
  RUNS       comma list of dataset folders under DATA_DIR to train on, e.g. "ego_mix" or
             "ego_mix_no_waymo,ego_mix_thirds". Val and test come from DATA_DIR/EVAL_SET (default ego_mix).
  ZERO_SHOT  1 to score the untuned model first
  EPOCHS, BATCH, LR, GPU_RATE ($/h, for the cost projection), MAX_RUN_USD (stop rule), GRAD_CKPT
  TINY       1 = random miniature model on CPU, to test this script without a GPU

Scoring is one forward pass per sample: the gap between the logits of `true` and `false` right after
`{"in_way":`. That gives a ranking, so recall can be read at any false-alarm rate (tools/ego_mix/score.py).
"""
import json
import math
import os
import random
import sys
import time

import torch
from peft import LoraConfig, get_peft_model, set_peft_model_state_dict
from safetensors.torch import load_file
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

MODEL = os.environ.get("MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16")
MODEL_DIR = os.environ.get("MODEL_DIR", MODEL)
DATA = os.environ.get("DATA_DIR", "data")
OUT = os.environ.get("OUT_DIR", "out")
MODE = os.environ.get("MODE", "smoke")
TINY = os.environ.get("TINY") == "1"
EPOCHS, BATCH, LR = int(os.environ.get("EPOCHS", "2")), int(os.environ.get("BATCH", "8")), float(os.environ.get("LR", "1e-4"))
GPU_RATE, MAX_RUN_USD = float(os.environ.get("GPU_RATE", "1.80")), float(os.environ.get("MAX_RUN_USD", "8"))
SMOKE_STEPS = int(os.environ.get("SMOKE_STEPS", "50"))
MAX_STEPS = int(os.environ.get("MAX_STEPS", "0")) or None    # hard cap on training steps in full mode
EVAL_CAP = int(os.environ.get("EVAL_CAP", "0")) or None      # samples per embodiment in each eval set
DEV = "cuda" if torch.cuda.is_available() else "cpu"

# Every nn.Linear that can be adapted, by name: Mamba mixers (in_proj), attention (q/k/v/o_proj) and the
# shared expert MLP of each MoE layer (up/down_proj). PEFT rejects the Mamba out_proj and conv1d, because
# the fast Mamba path reads their weights directly and would bypass the adapter. The 128 routed experts are raw 3-D parameters, which
# LoRA cannot wrap, and the router ("gate") is left alone on purpose.
TARGETS = ["in_proj", "q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj"]
ANSWER_HEAD = '{"in_way":'


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_rows(folder, split):
    return [json.loads(line) for line in open(os.path.join(DATA, folder, f"{split}.jsonl"))]


def is_pos(r):
    return '"in_way":true' in r["messages"][-1]["content"]


def eval_subset(rows, vehicle_negatives, per_emb=None, seed=7):
    """All human and robot rows; vehicle: every positive plus a seeded sample of negatives. Recall is
    measured on positives and false alarms on negatives, so thinning negatives does not bias either."""
    rng = random.Random(seed)
    veh_neg = [r for r in rows if r["meta"]["embodiment"] == "vehicle" and not is_pos(r)]
    keep = [r for r in rows if r["meta"]["embodiment"] != "vehicle" or is_pos(r)]
    keep += rng.sample(veh_neg, min(len(veh_neg), vehicle_negatives))
    if per_emb:
        out = []
        for e in ("human", "robot", "vehicle"):
            mine = [r for r in keep if r["meta"]["embodiment"] == e]
            pos, neg = [r for r in mine if is_pos(r)], [r for r in mine if not is_pos(r)]
            out += rng.sample(pos, min(len(pos), per_emb // 2)) + rng.sample(neg, min(len(neg), per_emb // 2))
        keep = out
    return keep


class Codec:
    """Turns a chat sample into token ids the same way for training, scoring and generation."""

    def __init__(self, tok, sample):
        self.tok = tok
        msgs = sample["messages"]
        full = tok.apply_chat_template(msgs, tokenize=False, enable_thinking=False)
        tail = full.rsplit(msgs[-1]["content"], 1)[-1].strip()  # what the template writes after an answer
        self.end = tok(tail, add_special_tokens=False).input_ids if tail else [tok.eos_token_id]
        t = tok(ANSWER_HEAD + "true", add_special_tokens=False).input_ids
        f = tok(ANSWER_HEAD + "false", add_special_tokens=False).input_ids
        k = next(i for i, (a, b) in enumerate(zip(t, f)) if a != b)
        assert k > 0, "true/false must differ after a shared answer head"
        self.head, self.true_id, self.false_id = t[:k], t[k], f[k]
        log("template prefix ends with:", repr(self.prefix_text(sample)[-80:]))
        log("answer end tokens:", repr(tail), self.end, "| head", self.head, "true", self.true_id, "false", self.false_id)

    def prefix_text(self, r):
        return self.tok.apply_chat_template(r["messages"][:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False)

    def prefix(self, r):
        return self.tok(self.prefix_text(r), add_special_tokens=False).input_ids

    def train_pair(self, r):
        p = self.prefix(r)
        a = self.tok(r["messages"][-1]["content"], add_special_tokens=False).input_ids + self.end
        return p + a, [-100] * len(p) + a


def load_model():
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    t0 = time.time()
    if TINY:
        cfg = AutoConfig.from_pretrained(MODEL_DIR)
        for k, v in dict(hidden_size=64, intermediate_size=64, moe_intermediate_size=64, moe_shared_expert_intermediate_size=128,
                         n_routed_experts=8, num_experts_per_tok=2, num_attention_heads=4, head_dim=16, num_key_value_heads=2,
                         mamba_num_heads=8, mamba_head_dim=16, ssm_state_size=16,
                         layers_block_type=["linear_attention", "moe", "linear_attention", "full_attention", "moe"]).items():
            setattr(cfg, k, v)
        model = AutoModelForCausalLM.from_config(cfg)
    else:
        model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.bfloat16, device_map={"": 0})
    log(f"model loaded in {time.time() - t0:.0f} s; {sum(p.numel() for p in model.parameters()) / 1e9:.2f}B parameters")
    return tok, model


def add_lora(model, seed):
    torch.manual_seed(seed)
    peft_model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules=TARGETS, task_type="CAUSAL_LM"))
    wrapped = [n for n, m in peft_model.named_modules() if hasattr(m, "lora_A") and n.split(".")[-1] in TARGETS]
    kinds = {t: sum(n.endswith("." + t) for n in wrapped) for t in TARGETS}
    trainable = sum(p.numel() for p in peft_model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in peft_model.parameters())
    log(f"LoRA on {len(wrapped)} layers {kinds}; trainable {trainable / 1e6:.1f}M = {100 * trainable / total:.3f}%")
    # the known trap: adapters silently landing on a fraction of the network
    assert kinds["in_proj"] and kinds["q_proj"] and kinds["up_proj"], "LoRA missed a layer type (Mamba, attention or shared expert)"
    assert not any("gate" in n or ".experts." in n for n in wrapped), "LoRA must not touch the router or routed experts"
    return peft_model


@torch.no_grad()
def score(model, codec, rows, tag):
    """One row at a time, so no padding ever passes through the Mamba state."""
    model.eval()
    out, t0 = [], time.time()
    for i, r in enumerate(rows):
        ids = torch.tensor([codec.prefix(r) + codec.head], device=DEV)
        with torch.autocast(DEV, dtype=torch.bfloat16, enabled=DEV == "cuda"):
            logits = model(input_ids=ids, logits_to_keep=1, use_cache=False).logits[0, -1].float()
        out.append({"seq": r["meta"]["seq"], "t": r["meta"]["t"], "embodiment": r["meta"]["embodiment"],
                    "label": is_pos(r), "now": '"t_s":0.0' in r["messages"][-1]["content"],
                    "score": round((logits[codec.true_id] - logits[codec.false_id]).item(), 4)})
        if i == 20:
            log(f"  scoring {tag}: {(time.time() - t0) / 21:.2f} s/sample, {len(rows)} samples")
    summary = {}
    for e in ("human", "robot", "vehicle"):
        mine = [o for o in out if o["embodiment"] == e]
        pos, neg = sorted(o["score"] for o in mine if o["label"]), sorted(o["score"] for o in mine if not o["label"])
        if not pos or not neg:
            continue
        auc = sum(sum(n < p for n in neg) + 0.5 * sum(n == p for n in neg) for p in pos) / (len(pos) * len(neg))
        thr = neg[min(len(neg) - 1, math.ceil(0.9 * len(neg)))]  # threshold that lets through at most 10% of negatives
        summary[e] = {"n": len(mine), "pos": len(pos), "auroc": round(auc, 3),
                      "recall_at_10pct_false_alarms": round(sum(p > thr for p in pos) / len(pos), 3),
                      "accuracy_at_0": round((sum(p > 0 for p in pos) + sum(n <= 0 for n in neg)) / len(mine), 3)}
    log(f"SCORES {tag}: {json.dumps(summary)}")
    os.makedirs(OUT, exist_ok=True)
    json.dump({"summary": summary, "rows": out}, open(os.path.join(OUT, f"scores_{tag}.json"), "w"))
    return summary


@torch.no_grad()
def generate_check(model, codec, rows, tag):
    """Does the tuned model still write the whole JSON answer? Not on the critical path, so failures are logged."""
    model.eval()
    valid = agree = 0
    t_err, shown = [], 0
    try:
        for r in rows:
            ids = torch.tensor([codec.prefix(r)], device=DEV)
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=DEV == "cuda"):
                gen = model.generate(input_ids=ids, max_new_tokens=40, do_sample=False, pad_token_id=codec.tok.pad_token_id or 0)
            text = codec.tok.decode(gen[0, ids.shape[1]:], skip_special_tokens=True).strip()
            truth = json.loads(r["messages"][-1]["content"])
            if shown < 3:
                log(f"  gen {tag}: {text!r} | truth {r['messages'][-1]['content']}")
                shown += 1
            try:
                got = json.loads(text[:text.index("}") + 1])
                valid += 1
                agree += got.get("in_way") == truth["in_way"]
                if truth["in_way"] and isinstance(got.get("t_s"), (int, float)):
                    t_err.append(abs(got["t_s"] - truth["t_s"]))
            except ValueError:
                pass
        res = {"n": len(rows), "json_valid": valid, "in_way_agree": agree, "t_s_mean_abs_err": round(sum(t_err) / len(t_err), 2) if t_err else None}
    except Exception as e:  # noqa: BLE001
        res = {"error": repr(e)[:300]}
    log(f"GENERATION {tag}: {json.dumps(res)}")
    return res


def batches(codec, rows, bs, seed):
    rng = random.Random(seed)
    rows = rows[:]
    rng.shuffle(rows)
    enc = [codec.train_pair(r) for r in rows]
    chunks = [sorted(enc[i:i + 50 * bs], key=lambda e: len(e[0])) for i in range(0, len(enc), 50 * bs)]  # similar lengths together
    out = [c[i:i + bs] for c in chunks for i in range(0, len(c), bs)]
    rng.shuffle(out)
    return out


def collate(batch, pad):
    n = max(len(ids) for ids, _ in batch)
    # padding goes on the right: a left-to-right model never lets it influence the real tokens before it
    ids = torch.tensor([i + [pad] * (n - len(i)) for i, _ in batch], device=DEV)
    labels = torch.tensor([l + [-100] * (n - len(l)) for _, l in batch], device=DEV)
    mask = torch.tensor([[1] * len(i) + [0] * (n - len(i)) for i, _ in batch], device=DEV)
    return ids, mask, labels


def loss_of(model, ids, mask, labels):
    with torch.autocast(DEV, dtype=torch.bfloat16, enabled=DEV == "cuda"):
        return model(input_ids=ids, attention_mask=mask, labels=labels, use_cache=False).loss


def train(model, codec, rows, val_rows, tag, max_steps=None):
    pad = codec.tok.pad_token_id or 0
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=LR, weight_decay=0.0)
    plan = [b for ep in range(EPOCHS) for b in batches(codec, rows, BATCH, seed=ep)]
    steps = min(len(plan), max_steps or len(plan))
    warm = min(50, steps // 10 + 1)
    lr_at = lambda s: (s + 1) / warm if s < warm else 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, steps - warm)))
    per_epoch = len(plan) // EPOCHS
    log(f"TRAIN {tag}: {len(rows)} samples, {steps} steps of {BATCH}, {EPOCHS} epochs, lr {LR}")
    hist, tokens, t0, best = [], 0, time.time(), (1e9, -1)
    val = [collate(b, pad) for b in batches(codec, val_rows, BATCH, seed=0)]
    for s in range(steps):
        model.train()
        ids, mask, labels = collate(plan[s], pad)
        for g in opt.param_groups:
            g["lr"] = LR * lr_at(s)
        loss = loss_of(model, ids, mask, labels)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        hist.append(loss.item())
        tokens += int(mask.sum())
        if not math.isfinite(hist[-1]):
            sys.exit(f"loss is {hist[-1]} at step {s}")
        if s % 10 == 9 or s == steps - 1:
            dt = time.time() - t0
            left = (steps - s - 1) * dt / (s + 1)
            mem = torch.cuda.max_memory_allocated() / 2**30 if DEV == "cuda" else 0
            log(f"  step {s + 1}/{steps} loss {sum(hist[-10:]) / len(hist[-10:]):.4f} | {tokens / dt:.0f} tok/s | "
                f"{dt / (s + 1):.2f} s/step | left {left / 60:.0f} min = ${left / 3600 * GPU_RATE:.2f} | peak {mem:.0f} GiB")
        if s == 299 and steps > 400:  # pilot gate, 300 steps in
            first, last = sum(hist[:20]) / 20, sum(hist[-50:]) / 50
            cost = steps * (time.time() - t0) / 300 / 3600 * GPU_RATE
            log(f"GATE {tag}: loss {first:.3f} -> {last:.3f}; projected cost of this run ${cost:.2f} (cap ${MAX_RUN_USD})")
            if not last < 0.7 * first:
                sys.exit("gate failed: loss is not falling")
            if cost > MAX_RUN_USD:
                sys.exit("gate failed: projected cost over the cap")
        if (s + 1) % per_epoch == 0 or s == steps - 1:
            model.eval()
            with torch.no_grad():
                v = sum(loss_of(model, *b).item() for b in val) / len(val)
            log(f"  VAL {tag}: epoch {(s + 1) / per_epoch:.2f} val loss {v:.4f}")
            if v < best[0]:
                best = (v, s + 1)
                model.save_pretrained(os.path.join(OUT, f"adapter_{tag}"))
    dt = time.time() - t0
    return {"steps": steps, "seconds": round(dt), "tokens_per_s": round(tokens / dt), "first_loss": round(sum(hist[:20]) / len(hist[:20]), 4),
            "last_loss": round(sum(hist[-20:]) / len(hist[-20:]), 4), "best_val_loss": round(best[0], 4), "best_step": best[1],
            "usd": round(dt / 3600 * GPU_RATE, 2)}


def main():
    os.makedirs(OUT, exist_ok=True)
    smoke = MODE == "smoke"
    log(f"mode {MODE} | device {DEV} | torch {torch.__version__} | runs {os.environ.get('RUNS', 'ego_mix')}")
    tok, base = load_model()
    if os.environ.get("GRAD_CKPT") == "1":
        base.gradient_checkpointing_enable()
    eval_set = os.environ.get("EVAL_SET", "ego_mix")  # folder holding val.jsonl and test.jsonl
    val_all, test_all = load_rows(eval_set, "val"), load_rows(eval_set, "test")
    val = eval_subset(val_all, 1500, per_emb=EVAL_CAP or (20 if smoke else None))
    test = eval_subset(test_all, 1500, per_emb=EVAL_CAP or (20 if smoke else None))
    val_loss_rows = eval_subset(val_all, 150, per_emb=16 if smoke else 100)
    codec = Codec(tok, val_all[0])
    results = {"mode": MODE, "model": MODEL, "targets": TARGETS, "runs": {}}
    if os.environ.get("ZERO_SHOT", "1") == "1":
        results["zero_shot"] = {"val": score(base, codec, val, "zero_shot_val")}
        if not smoke:
            results["zero_shot"]["test"] = score(base, codec, test, "zero_shot_test")
    for run in os.environ.get("RUNS", "ego_mix").split(","):
        rows = load_rows(run, "train")
        model = add_lora(base, seed=7)
        res = {"train": train(model, codec, rows[:BATCH * SMOKE_STEPS] if smoke else rows, val_loss_rows, run, max_steps=SMOKE_STEPS if smoke else MAX_STEPS)}
        if not smoke:  # score the checkpoint with the lowest val loss, not the last step
            set_peft_model_state_dict(model, load_file(os.path.join(OUT, f"adapter_{run}", "adapter_model.safetensors")))
        res["val"] = score(model, codec, val, f"{run}_val")
        if not smoke:
            res["test"] = score(model, codec, test, f"{run}_test")
        res["generation"] = generate_check(model, codec, val[:3] if smoke else random.Random(7).sample(val, min(300, len(val))), run)
        results["runs"][run] = res
        json.dump(results, open(os.path.join(OUT, "results.json"), "w"), indent=2)
        base = model.unload()  # back to the untouched base model for the next run
    log("RESULTS", json.dumps(results))


if __name__ == "__main__":
    main()
