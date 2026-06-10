#!/usr/bin/env bash
# Full Cloud Run deployment + Cloud Scheduler setup for SiteTrax.io Atlas Agent.
#
# Prerequisites:
#   - gcloud CLI authenticated: gcloud auth login && gcloud auth application-default login
#   - Project set:              gcloud config set project <PROJECT_ID>
#   - APIs enabled:
#       gcloud services enable run.googleapis.com \
#         cloudbuild.googleapis.com cloudscheduler.googleapis.com \
#         firestore.googleapis.com aiplatform.googleapis.com
#   - .env populated with real tokens (USE_REAL_API=true, SITETRAX_* etc.)
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh [--region us-central1] [--service sitetrax-coordinator]

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-sitetrax-coordinator}"
MCP_SERVICE="${MCP_SERVICE:-sitetrax-mcp}"
SCHEDULER_JOB="${SCHEDULER_JOB:-sitetrax-eval}"
EVAL_SCHEDULE="${EVAL_SCHEDULE:-*/10 * * * *}"   # every 10 minutes

# Parse CLI flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --mcp-service) MCP_SERVICE="$2"; shift 2 ;;
    --skip-mcp) SKIP_MCP=1; shift ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done
SKIP_MCP="${SKIP_MCP:-0}"

echo "Project:      $PROJECT_ID"
echo "Region:       $REGION"
echo "Service:      $SERVICE"
echo "MCP service:  $MCP_SERVICE"
echo ""

# Keep the ADK coordinator mirror aligned before building deployment images.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/../scripts/sync_coordinator.sh"

# ── Load .env for secret values ───────────────────────────────────────────────
if [[ ! -f .env ]]; then
  echo "ERROR: .env not found. Copy .env.example → .env and fill in your secrets."
  exit 1
fi
set -o allexport; source .env; set +o allexport

# ── 1. Build and push the image ───────────────────────────────────────────────
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}:latest"
echo "Building image: $IMAGE"
docker build -t "$IMAGE" .
docker push "$IMAGE"

# ── 2. Deploy to Cloud Run ────────────────────────────────────────────────────
echo ""
echo "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=1 \
  --max-instances=4 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --concurrency=80 \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=${REGION}" \
  --set-env-vars="GOOGLE_MODEL=${GOOGLE_MODEL:-gemini-2.5-flash}" \
  --set-env-vars="USE_REAL_API=${USE_REAL_API:-true}" \
  --set-env-vars="SITETRAX_API_BASE=${SITETRAX_API_BASE:-}" \
  --set-env-vars="SITETRAX_ACCESS_TOKEN=${SITETRAX_ACCESS_TOKEN:-}" \
  --set-env-vars="SITETRAX_REFRESH_TOKEN=${SITETRAX_REFRESH_TOKEN:-}" \
  --set-env-vars="SITETRAX_REFRESH_SKEW_SECONDS=${SITETRAX_REFRESH_SKEW_SECONDS:-60}" \
  --set-env-vars="SITETRAX_FACILITY_TIMEOUT=${SITETRAX_FACILITY_TIMEOUT:-90}" \
  --set-env-vars="EMAIL_PROVIDER=${EMAIL_PROVIDER:-none}" \
  --set-env-vars="RESEND_API_KEY=${RESEND_API_KEY:-}" \
  --set-env-vars="ALERT_EMAIL_FROM=${ALERT_EMAIL_FROM:-onboarding@resend.dev}" \
  --set-env-vars="ALERT_EMAIL_TO=${ALERT_EMAIL_TO:-}" \
  --set-env-vars="TASKS_TOKEN=${TASKS_TOKEN:-}" \
  --set-env-vars="ENABLE_POLLER=false" \
  --set-env-vars="ALLOW_ORIGINS=${ALLOW_ORIGINS:-*}"

# Retrieve the deployed URL
SERVICE_URL=$(gcloud run services describe "$SERVICE" \
  --region="$REGION" --format="value(status.url)")
echo ""
echo "Cloud Run URL: $SERVICE_URL"

# ── 3. Verify health ──────────────────────────────────────────────────────────
echo ""
echo "Health check..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health")
if [[ "$HTTP_STATUS" == "200" ]]; then
  echo "  /health → 200 OK"
else
  echo "  WARNING: /health returned $HTTP_STATUS — check Cloud Run logs"
fi

# ── 4. Build + deploy the MCP HTTP server (remote MCP for Anthropic connector) ──
if [[ "$SKIP_MCP" != "1" ]]; then
  MCP_IMAGE="gcr.io/${PROJECT_ID}/${MCP_SERVICE}:latest"
  echo ""
  echo "Building MCP HTTP server image: $MCP_IMAGE"
  docker build -t "$MCP_IMAGE" -f Dockerfile.mcp .
  docker push "$MCP_IMAGE"

  # First deploy (without MCP_SERVER_URL — we need the URL it gets assigned)
  echo "Deploying MCP service (first pass to get URL)..."
  gcloud run deploy "$MCP_SERVICE" \
    --image="$MCP_IMAGE" \
    --region="$REGION" \
    --platform=managed \
    --allow-unauthenticated \
    --min-instances=0 \
    --max-instances=2 \
    --memory=512Mi \
    --cpu=1 \
    --timeout=60 \
    --set-env-vars="USE_REAL_API=${USE_REAL_API:-true}" \
    --set-env-vars="SITETRAX_API_BASE=${SITETRAX_API_BASE:-}" \
    --set-env-vars="SITETRAX_ACCESS_TOKEN=${SITETRAX_ACCESS_TOKEN:-}" \
    --set-env-vars="SITETRAX_REFRESH_TOKEN=${SITETRAX_REFRESH_TOKEN:-}" \
    --set-env-vars="MCP_CLIENT_SECRET=${MCP_CLIENT_SECRET:-}" \
    --set-env-vars="MCP_TOKEN_TTL=${MCP_TOKEN_TTL:-3600}"

  MCP_URL=$(gcloud run services describe "$MCP_SERVICE" \
    --region="$REGION" --format="value(status.url)")
  echo "  MCP service URL: $MCP_URL"

  # Second pass — set MCP_SERVER_URL so OAuth issuer URL is correct
  echo "  Updating MCP_SERVER_URL..."
  gcloud run services update "$MCP_SERVICE" \
    --region="$REGION" \
    --update-env-vars="MCP_SERVER_URL=${MCP_URL}"

  echo ""
  echo "MCP server ready. Add to Anthropic connector / claude.ai:"
  echo "  URL:    ${MCP_URL}/mcp"
  echo "  OAuth:  ${MCP_URL}/.well-known/oauth-authorization-server"
  echo ""
  echo "When prompted for the access secret, enter the value of MCP_CLIENT_SECRET."
else
  MCP_URL=""
  echo ""
  echo "Skipped MCP HTTP server deploy (--skip-mcp)."
fi

# ── 5. Set up Cloud Scheduler → /tasks/evaluate ──────────────────────────────
echo ""
echo "Setting up Cloud Scheduler job: ${SCHEDULER_JOB} (${EVAL_SCHEDULE})"

# Build the curl body for the scheduler job
SCHEDULER_BODY="{}"
SCHEDULER_HEADERS=""
if [[ -n "${TASKS_TOKEN:-}" ]]; then
  SCHEDULER_HEADERS="X-Tasks-Token:${TASKS_TOKEN}"
fi

# Create or update the scheduler job
if gcloud scheduler jobs describe "$SCHEDULER_JOB" --location="$REGION" &>/dev/null; then
  echo "  Updating existing scheduler job..."
  UPDATE_CMD=(gcloud scheduler jobs update http "$SCHEDULER_JOB"
    --location="$REGION"
    --schedule="$EVAL_SCHEDULE"
    --uri="${SERVICE_URL}/tasks/evaluate"
    --http-method=POST
    --message-body="{}"
    --attempt-deadline=60s
  )
  if [[ -n "${TASKS_TOKEN:-}" ]]; then
    UPDATE_CMD+=(--headers="X-Tasks-Token=${TASKS_TOKEN}")
  fi
  "${UPDATE_CMD[@]}"
else
  echo "  Creating new scheduler job..."
  CREATE_CMD=(gcloud scheduler jobs create http "$SCHEDULER_JOB"
    --location="$REGION"
    --schedule="$EVAL_SCHEDULE"
    --uri="${SERVICE_URL}/tasks/evaluate"
    --http-method=POST
    --message-body="{}"
    --attempt-deadline=60s
    --time-zone="UTC"
  )
  if [[ -n "${TASKS_TOKEN:-}" ]]; then
    CREATE_CMD+=(--headers="X-Tasks-Token=${TASKS_TOKEN}")
  fi
  "${CREATE_CMD[@]}"
fi

echo ""
echo "Done."
echo ""
echo "Summary:"
echo "  Main service URL:  ${SERVICE_URL}"
echo "  Health:            ${SERVICE_URL}/health"
echo "  Scheduler job:     ${SCHEDULER_JOB} (${EVAL_SCHEDULE})"
echo "  Firestore:         auto-enabled (USE_FIRESTORE omitted → true on Cloud Run)"
echo "  Email provider:    ${EMAIL_PROVIDER:-none}"
if [[ -n "${MCP_URL:-}" ]]; then
  echo ""
  echo "  MCP HTTP server:"
  echo "    URL:            ${MCP_URL}/mcp"
  echo "    OAuth metadata: ${MCP_URL}/.well-known/oauth-authorization-server"
  echo "    Add in claude.ai → Settings → Integrations → Add MCP server"
  echo "    Enter URL: ${MCP_URL}/mcp"
  echo "    When prompted for secret: use MCP_CLIENT_SECRET from .env"
fi
echo ""
echo "Test the scheduler manually:"
echo "  gcloud scheduler jobs run ${SCHEDULER_JOB} --location=${REGION}"
echo ""
echo "Test /tasks/evaluate directly:"
if [[ -n "${TASKS_TOKEN:-}" ]]; then
  echo "  curl -X POST ${SERVICE_URL}/tasks/evaluate -H 'X-Tasks-Token: \${TASKS_TOKEN}'"
else
  echo "  curl -X POST ${SERVICE_URL}/tasks/evaluate"
fi
