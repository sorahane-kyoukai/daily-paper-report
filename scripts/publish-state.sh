#!/usr/bin/env bash
# Push a recoverable state snapshot; full text and source PDFs are never included.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${DATA_DIR:-${ROOT_DIR}/runtime/data}"
PUBLIC_DIR="${PUBLIC_DIR:-${ROOT_DIR}/runtime/public}"
REMOTE_URL="${REMOTE_URL:-git@github.com:sorahane-kyoukai/daily-paper-report.git}"
STATE_BRANCH="${STATE_BRANCH:-state}"
STATE_FILE="${DATA_DIR}/state.sqlite"
DEPLOY_KEY="${DEPLOY_KEY:-/etc/daily-paper-report/github_deploy_key}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if test -f "${DEPLOY_KEY}"; then
  export GIT_SSH_COMMAND="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
fi

test -f "${STATE_FILE}" || { echo "Missing ${STATE_FILE}" >&2; exit 1; }
"${PYTHON_BIN}" - "${STATE_FILE}" <<'PY'
import sqlite3
import sys
db = sqlite3.connect(sys.argv[1])
result = db.execute("PRAGMA integrity_check").fetchone()
db.close()
if not result or result[0] != "ok":
    raise SystemExit("SQLite integrity_check failed")
PY

TEMP_DIR="$(mktemp -d)"
cleanup() { rm -rf -- "${TEMP_DIR}"; }
trap cleanup EXIT
git -C "${TEMP_DIR}" init >/dev/null
git -C "${TEMP_DIR}" remote add origin "${REMOTE_URL}"
if git -C "${TEMP_DIR}" fetch --depth=1 origin "${STATE_BRANCH}" >/dev/null 2>&1; then
  git -C "${TEMP_DIR}" checkout -B "${STATE_BRANCH}" FETCH_HEAD >/dev/null
else
  git -C "${TEMP_DIR}" checkout --orphan "${STATE_BRANCH}" >/dev/null
fi
find "${TEMP_DIR}" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf -- {} +
mkdir -p "${TEMP_DIR}/api"
cp "${STATE_FILE}" "${TEMP_DIR}/state.sqlite"
for path in daily.json llm_scores.json translations_zh.json; do
  test ! -f "${PUBLIC_DIR}/api/${path}" || cp "${PUBLIC_DIR}/api/${path}" "${TEMP_DIR}/api/${path}"
done
for path in day reports; do
  test ! -d "${PUBLIC_DIR}/api/${path}" || cp -R "${PUBLIC_DIR}/api/${path}" "${TEMP_DIR}/api/${path}"
done
git -C "${TEMP_DIR}" add -A
if git -C "${TEMP_DIR}" diff --cached --quiet; then exit 0; fi
git -C "${TEMP_DIR}" config user.name "daily-paper-report-nano"
git -C "${TEMP_DIR}" config user.email "daily-paper-report-nano@users.noreply.github.com"
git -C "${TEMP_DIR}" commit -m "chore(state): snapshot $(date -u +%FT%TZ)" >/dev/null
git -C "${TEMP_DIR}" push --force-with-lease origin "HEAD:${STATE_BRANCH}"
