#!/usr/bin/env bash
# Night Shift "Dream" on a Nebius Serverless Job: Cosmos-Predict2.5-2B (image2world) turns NemoFleet camera
# frames into short possible futures. Outputs (mp4 + log) go to the private HF dataset $DREAM_REPO.
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
import json, os, urllib.request
site = os.environ.get("SITE", "https://nemofleet.pages.dev")
style = "Low-mounted forward robot camera, wide-angle lens, steady slow forward motion, realistic industrial lighting, physically accurate liquid behaviour, photorealistic."
S = [  # (name, scene, frame, what happens next)
  ("wh-spill-spreads", "warehouse", "cam-r14-spill", "In a fulfillment warehouse aisle with tall pallet racks, a puddle of clear liquid on polished concrete slowly spreads toward the robot; reflections of ceiling lights ripple across it."),
  ("wh-worker-cone", "warehouse", "cam-r14-spill", "In a fulfillment warehouse aisle, a worker in a yellow high-visibility vest walks in from the right and sets a yellow wet-floor sign next to the puddle on the concrete floor."),
  ("wh-forklift-through", "warehouse", "cam-r12-forklift", "An orange forklift with a driver drives forward through a puddle on the concrete warehouse floor; the tires spray small splashes of water."),
  ("dc-leak-spreads", "datacenter", "cam-r14-leak", "In a data center cold aisle between server racks, coolant leaking onto the raised floor tiles slowly spreads into a wider pool toward the robot."),
  ("dc-tech-pads", "datacenter", "cam-r14-leak", "In a data center cold aisle, a technician in dark clothing kneels by the coolant leak on the floor tiles and lays white absorbent pads over the liquid."),
  ("dc-cart-through", "datacenter", "cam-r12-cart", "In a data center aisle, a metal equipment cart is pushed forward across floor tiles wet with coolant; the wheels leave streaks through the liquid."),
]
for name, scene, frame, what in S:
    img = f"/work/in/{name}.jpg"
    urllib.request.urlretrieve(f"{site}/assets/scenes/{scene}/frames/{frame}.jpg", img)
    json.dump({"inference_type": "image2world", "name": name, "prompt": f"{what} {style}", "input_path": img}, open(f"/work/in/{name}.json", "w"))
    print("input", name)
PY

echo "== generate $(date -u)"
python examples/inference.py -i /work/in/*.json -o /work/out --model=2B/post-trained --inference-type=image2world
echo "== done $(date -u)"; ls -la /work/out
