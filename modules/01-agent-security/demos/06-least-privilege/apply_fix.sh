#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib.sh"

PROJECT_ID="${GCP_PROJECT:-${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}}"
REGION="${REGION:-us-central1}"
CUSTOM_SA="helpdesk-agent@$PROJECT_ID.iam.gserviceaccount.com"

echo ""
echo "============================================================"
echo "  DEMO 6 — LEAST PRIVILEGE: Applying Fix"
echo "============================================================"
echo ""
echo "  What this does:"
echo "    1. Switches Cloud Run from default compute SA to a custom SA"
echo "    2. Custom SA has ONLY: datastore.user, logging.logWriter, aiplatform.user"
echo "    3. Storage + Secret Manager access will be DENIED (403)"
echo ""

echo "  Updating Cloud Run service account..."
echo ""

gcloud run services update helpdesk-agent \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --service-account="$CUSTOM_SA" \
    --quiet

echo ""
echo "  ─────────────────────────────────────────────────────────"
echo ""
echo "  FIX APPLIED"
echo ""
echo "  What changed:"
echo "    Cloud Run SA: default compute → helpdesk-agent (custom)"
echo "    Removed:  roles/editor (broad permissions)"
echo "    Granted:  roles/datastore.user, roles/logging.logWriter,"
echo "              roles/aiplatform.user"
echo ""

wait_for_agent 60 2 || echo "  [WARN] Timed out — check the Cloud Run console."

echo ""
echo "  Next: Refresh the Chat UI and re-run the attack to confirm it's blocked."
echo ""
echo "  ─────────────────────────────────────────────────────────"
echo ""
