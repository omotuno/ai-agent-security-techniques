#!/usr/bin/env bash
# Shared helpers for demo apply_fix.sh scripts.
# Usage: source "$(dirname "$0")/../lib.sh"

# Resolve the module root (two levels above any demo script).
MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Load .env so apply_fix scripts work standalone after deploy ──
if [ -f "$MODULE_DIR/.env" ]; then
    set -a
    source "$MODULE_DIR/.env"
    set +a
fi


# wait_for_agent [max_attempts] [interval]
#   Polls the agent health endpoint until it responds or times out.
wait_for_agent() {
    if [ -z "${AGENT_URL:-}" ]; then
        echo "  [ERROR] AGENT_URL is not set. Set it to your Cloud Run service URL."
        exit 1
    fi
    local url="${AGENT_URL}/health"
    local max="${1:-30}"
    local interval="${2:-1}"

    echo "  Waiting for agent to be ready..."
    for i in $(seq 1 "$max"); do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo "  Agent is ready!"
            return 0
        fi
        if [ "$i" -eq "$max" ]; then
            echo "  [!] Timeout waiting for agent."
            return 1
        fi
        sleep "$interval"
    done
}

# restart_agent <security_level>
#   Updates SECURITY_LEVEL on Cloud Run via gcloud.
restart_agent() {
    local level="$1"
    local project="${GCP_PROJECT:-${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}}"
    local region="${REGION:-us-central1}"

    echo "  Updating SECURITY_LEVEL=${level} via gcloud..."
    echo ""

    gcloud run services update helpdesk-agent \
        --region="$region" \
        --project="$project" \
        --update-env-vars="SECURITY_LEVEL=$level" \
        --quiet

    echo ""
    wait_for_agent 60 2 || exit 1
}
