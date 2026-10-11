#!/usr/bin/env bash
set -e

# ==============================================================================
# Nebius Unified Deploy Script
#
# Credentials:
# - Fine-tuning / Checkpoints: Reads NEBIUS_API_KEY from .env
# - Compute / SkyPilot VM:     Uses credentials from ~/.nebius (auto-refreshed)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse arguments
TARGET_CKPT=""
SKIP_DOWNLOAD=false

if [ "$1" == "--list" ] || [ "$1" == "-l" ]; then
    echo "🔍 Querying Token Factory jobs and checkpoints..."
    uv run python fetch_checkpoint.py --list
    exit 0
fi

if [ "$1" == "--pull" ] || [ "$1" == "--sync" ]; then
    ./sync_results.sh
    exit 0
fi

if [ "$1" == "--skip-download" ]; then
    SKIP_DOWNLOAD=true
elif [ -n "$1" ]; then
    TARGET_CKPT="$1"
fi

echo "================================================================================"
echo "🚀 Nebius Fine-Tuned Model Deployment Pipeline"
echo "================================================================================"

# ------------------------------------------------------------------------------
# STEP 1: Verify & Refresh Nebius Compute Authentication
# ------------------------------------------------------------------------------
echo "🔑 [1/5] Checking Nebius Compute Authentication..."
mkdir -p "$HOME/.nebius"

# Load AI Cloud API key from .env if present
if [ -f .env ]; then
    AI_KEY=$(grep -E "^NEBIUS_API_KEY_AI_CLOUD=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -n "$AI_KEY" ]; then
        export NEBIUS_API_KEY="$AI_KEY"
    fi
fi

# Test getting fresh IAM token
FRESH_TOKEN=$(nebius iam get-access-token 2>/dev/null || true)

if [ -z "$FRESH_TOKEN" ] && [ -n "$NEBIUS_API_KEY" ]; then
    FRESH_TOKEN="$NEBIUS_API_KEY"
fi

if [ -z "$FRESH_TOKEN" ]; then
    echo "⚠️ Nebius session expired or unauthenticated. Launching interactive login..."
    nebius auth login
    FRESH_TOKEN=$(nebius iam get-access-token)
fi

# Write fresh IAM token for SkyPilot
echo "$FRESH_TOKEN" > "$HOME/.nebius/NEBIUS_IAM_TOKEN.txt"

# Ensure Tenant ID is present
if [ ! -s "$HOME/.nebius/NEBIUS_TENANT_ID.txt" ]; then
    echo "📋 Setting up Nebius Tenant ID..."
    TENANT_ID=$(nebius --format json iam whoami 2>/dev/null | jq -r '.user_profile.tenants[0].tenant_id // empty' || true)
    if [ -n "$TENANT_ID" ]; then
        echo "$TENANT_ID" > "$HOME/.nebius/NEBIUS_TENANT_ID.txt"
    fi
fi

echo "✅ Nebius Compute credentials verified and refreshed."

# ------------------------------------------------------------------------------
# STEP 2: Download Checkpoint (Token Factory API)
# ------------------------------------------------------------------------------
if [ "$SKIP_DOWNLOAD" = false ]; then
    if [ -n "$TARGET_CKPT" ]; then
        echo ""
        echo "📥 [2/5] Fetching specific checkpoint: $TARGET_CKPT (using .env Token Factory key)..."
        uv run python fetch_checkpoint.py --checkpoint "$TARGET_CKPT"
    else
        echo ""
        echo "📥 [2/5] Fetching LATEST fine-tuning checkpoint (using .env Token Factory key)..."
        uv run python fetch_checkpoint.py
    fi
else
    echo ""
    echo "⏭️ [2/5] Skipping checkpoint download..."
fi

# ------------------------------------------------------------------------------
# STEP 3: Check Environment & HF_TOKEN
# ------------------------------------------------------------------------------
RESOLVED_HF=""
if [ -n "$HF_TOKEN" ]; then
    RESOLVED_HF="$HF_TOKEN"
elif [ -n "$HUGGING_FACE_HUB_TOKEN" ]; then
    RESOLVED_HF="$HUGGING_FACE_HUB_TOKEN"
elif [ -f "$HOME/.cache/huggingface/token" ]; then
    RESOLVED_HF=$(cat "$HOME/.cache/huggingface/token" | tr -d '\r\n')
elif [ -f .env ] && grep -q "HF_TOKEN" .env; then
    RESOLVED_HF=$(grep -E "^HF_TOKEN=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
fi

HF_ENV_FLAG=""
if [ -n "$RESOLVED_HF" ]; then
    echo "🤗 Hugging Face token detected (${#RESOLVED_HF} chars) -> Forwarding to VM."
    HF_ENV_FLAG="--env HF_TOKEN=$RESOLVED_HF --env HUGGING_FACE_HUB_TOKEN=$RESOLVED_HF"
else
    echo "⚠️ No Hugging Face token found. Model downloads from HF may be throttled."
fi

# ------------------------------------------------------------------------------
# STEP 4: Launch VM with SkyPilot
# ------------------------------------------------------------------------------
echo ""
echo "☁️ [3/5] Provisioning Nebius H100 GPU VM with SkyPilot..."
sky launch -c brodel-eval sky-nebius-eval.yaml --yes $HF_ENV_FLAG

# ------------------------------------------------------------------------------
# STEP 5: Configure Autostop
# ------------------------------------------------------------------------------
echo ""
echo "⏰ [4/5] Configuring auto-shutdown (20 min idle timeout)..."
sky autostop brodel-eval -i 20 --down

# ------------------------------------------------------------------------------
# STEP 6: Automatically Sync Results Back to Local Machine
# ------------------------------------------------------------------------------
echo ""
echo "📥 [5/5] Pulling evaluation results back to local machine..."
./sync_results.sh || echo "⚠️ Note: Could not auto-sync results yet (no results generated)."

echo ""
echo "================================================================================"
echo "✅ Nebius VM 'brodel-eval' is ready and evaluation results synced locally!"
echo "================================================================================"
echo ""
echo "📁 Local Results Stored in: ./eval_results/"
echo "   - eval_results/eval_log.jsonl"
echo "   - eval_results/latest_run.md"
echo ""
echo "👉 Interactive Testing on VM:"
echo "   sky ssh brodel-eval"
echo "   cd sky_workdir && uv run python test_model.py"
echo ""
if [ -n "$TARGET_CKPT" ]; then
echo "👉 Test the specific checkpoint:"
echo "   cd sky_workdir && uv run python test_model.py --model_dir $TARGET_CKPT"
echo ""
fi
echo "👉 Pull new results anytime:"
echo "   ./sync_results.sh"
echo ""
echo "👉 Compare against Base Model:"
echo "   cd sky_workdir && uv run python test_model.py --base_only"
echo ""
echo "👉 Tear down VM when finished:"
echo "   sky down brodel-eval --yes"
echo "================================================================================"
