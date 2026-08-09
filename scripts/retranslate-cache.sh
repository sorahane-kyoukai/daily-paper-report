#!/usr/bin/env bash
# Clear the translation cache and rerun backfill so every visible story is
# retranslated with the current Traditional Chinese prompt.
set -euo pipefail

START_DATE="${1:-}"
END_DATE="${2:-}"
DRY_RUN="${DRY_RUN:-0}"

ROOT_DIR="${NANO_ROOT:-${HOME}/daily-paper-report}"
APP_DIR="${ROOT_DIR}/app"
DATA_DIR="${ROOT_DIR}/data"
PUBLIC_DIR="${ROOT_DIR}/public"
CACHE_DIR="${ROOT_DIR}/cache"
PYTHON_BIN="${APP_DIR}/.venv/bin/python"
DEPLOY_KEY="${ROOT_DIR}/github_deploy_key"
TRANSLATION_CACHE="${PUBLIC_DIR}/api/translations_zh.json"
export DATA_DIR PUBLIC_DIR CACHE_DIR PYTHON_BIN DEPLOY_KEY
export FULLTEXT_CACHE_DIR="${CACHE_DIR}/fulltext"
cd "${APP_DIR}"

# --- Parse date range --------------------------------------------------------
if [[ -z "${START_DATE}" ]]; then
  START_DATE="$(date -u -d '10 days ago' +%F)"
fi
if [[ -z "${END_DATE}" ]]; then
  END_DATE="$(date -u +%F)"
fi

if [[ ! "${START_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || \
   [[ ! "${END_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Usage: $0 [YYYY-MM-DD YYYY-MM-DD]" >&2
  echo "  Defaults: 10 days ago .. today (UTC)" >&2
  exit 2
fi

echo "=== Retranslate range: ${START_DATE} .. ${END_DATE} ==="
echo ""

# --- Step 1: Clear the translation cache ------------------------------------
if [[ "${DRY_RUN}" == "0" ]]; then
  if test -f "${TRANSLATION_CACHE}"; then
    echo "[1/3] Removing translation cache: ${TRANSLATION_CACHE}"
    rm -f "${TRANSLATION_CACHE}"
    echo "      Deleted."
  else
    echo "[1/3] No translation cache found at ${TRANSLATION_CACHE} — nothing to delete."
  fi
else
  echo "[1/3] DRY-RUN: would remove ${TRANSLATION_CACHE}"
fi

# --- Step 2: Lock and backfill each day --------------------------------------
exec 9>"${ROOT_DIR}/pipeline.lock"
if ! flock -n 9; then
  echo "Pipeline lock is held — another job may be running. Aborting." >&2
  exit 1
fi

echo "[2/3] Backfilling daily archives (this triggers retranslation)..."

CURRENT="${START_DATE}"
COUNT=0
FAILED=0
while [[ "${CURRENT}" < "${END_DATE}" || "${CURRENT}" == "${END_DATE}" ]]; do
  COUNT=$((COUNT + 1))
  echo "      [${COUNT}] ${CURRENT} ..."

  if [[ "${DRY_RUN}" == "0" ]]; then
    if "${PYTHON_BIN}" main.py backfill \
      --config config/sources.yaml --entities config/entities.yaml \
      --topics config/topics.yaml --state "${DATA_DIR}/state.sqlite" \
      --out "${PUBLIC_DIR}" --tz UTC --date "${CURRENT}" \
      --overwrite-existing --json-logs 2>&1 | tail -1; then
      :
    else
      FAILED=$((FAILED + 1))
      echo "      ⚠️  Backfill failed for ${CURRENT} (continuing)"
    fi
  else
    echo "      DRY-RUN: would backfill ${CURRENT}"
  fi

  CURRENT="$(date -u -d "${CURRENT} +1 day" +%F)"
done

# --- Step 3: Rebuild daily.json from the fresh day archives ------------------
echo "[3/3] Rebuilding daily.json..."
if [[ "${DRY_RUN}" == "0" ]]; then
  # Re-run today's daily to regenerate daily.json and day page
  TARGET_DATE="$(date -u +%F)"
  "${PYTHON_BIN}" main.py backfill \
    --config config/sources.yaml --entities config/entities.yaml \
    --topics config/topics.yaml --state "${DATA_DIR}/state.sqlite" \
    --out "${PUBLIC_DIR}" --tz UTC --date "${TARGET_DATE}" \
    --overwrite-existing --json-logs 2>&1 | tail -3
fi

echo ""
echo "=== Done: backfilled ${COUNT} days, ${FAILED} failures ==="

# --- Show a sample of the new translations -----------------------------------
if [[ "${DRY_RUN}" == "0" ]] && test -f "${TRANSLATION_CACHE}"; then
  ENTRY_COUNT="$("${PYTHON_BIN}" -c "
import json
data = json.load(open('${TRANSLATION_CACHE}'))
print(len(data))
")"
  echo "Translation cache now has ${ENTRY_COUNT} entries."
  echo ""
  echo "=== Sample (first 2 titles) ==="
  "${PYTHON_BIN}" -c "
import json
data = json.load(open('${TRANSLATION_CACHE}'))
for i, (sid, entry) in enumerate(data.items()):
    if i >= 2: break
    print(f\"  {entry.get('title_zh', 'N/A')}\")
"
fi
