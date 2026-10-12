#!/usr/bin/env bash
# LoRA fine-tune of Nemotron 3 Nano on the ego_mix sets (see docs/FINETUNE_PLAN.md). Two ways to run it:
# 1. SkyPilot (preferred: spot H200, cluster deleted when the job ends):
#   HF_TOKEN=... sky launch -y -c ego-smoke --down -i 3 --secret HF_TOKEN --env MODE=smoke --env RUN_ID=smoke-1 tools/ego_mix/sky_train.yaml
# 2. Nebius Serverless Job:
#   nebius ai job create --name ego-smoke --parent-id <project> --platform gpu-rtx6000 --preset 1gpu-24vcpu-218gb \
#     --image nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 --disk-size 200Gi --timeout 1h \
#     --inject-file tools/ego_mix/job_train.sh:/job/job_train.sh --inject-file tools/ego_mix/train.py:/job/train.py \
#     --container-command bash --args /job/job_train.sh \
#     --env HF_TOKEN=... --env DATA_REPO=<user>/nemofleet-ego-mix --env OUT_REPO=<user>/nemofleet-ego-lora \
#     --env RUN_ID=smoke-1 --env MODE=smoke --env MAX_MINUTES=40
# MODE=full with RUNS=ego_mix is the main run; RUNS=ego_mix_no_waymo,ego_mix_thirds is the comparison job.
# The data and anything trained on it include Waymo Open Dataset material (non-commercial licence, waymo.com/open):
# both HF repos are private and must stay private.
set -euo pipefail
: "${HF_TOKEN:?}" "${DATA_REPO:?}" "${OUT_REPO:?}"
export RUN_ID=${RUN_ID:-run} MODEL=${MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}
WORK=${WORK:-/work}; TRAIN_PY=${TRAIN_PY:-/job/train.py}
export WORK OUT_DIR=$WORK/out/$RUN_ID DATA_DIR=$WORK/data MODEL_DIR=$WORK/model HF_XET_HIGH_PERFORMANCE=1 PYTHONUNBUFFERED=1
mkdir -p "$OUT_DIR" "$DATA_DIR" "$MODEL_DIR"; LOG=$OUT_DIR/job.log; exec > >(tee -a "$LOG") 2>&1
START=$(date +%s)
upload() {  # always publish what we have, including the log on failure
  echo "== upload after $(( ($(date +%s) - START) / 60 )) min"
  "$WORK/venv/bin/python" - <<'PY' || echo "upload failed"
import os; from huggingface_hub import HfApi
a = HfApi(token=os.environ["HF_TOKEN"]); r = os.environ["OUT_REPO"]
a.create_repo(r, repo_type="model", private=True, exist_ok=True)
a.upload_folder(repo_id=r, repo_type="model", folder_path=os.environ["OUT_DIR"], path_in_repo=os.environ["RUN_ID"])
print("uploaded to", r)
PY
}
# The timers below must not outlive the job: a leftover `sleep` holding the log pipe keeps the job "running".
stop_timers() { for p in $(jobs -p); do pkill -P "$p" 2>/dev/null || true; kill "$p" 2>/dev/null || true; done; }
trap 'echo "EXIT $?"; upload || true; stop_timers' EXIT
# The platform's shortest timeout is 1 h, so the job also stops itself: MAX_MINUTES caps the spend.
( sleep $(( ${MAX_MINUTES:-45} * 60 )); echo "== self-timeout after ${MAX_MINUTES:-45} min" >> "$LOG"; kill -TERM $$ ) >/dev/null 2>&1 &

echo "== setup $(date -u)"; nvidia-smi --query-gpu=name,memory.total --format=csv
command -v curl >/dev/null || { apt-get update -qq && apt-get install -y -qq --no-install-recommends curl ca-certificates >/dev/null; }
export PATH="$HOME/.local/bin:$PATH"; command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv "$WORK/venv" --python 3.12 -q --allow-existing
uv pip install -q --python "$WORK/venv/bin/python" torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
uv pip install -q --python "$WORK/venv/bin/python" transformers==5.19.0 peft==0.21.2 accelerate safetensors huggingface_hub hf_xet
"$WORK/venv/bin/python" -c 'import torch, transformers, peft; print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0), "| transformers", transformers.__version__, "| peft", peft.__version__)'

echo "== data + model $(date -u)"
"$WORK/venv/bin/python" - <<'PY'
import os, time; from huggingface_hub import snapshot_download
snapshot_download(os.environ["DATA_REPO"], repo_type="dataset", local_dir=os.environ["DATA_DIR"])
t = time.time()
snapshot_download(os.environ["MODEL"], local_dir=os.environ["MODEL_DIR"], allow_patterns=["*.json", "*.safetensors", "*.jinja"])
print(f"model downloaded in {time.time() - t:.0f} s")
PY
du -sh "$MODEL_DIR" "$DATA_DIR"

( while sleep 600; do upload; done ) >/dev/null 2>&1 &  # spot machines can vanish: publish partial results every 10 min
echo "== train $(date -u) (setup took $(( ($(date +%s) - START) / 60 )) min)"
"$WORK/venv/bin/python" "$TRAIN_PY"
echo "== done $(date -u), $(( ($(date +%s) - START) / 60 )) min total"; ls -la "$OUT_DIR"
