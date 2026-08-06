#!/usr/bin/env bash
# Rebuild an inclusive UTC date range and every intersecting weekly/monthly report.
set -euo pipefail

START_DATE="${1:-}"
END_DATE="${2:-}"
if [[ ! "${START_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || \
   [[ ! "${END_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Usage: $0 YYYY-MM-DD YYYY-MM-DD" >&2
  exit 2
fi
if [[ "${START_DATE}" > "${END_DATE}" ]]; then
  echo "Start date must not be after end date" >&2
  exit 2
fi
if [[ "${END_DATE}" > "$(date -u +%F)" ]]; then
  echo "Cannot rerun a future date" >&2
  exit 2
fi

ROOT_DIR="${NANO_ROOT:-${HOME}/daily-paper-report}"
APP_DIR="${ROOT_DIR}/app"
DATA_DIR="${ROOT_DIR}/data"
PUBLIC_DIR="${ROOT_DIR}/public"
CACHE_DIR="${ROOT_DIR}/cache"
PYTHON_BIN="${APP_DIR}/.venv/bin/python"
DEPLOY_KEY="${ROOT_DIR}/github_deploy_key"
RANGE_ID="${START_DATE}_${END_DATE}"
STATUS_FILE="${ROOT_DIR}/logs/rerun-${RANGE_ID}.status"
export DATA_DIR PUBLIC_DIR CACHE_DIR PYTHON_BIN DEPLOY_KEY
export FULLTEXT_CACHE_DIR="${CACHE_DIR}/fulltext"
cd "${APP_DIR}"

exec 9>"${ROOT_DIR}/pipeline.lock"
flock -w 21600 9 || { echo "Could not acquire pipeline lock" >&2; exit 1; }
trap 'status=$?; printf "failed exit=%s at=%s\n" "$status" "$(date -u +%FT%TZ)" >"${STATUS_FILE}"; exit "$status"' ERR
printf 'running started=%s model=deepseek-v4-flash range=%s..%s\n' \
  "$(date -u +%FT%TZ)" "${START_DATE}" "${END_DATE}" >"${STATUS_FILE}"

CURRENT="${START_DATE}"
while [[ "${CURRENT}" < "${END_DATE}" || "${CURRENT}" == "${END_DATE}" ]]; do
  echo "rerun_daily date=${CURRENT} model=deepseek-v4-flash"
  "${PYTHON_BIN}" main.py backfill \
    --config config/sources.yaml --entities config/entities.yaml \
    --topics config/topics.yaml --state "${DATA_DIR}/state.sqlite" \
    --out "${PUBLIC_DIR}" --tz UTC --date "${CURRENT}" \
    --overwrite-existing --json-logs
  CURRENT="$(date -u -d "${CURRENT} +1 day" +%F)"
done

while IFS= read -r PERIOD; do
  echo "rerun_weekly period=${PERIOD} model=deepseek-v4-flash"
  "${PYTHON_BIN}" main.py report --type weekly --out "${PUBLIC_DIR}" \
    --tz UTC --period "${PERIOD}" --limit 100 --archive-lookahead-days 1 \
    --ai-metadata --json-logs
done < <("${PYTHON_BIN}" - "${START_DATE}" "${END_DATE}" <<'PY'
from datetime import date, timedelta
import sys

start = date.fromisoformat(sys.argv[1])
end = date.fromisoformat(sys.argv[2])
periods = set()
current = start
while current <= end:
    year, week, _ = current.isocalendar()
    periods.add(f"{year}-W{week:02d}")
    current += timedelta(days=1)
print("\n".join(sorted(periods)))
PY
)

while IFS= read -r PERIOD; do
  echo "rerun_monthly period=${PERIOD} model=deepseek-v4-flash"
  "${PYTHON_BIN}" main.py report --type monthly --out "${PUBLIC_DIR}" \
    --tz UTC --period "${PERIOD}" --limit 100 --archive-lookahead-days 1 \
    --ai-metadata --json-logs
done < <("${PYTHON_BIN}" - "${START_DATE}" "${END_DATE}" <<'PY'
from datetime import date
import sys

start = date.fromisoformat(sys.argv[1])
end = date.fromisoformat(sys.argv[2])
current = start.replace(day=1)
periods = []
while current <= end:
    periods.append(current.strftime("%Y-%m"))
    current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
print("\n".join(periods))
PY
)

cp "${ROOT_DIR}/frontend-dist/index.html" "${PUBLIC_DIR}/index.html"
mkdir -p "${PUBLIC_DIR}/assets"
cp -R "${ROOT_DIR}/frontend-dist/assets/." "${PUBLIC_DIR}/assets/"
"${PYTHON_BIN}" scripts/prepare-public.py "${PUBLIC_DIR}"
"${PYTHON_BIN}" scripts/backup-state.py \
  "${DATA_DIR}/state.sqlite" "${ROOT_DIR}/backups"
scripts/publish-state.sh
scripts/publish-pages.sh
printf 'complete finished=%s model=deepseek-v4-flash range=%s..%s\n' \
  "$(date -u +%FT%TZ)" "${START_DATE}" "${END_DATE}" >"${STATUS_FILE}"
echo "rerun_complete range=${START_DATE}..${END_DATE}"
