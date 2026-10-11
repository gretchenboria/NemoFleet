#!/usr/bin/env bash
set -e

# ==============================================================================
# Reverse Sync: Pull Evaluation Results & Artifacts from Nebius VM to Local
# ==============================================================================

CLUSTER_NAME="${1:-brodel-eval}"
LOCAL_DIR="./eval_results"

mkdir -p "$LOCAL_DIR"

echo "🔄 Syncing evaluation results from Nebius VM ($CLUSTER_NAME) -> $LOCAL_DIR/ ..."

# Check cluster status
if ! sky status | grep -q "$CLUSTER_NAME"; then
    echo "❌ Cluster '$CLUSTER_NAME' is not active or reachable in 'sky status'."
    exit 1
fi

# Pull eval_results via rsync or tar over SSH
if rsync -avz -e "ssh -o StrictHostKeyChecking=no" "$CLUSTER_NAME":sky_workdir/eval_results/ "$LOCAL_DIR/" 2>/dev/null; then
    echo "✅ Evaluation results successfully synced via rsync to $LOCAL_DIR/"
else
    echo "📦 Falling back to streaming tar over SSH..."
    ssh -o StrictHostKeyChecking=no "$CLUSTER_NAME" "cd sky_workdir && if [ -d eval_results ]; then tar -czf - -C eval_results .; else tar -czf - -T /dev/null; fi" | tar -xzf - -C "$LOCAL_DIR"
    echo "✅ Evaluation results successfully synced to $LOCAL_DIR/"
fi
echo ""
if [ -f "$LOCAL_DIR/eval_log.jsonl" ]; then
    ENTRY_COUNT=$(wc -l < "$LOCAL_DIR/eval_log.jsonl" | tr -d ' ')
    echo "📊 Total logged evaluations: $ENTRY_COUNT"
fi

if [ -f "$LOCAL_DIR/latest_run.md" ]; then
    echo ""
    echo "📋 Latest run report preview:"
    tail -n 20 "$LOCAL_DIR/latest_run.md"
fi
