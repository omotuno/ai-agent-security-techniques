#!/usr/bin/env bash
# Deploy the helpdesk agent to GCP Cloud Run using gcloud CLI.
#
# Creates all GCP resources using gcloud/curl commands, which are natively
# idempotent and don't require state reconciliation.
#
# Prerequisites:
#   gcloud auth application-default login
#   export OPENAI_API_KEY=sk-...
#
# Optional env vars:
#   REGION              (default: us-central1)
#   FIREBASE_API_KEY    (from Firebase Console after first deploy)
#   LANGSMITH_API_KEY   (enables LangSmith tracing)
#   LLM_MODEL           (default: gpt-5.4)
#   SECURITY_LEVEL      (default: demo1_vulnerable)
#   USE_LEAST_PRIVILEGE (default: false — set true for Demo 6 fix)
set -euo pipefail

MODULE_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Cleanup trap ──────────────────────────────────────────────
BG_FIRESTORE_PID=""
cleanup() {
    if [ -n "$BG_FIRESTORE_PID" ] && kill -0 "$BG_FIRESTORE_PID" 2>/dev/null; then
        echo "  Cleaning up background process (PID $BG_FIRESTORE_PID)..."
        kill "$BG_FIRESTORE_PID" 2>/dev/null || true
        wait "$BG_FIRESTORE_PID" 2>/dev/null || true
    fi
    rm -f /tmp/helpdesk-firestore.log /tmp/helpdesk-idp-response.json
}
trap cleanup EXIT

# ── Load .env if present ───────────────────────────────────
if [ -f "$MODULE_DIR/.env" ]; then
    set -a
    source "$MODULE_DIR/.env"
    set +a
fi

# ── Auto-detect project ID from gcloud ──────────────────────────
PROJECT_ID="${GCP_PROJECT:-${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}}"
if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: No GCP project found."
    echo "  Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

# ── Check required env vars ─────────────────────────────────────
if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "ERROR: OPENAI_API_KEY is not set."
    echo "  Run: export OPENAI_API_KEY=sk-..."
    exit 1
fi

if [ -z "${FIREBASE_API_KEY:-}" ]; then
    echo ""
    echo "  WARNING: FIREBASE_API_KEY is not set."
    echo "  The Chat UI login will not work until you set it."
    echo "  To get it (one-time setup):"
    echo "    1. Go to: https://console.firebase.google.com/"
    echo "    2. Click 'Add project' → select your GCP project '$PROJECT_ID'"
    echo "    3. Go to Project Settings → General → Web app → copy 'apiKey'"
    echo "    4. Add to .env: FIREBASE_API_KEY=your-api-key-here"
    echo "    5. Re-run: bash deploy_gcloud.sh"
    echo ""
fi

# ── Configuration ────────────────────────────────────────────────
REGION="${REGION:-us-central1}"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/helpdesk/helpdesk-agent:latest"
CUSTOM_SA="helpdesk-agent@$PROJECT_ID.iam.gserviceaccount.com"
BUCKET_NAME="$PROJECT_ID-techcorp-customer-data"
USE_LEAST_PRIVILEGE="${USE_LEAST_PRIVILEGE:-false}"
SECURITY_LEVEL="${SECURITY_LEVEL:-demo1_vulnerable}"
LLM_MODEL="${LLM_MODEL:-gpt-5.4}"

echo "==> Deploying to project: $PROJECT_ID (region: $REGION)"
echo ""

# ── Helper: run a gcloud create command; succeed if already exists ─
gcloud_create() {
    local description="$1"; shift
    echo "  Creating $description..."
    if output=$("$@" 2>&1); then
        echo "    Created."
    elif echo "$output" | grep -qi "already exists\|ALREADY_EXISTS\|already own it\|duplicate\|conflict\|409"; then
        echo "    Already exists (skipping)."
    else
        echo "    ERROR: $output"
        return 1
    fi
}

# ══════════════════════════════════════════════════════════════════
# Step 1: Enable APIs
# ══════════════════════════════════════════════════════════════════
echo "==> Step 1/9: Enabling APIs..."
gcloud services enable \
    cloudresourcemanager.googleapis.com \
    run.googleapis.com \
    compute.googleapis.com \
    firestore.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    iam.googleapis.com \
    identitytoolkit.googleapis.com \
    artifactregistry.googleapis.com \
    --project="$PROJECT_ID" --quiet
echo "  APIs enabled. Waiting for propagation..."
echo "  (GCP APIs can take up to 60s to propagate after enabling.)"

# Wait for Artifact Registry API to be usable before proceeding.
for i in $(seq 1 12); do
    if gcloud artifacts repositories list \
        --location="$REGION" --project="$PROJECT_ID" \
        --format="value(name)" > /dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 12 ]; then
        echo "  WARNING: API propagation timed out — continuing anyway."
    fi
    sleep 5
done
echo "  APIs ready."

# ══════════════════════════════════════════════════════════════════
# Step 2: Artifact Registry
# ══════════════════════════════════════════════════════════════════
echo ""
echo "==> Step 2/9: Artifact Registry..."
gcloud_create "Docker repo 'helpdesk'" \
    gcloud artifacts repositories create helpdesk \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID" --quiet

# ══════════════════════════════════════════════════════════════════
# Step 3: Firestore DB + Vector Index (background)
# ══════════════════════════════════════════════════════════════════
echo ""
echo "==> Step 3/9: Starting Firestore database + vector index (background)..."
(
    set -euo pipefail

    # Create database
    echo "  Creating Firestore (default) database..."
    if db_output=$(gcloud firestore databases create \
        --database="(default)" \
        --location=nam5 \
        --type=firestore-native \
        --project="$PROJECT_ID" --quiet 2>&1); then
        echo "    Firestore database created."
    elif echo "$db_output" | grep -qi "already exists\|ALREADY_EXISTS"; then
        echo "    Firestore database already exists (skipping)."
    else
        echo "    ERROR creating Firestore: $db_output"
        exit 1
    fi

    # Vector index — check if one already exists on wiki/embedding
    EXISTING_INDEX=$(gcloud firestore indexes composite list \
        --database="(default)" --project="$PROJECT_ID" \
        --format="value(name)" 2>/dev/null \
        | grep "/collectionGroups/wiki/" | head -1 || true)

    if [ -n "$EXISTING_INDEX" ]; then
        echo "  Firestore vector index already exists (skipping)."
    else
        echo "  Creating Firestore vector index on wiki/embedding (may take 5-10 min)..."
        ACCESS_TOKEN=$(gcloud auth print-access-token)
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST \
            "https://firestore.googleapis.com/v1/projects/$PROJECT_ID/databases/(default)/collectionGroups/wiki/indexes" \
            -H "Authorization: Bearer $ACCESS_TOKEN" \
            -H "Content-Type: application/json" \
            -H "X-Goog-User-Project: $PROJECT_ID" \
            -d '{
                "queryScope": "COLLECTION",
                "fields": [
                    {"fieldPath": "__name__", "order": "ASCENDING"},
                    {"fieldPath": "embedding", "vectorConfig": {"dimension": 1536, "flat": {}}}
                ]
            }')
        if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
            echo "    Vector index creation started."
        else
            echo "    WARNING: Vector index creation returned HTTP $HTTP_CODE (may already exist)."
        fi
    fi
) > /tmp/helpdesk-firestore.log 2>&1 &
BG_FIRESTORE_PID=$!
echo "  Firestore provisioning started in background (PID $BG_FIRESTORE_PID)"

# ══════════════════════════════════════════════════════════════════
# Step 4: Identity Platform (Firebase Auth)
# ══════════════════════════════════════════════════════════════════
echo ""
echo "==> Step 4/9: Configuring Identity Platform (Firebase Auth)..."
# Firebase was set up manually (prerequisite). Just ensure email/password
# sign-in is enabled via the Identity Platform config API.
ACCESS_TOKEN=$(gcloud auth print-access-token)
CONFIG_URL="https://identitytoolkit.googleapis.com/admin/v2/projects/$PROJECT_ID/config"

HTTP_CODE=$(curl -s -o /tmp/helpdesk-idp-response.json -w "%{http_code}" \
    -X PATCH \
    "$CONFIG_URL?updateMask=signIn.email.enabled,signIn.email.passwordRequired" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Goog-User-Project: $PROJECT_ID" \
    -d '{
        "signIn": {
            "email": {
                "enabled": true,
                "passwordRequired": true
            }
        }
    }')
if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo "  Identity Platform configured (email/password enabled)."
else
    echo "  WARNING: Identity Platform config returned HTTP $HTTP_CODE"
    cat /tmp/helpdesk-idp-response.json 2>/dev/null || true
    echo ""
    echo "  (This usually means Firebase was not set up for this project.)"
    echo "  (The deploy will continue, but seed_data may fail.)"
fi

# ══════════════════════════════════════════════════════════════════
# Step 5: GCS Bucket
# ══════════════════════════════════════════════════════════════════
echo ""
echo "==> Step 5/9: GCS bucket..."
gcloud_create "GCS bucket '$BUCKET_NAME'" \
    gcloud storage buckets create "gs://$BUCKET_NAME" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --project="$PROJECT_ID" --quiet

# ══════════════════════════════════════════════════════════════════
# Step 6: Secret Manager
# ══════════════════════════════════════════════════════════════════
echo ""
echo "==> Step 6/9: Secret Manager secrets..."

create_or_update_secret() {
    local secret_id="$1" secret_value="$2"
    gcloud_create "secret '$secret_id'" \
        gcloud secrets create "$secret_id" \
        --replication-policy=automatic \
        --project="$PROJECT_ID" --quiet

    echo "  Setting latest version for '$secret_id'..."
    printf '%s' "$secret_value" | gcloud secrets versions add "$secret_id" \
        --data-file=- --project="$PROJECT_ID" --quiet
}

create_or_update_secret "openai-api-key" "$OPENAI_API_KEY"

if [ -n "${LANGSMITH_API_KEY:-}" ]; then
    create_or_update_secret "langsmith-api-key" "$LANGSMITH_API_KEY"
fi

# ══════════════════════════════════════════════════════════════════
# Step 7: Service Account + IAM
# ══════════════════════════════════════════════════════════════════
echo ""
echo "==> Step 7/9: Service accounts + IAM bindings..."

# Get project number for default compute SA
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
DEFAULT_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Create custom SA
gcloud_create "service account 'helpdesk-agent'" \
    gcloud iam service-accounts create helpdesk-agent \
    --display-name="Helpdesk Agent (Least Privilege)" \
    --project="$PROJECT_ID" --quiet

# Project-level IAM roles for custom SA
for role in roles/datastore.user roles/logging.logWriter roles/aiplatform.user; do
    echo "  Granting $role to custom SA..."
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$CUSTOM_SA" \
        --role="$role" \
        --condition=None \
        --quiet > /dev/null 2>&1 || \
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$CUSTOM_SA" \
        --role="$role" \
        --quiet > /dev/null
done

# Secret accessor for BOTH SAs on openai-api-key
for sa in "$DEFAULT_SA" "$CUSTOM_SA"; do
    echo "  Granting secretAccessor on openai-api-key to $(echo "$sa" | cut -d@ -f1)..."
    gcloud secrets add-iam-policy-binding openai-api-key \
        --member="serviceAccount:$sa" \
        --role="roles/secretmanager.secretAccessor" \
        --project="$PROJECT_ID" \
        --quiet > /dev/null
done

# Secret accessor for demo secrets (stripe-api-key, database-password) — default SA only.
# The custom least-privilege SA deliberately does NOT get access (Demo 6 needs denial).
for secret_name in stripe-api-key database-password; do
    echo "  Granting secretAccessor on $secret_name to default SA..."
    gcloud secrets add-iam-policy-binding "$secret_name" \
        --member="serviceAccount:$DEFAULT_SA" \
        --role="roles/secretmanager.secretAccessor" \
        --project="$PROJECT_ID" \
        --quiet > /dev/null 2>&1 || true
done

# Secret accessor for langsmith-api-key (if it exists)
if [ -n "${LANGSMITH_API_KEY:-}" ]; then
    for sa in "$DEFAULT_SA" "$CUSTOM_SA"; do
        echo "  Granting secretAccessor on langsmith-api-key to $(echo "$sa" | cut -d@ -f1)..."
        gcloud secrets add-iam-policy-binding langsmith-api-key \
            --member="serviceAccount:$sa" \
            --role="roles/secretmanager.secretAccessor" \
            --project="$PROJECT_ID" \
            --quiet > /dev/null
    done
fi

# ══════════════════════════════════════════════════════════════════
# Step 8: Build & push container image (parallel with Step 3)
# ══════════════════════════════════════════════════════════════════
echo ""
echo "==> Step 8/9: Build & push container image..."
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

cd "$MODULE_DIR"
docker pull "$IMAGE" 2>/dev/null || true
docker build --platform linux/amd64 --cache-from "$IMAGE" -t "$IMAGE" -f agent/Dockerfile .
docker push "$IMAGE"

# ── Wait for background Firestore provisioning ─────────────────
echo ""
echo "  Docker image pushed. Waiting for Firestore background job..."
if ! wait "$BG_FIRESTORE_PID"; then
    echo ""
    echo "ERROR: Firestore provisioning failed:"
    cat /tmp/helpdesk-firestore.log
    exit 1
fi
BG_FIRESTORE_PID=""
echo "  Firestore ready."
cat /tmp/helpdesk-firestore.log
rm -f /tmp/helpdesk-firestore.log

# ══════════════════════════════════════════════════════════════════
# Step 9: Deploy Cloud Run service
# ══════════════════════════════════════════════════════════════════
echo ""
echo "==> Step 9/9: Deploying Cloud Run service..."

# Choose service account based on toggle
if [ "$USE_LEAST_PRIVILEGE" = "true" ]; then
    RUN_SA="$CUSTOM_SA"
    echo "  Using LEAST-PRIVILEGE service account: $CUSTOM_SA"
else
    RUN_SA="$DEFAULT_SA"
    echo "  Using DEFAULT COMPUTE service account: $DEFAULT_SA"
fi

# Build env vars string
ENV_VARS="GCP_PROJECT=$PROJECT_ID"
ENV_VARS+=",COMPANY_ID=techcorp"
ENV_VARS+=",SECURITY_LEVEL=$SECURITY_LEVEL"
ENV_VARS+=",LLM_MODEL=$LLM_MODEL"
ENV_VARS+=",LLM_TEMPERATURE=0"
ENV_VARS+=",LANGSMITH_TRACING=${LANGSMITH_TRACING:-false}"
ENV_VARS+=",LANGSMITH_PROJECT=${LANGSMITH_PROJECT:-ai-security-course}"
ENV_VARS+=",FIREBASE_API_KEY=${FIREBASE_API_KEY:-}"
ENV_VARS+=",EMBEDDING_MODEL=text-embedding-3-small"

# Build secrets string
SECRETS="OPENAI_API_KEY=openai-api-key:latest"
if [ -n "${LANGSMITH_API_KEY:-}" ]; then
    SECRETS+=",LANGSMITH_API_KEY=langsmith-api-key:latest"
fi

gcloud run deploy helpdesk-agent \
    --image="$IMAGE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --service-account="$RUN_SA" \
    --set-env-vars="$ENV_VARS" \
    --set-secrets="$SECRETS" \
    --cpu=1 \
    --memory=512Mi \
    --min-instances=0 \
    --max-instances=1 \
    --port=8080 \
    --allow-unauthenticated \
    --quiet

# ── Capture service URL ─────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe helpdesk-agent \
    --region="$REGION" --project="$PROJECT_ID" \
    --format="value(status.url)")

# ── Log Cloud Run env vars ──────────────────────────────────────
echo ""
echo "==> Cloud Run environment variables:"
gcloud run services describe helpdesk-agent \
    --region "$REGION" --project "$PROJECT_ID" \
    --format=json 2>/dev/null \
| python3 -c "
import json, sys
svc = json.load(sys.stdin)
envs = svc['spec']['template']['spec']['containers'][0].get('env', [])
for e in envs:
    name = e.get('name', '')
    if 'valueFrom' in e:
        val = '****(from Secret Manager)'
    else:
        v = e.get('value', '')
        if any(k in name.upper() for k in ['KEY', 'SECRET', 'PASSWORD', 'TOKEN']):
            val = v[:4] + '****' if len(v) > 4 else '****'
        else:
            val = v
    print(f'  {name}={val}')
" || echo "  (could not read Cloud Run env vars)"

# ── Seed cloud data ─────────────────────────────────────────────
echo ""
echo "==> Seeding cloud data..."
cd "$MODULE_DIR"
if GCP_PROJECT="$PROJECT_ID" ./run -m demos.seed_data 2>&1; then
    echo ""
    echo "========================================="
    echo "  Deployment complete!"
    echo "========================================="
else
    echo ""
    echo "========================================="
    echo "  Infrastructure deployed! Seeding failed."
    echo "========================================="
    echo ""
    echo "  Check the error above. Common fixes:"
    echo "    - Ensure billing is enabled on the project"
    echo "    - Run: gcloud auth application-default login"
    echo "    - Re-run: bash deploy_gcloud.sh"
fi


# ── Save AGENT_URL to .env ────────────────────────────────────
if [ -n "${SERVICE_URL:-}" ]; then
    if grep -q '^AGENT_URL=' "$MODULE_DIR/.env" 2>/dev/null; then
        sed -i '' "s|^AGENT_URL=.*|AGENT_URL=$SERVICE_URL|" "$MODULE_DIR/.env"
    else
        echo "AGENT_URL=$SERVICE_URL" >> "$MODULE_DIR/.env"
    fi
    echo ""
    echo "  Service URL: $SERVICE_URL"
    echo "  AGENT_URL saved to .env"
fi
