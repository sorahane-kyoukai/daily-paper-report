#!/usr/bin/env bash
# Run the digest pipeline locally with DeepSeek as the LLM provider.
#
# The script mirrors the useful parts of .github/workflows/daily-digest.yaml
# without depending on GitHub-hosted runner utilities such as GNU find or jq.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

REPO="${GH_REPO:-sorahane-kyoukai/daily-paper-report}"
STATE_BRANCH="${STATE_BRANCH:-state}"
STATE_REF="${STATE_REF:-${STATE_BRANCH}}"
STATE_FILE="${STATE_FILE:-state.sqlite}"
OUTPUT_DIR="${OUTPUT_DIR:-public}"
CONFIG_DIR="${CONFIG_DIR:-tests/fixtures/config}"
TIMEZONE="${TIMEZONE:-Asia/Taipei}"
LOOKBACK_HOURS="${LOOKBACK_HOURS:-24}"
REPORT_MODE="${REPORT_MODE:-auto}"
RUN_MODE="${RUN_MODE:-auto}"
TARGET_DATE="${TARGET_DATE:-}"
RESTORE_STATE=true
BUILD_FRONTEND=true
INSTALL_DEPS=true
PUSH_STATE=false
DEPLOY=false
SKIP_TRANSLATION=false
SOURCE_MAX_ITEMS="${SOURCE_MAX_ITEMS:-}"

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --date YYYY-MM-DD       Target local date. Defaults to today in ${TIMEZONE}.
  --mode auto|run|backfill
                          auto runs fresh collection for today, backfill otherwise.
  --report-mode MODE      auto, none, weekly, monthly, or all. Default: ${REPORT_MODE}
  --lookback HOURS        Fresh run lookback window. Default: ${LOOKBACK_HOURS}
  --source-max-items N    Override per-source max_items for this run.
  --no-restore-state      Do not restore state/public archives from ${STATE_REF}.
  --skip-frontend         Do not build the Vue frontend.
  --skip-install          Do not run uv sync --frozen.
  --no-translate          Skip the translation phase.
  --push-state            Push generated state/public archives to ${STATE_BRANCH}.
  --deploy                Trigger scripts/deploy-from-state.sh after --push-state.
  --help, -h              Show this help.

DeepSeek environment:
  Required in .env or shell: DEEPSEEK_API_KEY
  Defaults set by this script:
    LLM_PROVIDER=deepseek
    OPENAI_BASE_URL=https://api.deepseek.com
    OPENAI_MODEL=deepseek-v4-pro
    OPENAI_THINKING_TYPE=enabled
    OPENAI_REASONING_EFFORT=high

Examples:
  $0
  $0 --date 2026-06-21 --report-mode weekly
  OPENAI_MODEL=deepseek-v4-flash $0 --push-state --deploy
EOF
}

log() {
  printf '[local-deepseek] %s\n' "$*"
}

die() {
  printf '[local-deepseek] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required."
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --date)
      TARGET_DATE="$2"
      shift 2
      ;;
    --mode)
      RUN_MODE="$2"
      shift 2
      ;;
    --report-mode)
      REPORT_MODE="$2"
      shift 2
      ;;
    --lookback)
      LOOKBACK_HOURS="$2"
      shift 2
      ;;
    --source-max-items)
      SOURCE_MAX_ITEMS="$2"
      shift 2
      ;;
    --no-restore-state)
      RESTORE_STATE=false
      shift
      ;;
    --skip-frontend)
      BUILD_FRONTEND=false
      shift
      ;;
    --skip-install)
      INSTALL_DEPS=false
      shift
      ;;
    --no-translate)
      SKIP_TRANSLATION=true
      shift
      ;;
    --push-state)
      PUSH_STATE=true
      shift
      ;;
    --deploy)
      PUSH_STATE=true
      DEPLOY=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

case "${RUN_MODE}" in
  auto|run|backfill) ;;
  *) die "--mode must be auto, run, or backfill." ;;
esac

case "${REPORT_MODE}" in
  auto|none|weekly|monthly|all) ;;
  *) die "--report-mode must be auto, none, weekly, monthly, or all." ;;
esac

require_cmd git
require_cmd python3
require_cmd uv

if [ "${BUILD_FRONTEND}" = "true" ]; then
  require_cmd pnpm
fi

if [ -z "${TARGET_DATE}" ]; then
  TARGET_DATE="$(
    python3 - "${TIMEZONE}" <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo
import sys

print(datetime.now(ZoneInfo(sys.argv[1])).date().isoformat())
PY
  )"
fi

python3 - "${TARGET_DATE}" <<'PY'
from datetime import date
import sys

try:
    date.fromisoformat(sys.argv[1])
except ValueError as exc:
    raise SystemExit(f"Invalid --date {sys.argv[1]!r}; expected YYYY-MM-DD") from exc
PY

TODAY_LOCAL="$(
  python3 - "${TIMEZONE}" <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo
import sys

print(datetime.now(ZoneInfo(sys.argv[1])).date().isoformat())
PY
)"

if [ "${RUN_MODE}" = "auto" ]; then
  if [ "${TARGET_DATE}" = "${TODAY_LOCAL}" ]; then
    RUN_MODE="run"
  else
    RUN_MODE="backfill"
  fi
fi

GENERATE_WEEKLY=false
GENERATE_MONTHLY=false
case "${REPORT_MODE}" in
  auto)
    read -r WEEKDAY DAY_OF_MONTH < <(
      python3 - "${TARGET_DATE}" <<'PY'
from datetime import date
import sys

target = date.fromisoformat(sys.argv[1])
print(target.isoweekday(), target.day)
PY
    )
    if [ "${WEEKDAY}" = "7" ]; then
      GENERATE_WEEKLY=true
    fi
    if [ "${DAY_OF_MONTH}" = "1" ]; then
      GENERATE_MONTHLY=true
    fi
    ;;
  weekly)
    GENERATE_WEEKLY=true
    ;;
  monthly)
    GENERATE_MONTHLY=true
    ;;
  all)
    GENERATE_WEEKLY=true
    GENERATE_MONTHLY=true
    ;;
  none)
    ;;
esac

export LLM_PROVIDER="${LLM_PROVIDER:-deepseek}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.deepseek.com}"
export OPENAI_MODEL="${OPENAI_MODEL:-deepseek-v4-pro}"
export OPENAI_THINKING_TYPE="${OPENAI_THINKING_TYPE:-enabled}"
export OPENAI_REASONING_EFFORT="${OPENAI_REASONING_EFFORT:-high}"
export LLM_RELEVANCE_BATCH_SIZE="${LLM_RELEVANCE_BATCH_SIZE:-5}"
export LLM_TRANSLATION_BATCH_SIZE="${LLM_TRANSLATION_BATCH_SIZE:-5}"

if [ "${INSTALL_DEPS}" = "true" ]; then
  log "Installing Python dependencies with uv sync --frozen"
  uv sync --frozen
fi

uv run python - <<'PY'
from src.settings.app import get_settings

settings = get_settings()
if not settings.deepseek_api_key:
    raise SystemExit("DEEPSEEK_API_KEY is required in .env or the shell.")
PY

restore_state() {
  log "Restoring ${STATE_REF} into ${STATE_FILE} and ${OUTPUT_DIR}/"
  git fetch --depth=1 origin "${STATE_REF}"
  local state_commit
  state_commit="$(git rev-parse FETCH_HEAD)"

  mkdir -p \
    "${OUTPUT_DIR}/api/day" \
    "${OUTPUT_DIR}/api/reports/weekly" \
    "${OUTPUT_DIR}/api/reports/monthly" \
    "${OUTPUT_DIR}/day" \
    "${OUTPUT_DIR}/reports/weekly" \
    "${OUTPUT_DIR}/reports/monthly"

  restore_tree() {
    local tree_path="$1"
    git ls-tree -r --name-only "${state_commit}" "${tree_path}" 2>/dev/null |
      while IFS= read -r file; do
        [ -n "${file}" ] || continue
        mkdir -p "$(dirname "${OUTPUT_DIR}/${file}")"
        git show "${state_commit}:${file}" > "${OUTPUT_DIR}/${file}"
      done
  }

  restore_file() {
    local file="$1"
    local target="${2:-${OUTPUT_DIR}/${file}}"
    if git cat-file -e "${state_commit}:${file}" 2>/dev/null; then
      mkdir -p "$(dirname "${target}")"
      git show "${state_commit}:${file}" > "${target}"
    fi
  }

  restore_tree "api/day/"
  restore_tree "api/reports/"
  restore_tree "day/"
  restore_tree "reports/"
  restore_file "api/daily.json"
  restore_file "api/llm_scores.json"
  restore_file "api/translations_zh.json"

  if ! git show "${state_commit}:${STATE_FILE}" > "${STATE_FILE}" 2>/dev/null; then
    die "Missing ${STATE_FILE} in ${STATE_REF}."
  fi
  if ! head -c 15 "${STATE_FILE}" | grep -q "SQLite format 3"; then
    die "Restored ${STATE_FILE} is not a SQLite database."
  fi
}

run_digest() {
  local cmd=(
    uv run python main.py run
    --config "${CONFIG_DIR}/sources.yaml"
    --entities "${CONFIG_DIR}/entities.yaml"
    --topics "${CONFIG_DIR}/topics.yaml"
    --state "${STATE_FILE}"
    --out "${OUTPUT_DIR}"
    --tz "${TIMEZONE}"
    --date "${TARGET_DATE}"
    --lookback "${LOOKBACK_HOURS}"
    --json-logs
  )
  if [ -n "${SOURCE_MAX_ITEMS}" ]; then
    cmd+=(--source-max-items "${SOURCE_MAX_ITEMS}")
  fi
  if [ "${SKIP_TRANSLATION}" = "true" ]; then
    cmd+=(--no-translate)
  fi
  log "Running fresh digest for ${TARGET_DATE}"
  "${cmd[@]}"
}

run_backfill() {
  log "Backfilling ${TARGET_DATE} from existing state"
  uv run python main.py backfill \
    --config "${CONFIG_DIR}/sources.yaml" \
    --entities "${CONFIG_DIR}/entities.yaml" \
    --topics "${CONFIG_DIR}/topics.yaml" \
    --state "${STATE_FILE}" \
    --out "${OUTPUT_DIR}" \
    --tz "${TIMEZONE}" \
    --date "${TARGET_DATE}" \
    --overwrite-existing \
    --json-logs
}

run_reports() {
  if [ "${GENERATE_WEEKLY}" = "true" ]; then
    log "Generating weekly report for date ${TARGET_DATE}"
    uv run python main.py report \
      --type weekly \
      --out "${OUTPUT_DIR}" \
      --tz "${TIMEZONE}" \
      --date "${TARGET_DATE}" \
      --limit 100 \
      --archive-lookahead-days 1 \
      --json-logs
  fi

  if [ "${GENERATE_MONTHLY}" = "true" ]; then
    log "Generating previous-month monthly report from date ${TARGET_DATE}"
    uv run python main.py report \
      --type monthly \
      --out "${OUTPUT_DIR}" \
      --tz "${TIMEZONE}" \
      --date "${TARGET_DATE}" \
      --previous-month \
      --limit 100 \
      --archive-lookahead-days 1 \
      --json-logs
  fi
}

build_frontend() {
  log "Building Vue frontend"
  ensure_frontend_pnpm_workspace
  (
    cd frontend
    pnpm install --frozen-lockfile
    pnpm run build-only
  )

  mkdir -p "${OUTPUT_DIR}"
  cp frontend/dist/index.html "${OUTPUT_DIR}/index.html"
  cp frontend/dist/index.html "${OUTPUT_DIR}/404.html"
  rm -rf "${OUTPUT_DIR}/assets"
  cp -R frontend/dist/assets "${OUTPUT_DIR}/assets"

  for route in archive sources status reports; do
    mkdir -p "${OUTPUT_DIR}/${route}"
    cp frontend/dist/index.html "${OUTPUT_DIR}/${route}.html"
    cp frontend/dist/index.html "${OUTPUT_DIR}/${route}/index.html"
  done
}

ensure_frontend_pnpm_workspace() {
  local workspace_file="${ROOT_DIR}/frontend/pnpm-workspace.yaml"
  local pnpm_version
  local pnpm_major

  pnpm_version="$(pnpm --version 2>/dev/null || true)"
  pnpm_major="${pnpm_version%%.*}"
  case "${pnpm_major}" in
    ""|*[!0-9]*)
      pnpm_major=0
      ;;
  esac

  if [ -f "${workspace_file}" ]; then
    if grep -q "set this to true or false" "${workspace_file}" || ! grep -q "^packages:" "${workspace_file}"; then
      log "Refreshing local pnpm workspace build approvals"
      write_frontend_pnpm_workspace "${workspace_file}"
    fi
  elif [ "${pnpm_major}" -ge 10 ]; then
    log "Writing local pnpm workspace build approvals for pnpm ${pnpm_version}"
    write_frontend_pnpm_workspace "${workspace_file}"
  fi
}

write_frontend_pnpm_workspace() {
  local workspace_file="$1"

  cat > "${workspace_file}" <<'YAML'
packages:
  - "."
allowBuilds:
  esbuild: true
  vue-demi: true
YAML
}

prepare_archive_output() {
  log "Preparing archive output"
  mkdir -p \
    "${OUTPUT_DIR}/api/day" \
    "${OUTPUT_DIR}/api/reports" \
    "${OUTPUT_DIR}/day" \
    "${OUTPUT_DIR}/reports/weekly" \
    "${OUTPUT_DIR}/reports/monthly"

  [ -f "${STATE_FILE}" ] || die "Missing ${STATE_FILE}."
  cp "${STATE_FILE}" "${OUTPUT_DIR}/api/state.sqlite"

  if [ ! -f "${OUTPUT_DIR}/api/day/${TARGET_DATE}.json" ]; then
    die "Missing ${OUTPUT_DIR}/api/day/${TARGET_DATE}.json after ${RUN_MODE}."
  fi

  if [ ! -f "${OUTPUT_DIR}/api/daily.json" ]; then
    cp "${OUTPUT_DIR}/api/day/${TARGET_DATE}.json" "${OUTPUT_DIR}/api/daily.json"
  fi

  python3 - "${OUTPUT_DIR}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

out = Path(sys.argv[1])
api_day = out / "api" / "day"
daily = out / "api" / "daily.json"
reports_index = out / "api" / "reports" / "index.json"

dates = sorted(
    (p.stem for p in api_day.glob("*.json") if len(p.stem) == 10),
    reverse=True,
)

payload = json.loads(daily.read_text())
payload["archive_dates"] = dates
daily.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
)

if not reports_index.exists():
    reports_index.parent.mkdir(parents=True, exist_ok=True)
    reports_index.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "latest": {"weekly": None, "monthly": None},
                "weekly": [],
                "monthly": [],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
PY

  if [ -f "${OUTPUT_DIR}/index.html" ]; then
    for json_file in "${OUTPUT_DIR}/api/day/"*.json; do
      [ -f "${json_file}" ] || continue
      local day
      day="$(basename "${json_file}" .json)"
      cp "${OUTPUT_DIR}/index.html" "${OUTPUT_DIR}/day/${day}.html"
    done

    for report_type in weekly monthly; do
      for json_file in "${OUTPUT_DIR}/api/reports/${report_type}/"*.json; do
        [ -f "${json_file}" ] || continue
        local period
        period="$(basename "${json_file}" .json)"
        mkdir -p "${OUTPUT_DIR}/reports/${report_type}"
        cp "${OUTPUT_DIR}/index.html" "${OUTPUT_DIR}/reports/${report_type}/${period}.html"
      done
    done
  fi
}

push_state() {
  log "Pushing state payload to ${STATE_BRANCH}"
  local remote_url
  remote_url="$(git remote get-url origin)"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' RETURN

  if ! git clone --depth=1 --branch "${STATE_BRANCH}" "${remote_url}" "${tmp_dir}" >/dev/null 2>&1; then
    rm -rf "${tmp_dir}"
    tmp_dir="$(mktemp -d)"
    git init "${tmp_dir}" >/dev/null
    (
      cd "${tmp_dir}"
      git checkout --orphan "${STATE_BRANCH}" >/dev/null 2>&1
      git remote add origin "${remote_url}"
    )
  fi

  (
    cd "${tmp_dir}"
    git config user.name "${GIT_AUTHOR_NAME:-local-deepseek}"
    git config user.email "${GIT_AUTHOR_EMAIL:-local-deepseek@users.noreply.github.com}"
    rm -f .gitattributes .gitignore
    mkdir -p day reports api/day api/reports api
    cp "${ROOT_DIR}/${STATE_FILE}" "${STATE_FILE}"
    cp "${ROOT_DIR}/${STATE_FILE}" api/state.sqlite

    if [ -d "${ROOT_DIR}/${OUTPUT_DIR}/day" ]; then
      cp -R "${ROOT_DIR}/${OUTPUT_DIR}/day/." day/
    fi
    if [ -d "${ROOT_DIR}/${OUTPUT_DIR}/reports" ]; then
      cp -R "${ROOT_DIR}/${OUTPUT_DIR}/reports/." reports/
    fi
    if [ -d "${ROOT_DIR}/${OUTPUT_DIR}/api/day" ]; then
      cp -R "${ROOT_DIR}/${OUTPUT_DIR}/api/day/." api/day/
    fi
    if [ -d "${ROOT_DIR}/${OUTPUT_DIR}/api/reports" ]; then
      cp -R "${ROOT_DIR}/${OUTPUT_DIR}/api/reports/." api/reports/
    fi
    cp "${ROOT_DIR}/${OUTPUT_DIR}/api/daily.json" api/daily.json
    cp "${ROOT_DIR}/${OUTPUT_DIR}/api/llm_scores.json" api/llm_scores.json 2>/dev/null || true
    cp "${ROOT_DIR}/${OUTPUT_DIR}/api/translations_zh.json" api/translations_zh.json 2>/dev/null || true

    git add "${STATE_FILE}" day/ reports/ api/
    if git diff --cached --quiet; then
      log "No state changes to push."
      exit 0
    fi

    git commit -m "chore(state): local DeepSeek run ${TARGET_DATE} [skip ci]"
    git push --force-with-lease origin "HEAD:refs/heads/${STATE_BRANCH}"
  )
}

log "Target date: ${TARGET_DATE}; run mode: ${RUN_MODE}; report mode: ${REPORT_MODE}"
log "DeepSeek model: ${OPENAI_MODEL}; base URL: ${OPENAI_BASE_URL}"

if [ "${RESTORE_STATE}" = "true" ]; then
  restore_state
fi

case "${RUN_MODE}" in
  run)
    run_digest
    ;;
  backfill)
    run_backfill
    ;;
esac

run_reports

if [ "${BUILD_FRONTEND}" = "true" ]; then
  build_frontend
fi

prepare_archive_output

if [ "${PUSH_STATE}" = "true" ]; then
  push_state
fi

if [ "${DEPLOY}" = "true" ]; then
  log "Triggering deploy-from-state workflow"
  ./scripts/deploy-from-state.sh --repo "${REPO}" --state-ref "${STATE_BRANCH}"
fi

log "Done. Latest local payload: ${OUTPUT_DIR}/api/daily.json"
