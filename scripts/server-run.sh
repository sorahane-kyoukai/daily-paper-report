#!/usr/bin/env bash
# Run one Nano job under a shared lock, then atomically publish successful output.
set -euo pipefail

MODE="${1:-daily}"
ROOT_DIR="${APP_DIR:-/srv/daily-paper-report/app}"
DATA_DIR="${DATA_DIR:-/srv/daily-paper-report/data}"
PUBLIC_DIR="${PUBLIC_DIR:-/srv/daily-paper-report/public}"
CACHE_DIR="${CACHE_DIR:-/srv/daily-paper-report/cache}"
ENV_FILE="${ENV_FILE:-/etc/daily-paper-report/daily-paper-report.env}"
LOCK_FILE="${LOCK_FILE:-/run/lock/daily-paper-report.lock}"
export DATA_DIR PUBLIC_DIR CACHE_DIR ENV_FILE
cd "${ROOT_DIR}"

exec 9>"${LOCK_FILE}"
flock -w 21600 9 || { echo "Could not acquire pipeline lock" >&2; exit 1; }

mkdir -p "${DATA_DIR}" "${PUBLIC_DIR}" "${CACHE_DIR}/fulltext"
TARGET_DATE="$(date -u +%F)"
COMMON=(--out /public --tz UTC --json-logs)

case "${MODE}" in
  daily)
    docker compose run --rm digest run \
      --config /app/config/sources.yaml \
      --entities /app/config/entities.yaml \
      --topics /app/config/topics.yaml \
      --state /data/state.sqlite \
      "${COMMON[@]}" --date "${TARGET_DATE}" --lookback 24
    ;;
  weekly)
    REPORT_DATE="$(date -u -d yesterday +%F)"
    docker compose run --rm digest report --type weekly \
      "${COMMON[@]}" --date "${REPORT_DATE}" --limit 100 --archive-lookahead-days 1
    ;;
  monthly)
    docker compose run --rm digest report --type monthly \
      "${COMMON[@]}" --date "${TARGET_DATE}" --previous-month \
      --limit 100 --archive-lookahead-days 1
    ;;
  *) echo "Usage: $0 daily|weekly|monthly" >&2; exit 2 ;;
esac

docker compose run --rm --entrypoint sh digest -c \
  'cp /opt/frontend-dist/index.html /public/index.html && mkdir -p /public/assets && cp -R /opt/frontend-dist/assets/. /public/assets/'
python3 "${ROOT_DIR}/scripts/prepare-public.py" "${PUBLIC_DIR}"
python3 "${ROOT_DIR}/scripts/backup-state.py" \
  "${DATA_DIR}/state.sqlite" "${DATA_DIR%/data}/backups"
"${ROOT_DIR}/scripts/publish-state.sh"
"${ROOT_DIR}/scripts/publish-pages.sh"
