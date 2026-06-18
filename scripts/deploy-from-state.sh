#!/usr/bin/env bash
# Trigger the Pages refresh workflow after publishing local state data.

set -euo pipefail

REPO="${GH_REPO:-sorahane-kyoukai/daily-paper-report}"
WORKFLOW="${DEPLOY_WORKFLOW:-deploy-from-state.yaml}"
REF="${DEPLOY_REF:-main}"
STATE_REF="${STATE_REF:-state}"
WATCH=true

usage() {
  cat <<EOF
Usage: $0 [--repo OWNER/REPO] [--ref REF] [--state-ref REF] [--no-watch]

Options:
  --repo       GitHub repository. Defaults to ${REPO}
  --ref        Branch or tag containing the workflow file. Defaults to ${REF}
  --state-ref  State branch, tag, or SHA to deploy. Defaults to ${STATE_REF}
  --no-watch   Trigger the workflow without waiting for completion
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --ref)
      REF="$2"
      shift 2
      ;;
    --state-ref)
      STATE_REF="$2"
      shift 2
      ;;
    --no-watch)
      WATCH=false
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run 'gh auth login' first." >&2
  exit 1
fi

requested_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

gh workflow run "${WORKFLOW}" \
  --repo "${REPO}" \
  --ref "${REF}" \
  -f "state_ref=${STATE_REF}"

echo "Triggered ${WORKFLOW} for ${REPO} from ${STATE_REF}."

if [ "${WATCH}" != "true" ]; then
  exit 0
fi

run_id=""
for _ in $(seq 1 30); do
  run_id=$(
    gh run list \
      --repo "${REPO}" \
      --workflow "${WORKFLOW}" \
      --limit 10 \
      --json databaseId,createdAt,event \
      --jq "map(select(.event == \"workflow_dispatch\" and .createdAt >= \"${requested_at}\")) | .[0].databaseId // \"\""
  )

  if [ -n "${run_id}" ]; then
    break
  fi

  sleep 2
done

if [ -z "${run_id}" ]; then
  echo "Workflow was triggered, but the run did not appear in time." >&2
  exit 1
fi

echo "Watching run ${run_id}..."
gh run watch "${run_id}" --repo "${REPO}" --exit-status
