#!/usr/bin/env bash
# Rootless Nano runner used when sudo is unavailable.
set -euo pipefail

MODE="${1:-daily}"
ROOT_DIR="${NANO_ROOT:-${HOME}/daily-paper-report}"
APP_DIR="${ROOT_DIR}/app"
DATA_DIR="${ROOT_DIR}/data"
PUBLIC_DIR="${ROOT_DIR}/public"
CACHE_DIR="${ROOT_DIR}/cache"
PYTHON_BIN="${APP_DIR}/.venv/bin/python"
DEPLOY_KEY="${ROOT_DIR}/github_deploy_key"
export DATA_DIR PUBLIC_DIR CACHE_DIR PYTHON_BIN DEPLOY_KEY
cd "${APP_DIR}"

exec 9>"${ROOT_DIR}/pipeline.lock"
flock -w 21600 9 || { echo "Could not acquire pipeline lock" >&2; exit 1; }

mkdir -p "${DATA_DIR}" "${PUBLIC_DIR}" "${CACHE_DIR}/fulltext"
TARGET_DATE="$(date -u +%F)"
COMMON=(--out "${PUBLIC_DIR}" --tz UTC --json-logs)

case "${MODE}" in
  daily)
    FULLTEXT_CACHE_DIR="${CACHE_DIR}/fulltext" "${PYTHON_BIN}" main.py run \
      --config config/sources.yaml --entities config/entities.yaml \
      --topics config/topics.yaml --state "${DATA_DIR}/state.sqlite" \
      "${COMMON[@]}" --date "${TARGET_DATE}" --lookback 24
    ;;
  weekly)
    REPORT_DATE="$(date -u -d yesterday +%F)"
    "${PYTHON_BIN}" main.py report --type weekly "${COMMON[@]}" \
      --date "${REPORT_DATE}" --limit 100 --archive-lookahead-days 1
    ;;
  monthly)
    "${PYTHON_BIN}" main.py report --type monthly "${COMMON[@]}" \
      --date "${TARGET_DATE}" --previous-month \
      --limit 100 --archive-lookahead-days 1
    ;;
  *) echo "Usage: $0 daily|weekly|monthly" >&2; exit 2 ;;
esac

cp "${ROOT_DIR}/frontend-dist/index.html" "${PUBLIC_DIR}/index.html"
mkdir -p "${PUBLIC_DIR}/assets"
cp -R "${ROOT_DIR}/frontend-dist/assets/." "${PUBLIC_DIR}/assets/"
"${PYTHON_BIN}" scripts/prepare-public.py "${PUBLIC_DIR}"
"${PYTHON_BIN}" scripts/backup-state.py \
  "${DATA_DIR}/state.sqlite" "${ROOT_DIR}/backups"
scripts/publish-state.sh
scripts/publish-pages.sh
