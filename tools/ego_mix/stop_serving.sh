#!/usr/bin/env bash
# Take the tuned adapter out of service cleanly: hold it in every scene, delete the serving machine, clear the
# endpoint from config/models.yaml and redeploy, so the console never claims an adapter is serving when it is not.
#   bash tools/ego_mix/stop_serving.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$HOME/.local/bin:$PATH"
for scene in datacenter warehouse sanfrancisco; do
  curl -s -m 30 -X POST -H 'content-type: application/json' -d "{\"scene\":\"$scene\",\"type\":\"hold_adapter\"}" https://nemofleet.pages.dev/api/actions >/dev/null || true
done
sky down -y nemo-serve || true
sed -i '' '/reflex_tuned:/,/api_key_env/ s|^    base_url:.*|    base_url:|' config/models.yaml
export CLOUDFLARE_API_TOKEN=$(grep '^CLOUDFLARE_API_TOKEN=' .env | cut -d= -f2-) CLOUDFLARE_ACCOUNT_ID=$(grep '^CLOUDFLARE_ACCOUNT_ID=' .env | cut -d= -f2-)
node site/build.cjs >/dev/null && npx wrangler pages deploy --project-name nemofleet --branch main | tail -1
