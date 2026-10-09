#!/usr/bin/env bash
# Robotaxi camera frames for the experimental San Francisco scene: Cosmos-Predict2.5-2B (distilled, text2world)
# renders dashcam clips; one frame of each becomes a scene camera frame (frames are synthetic, labeled as such). Outputs (mp4 + log) go to the private HF dataset $DREAM_REPO.
#   nebius ai job create ... --image nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 \
#     --inject-file tools/cosmos_dream/dream.sh:/job/dream.sh --container-command bash --args /job/dream.sh \
#     --env HF_TOKEN=... --env DREAM_REPO=<user>/nemofleet-dreams
# Needs the NVIDIA Open Model License accepted on HF for nvidia/Cosmos-Predict2.5-2B and nvidia/Cosmos-Guardrail1.
set -euo pipefail
: "${HF_TOKEN:?}" "${DREAM_REPO:?}"
SITE=${SITE:-https://nemofleet.pages.dev}
LOG=/work/out/dream.log; mkdir -p /work/in /work/out; exec > >(tee -a "$LOG") 2>&1
upload() {  # always publish what we have, including the log on failure
  local PY=/work/cp/.venv/bin/python
  if ! [ -x "$PY" ] || ! "$PY" -c 'import huggingface_hub' 2>/dev/null; then
    PY=python3; command -v python3 >/dev/null || { apt-get update -qq && apt-get install -y -qq python3 python3-pip >/dev/null; }
    python3 -c 'import huggingface_hub' 2>/dev/null || python3 -m pip install -q --break-system-packages huggingface_hub
  fi
  "$PY" - <<'PY'
import os; from huggingface_hub import HfApi
a = HfApi(token=os.environ["HF_TOKEN"]); r = os.environ["DREAM_REPO"]
a.create_repo(r, repo_type="dataset", private=True, exist_ok=True)
a.upload_folder(repo_id=r, repo_type="dataset", folder_path="/work/out", path_in_repo=os.environ.get("RUN_ID", "run"))
print("uploaded to", r)
PY
}
trap 'echo "EXIT $?"; upload || true' EXIT

echo "== setup $(date -u)"; nvidia-smi --query-gpu=name,memory.total --format=csv
apt-get update -qq && apt-get install -y -qq --no-install-recommends git git-lfs curl ca-certificates ffmpeg libx11-dev python3 python3-pip >/dev/null
git lfs install
curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"
git clone --depth 1 https://github.com/nvidia-cosmos/cosmos-predict2.5.git /work/cp
cd /work/cp && git lfs pull
# the repo pins 3.13, but the cu128 flash-attn wheels are cp310 only
uv python install 3.10 && uv python pin 3.10 && uv sync --python 3.10 --extra=cu128
source .venv/bin/activate && uv pip install -q huggingface_hub

echo "== inputs $(date -u)"
python - <<'PY'
import json
style = "Forward-facing dashcam of an autonomous robotaxi, wide-angle lens, eye level, realistic daylight, photorealistic, physically accurate, sharp."
S = {
  "cam-av07-clear": "Driving slowly down a wide downtown San Francisco street between tall glass office towers on a clear morning; light traffic, crisp white lane markings, a green traffic light ahead.",
  "cam-av14-truck": "On a one-way downtown San Francisco street between office towers, a white box delivery truck is double-parked with hazard lights flashing, blocking the right lane ahead; two orange traffic cones beside it.",
  "cam-av03-person": "Stopped at a busy downtown San Francisco intersection; a pedestrian in a dark jacket steps off the curb into the zebra crosswalk directly in front of the car; office towers behind.",
  "cam-av12-firetruck": "On a downtown San Francisco street between office towers, a red fire engine with flashing lights is stopped in the lane ahead beside a double-parked white delivery truck; a cyclist passes in the bike lane.",
}
for name, what in S.items():
    json.dump({"inference_type": "text2world", "name": name, "prompt": f"{what} {style}"}, open(f"/work/in/{name}.json", "w"))
    print("input", name)
PY

echo "== generate $(date -u)"
python examples/inference.py -i /work/in/*.json -o /work/out --model=2B/distilled --inference-type=text2world
echo "== done $(date -u)"; ls -la /work/out
