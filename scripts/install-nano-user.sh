#!/usr/bin/env bash
# Install a rootless Nano runtime and UTC-aware cron dispatcher.
set -euo pipefail

ROOT_DIR="${NANO_ROOT:-${HOME}/daily-paper-report}"
APP_DIR="${ROOT_DIR}/app"
UV_BIN="${ROOT_DIR}/bin/uv"
test -f "${APP_DIR}/uv.lock" || { echo "Missing checkout at ${APP_DIR}" >&2; exit 1; }
test -f "${ROOT_DIR}/frontend-dist/index.html" || { echo "Missing frontend-dist" >&2; exit 1; }

mkdir -p "${ROOT_DIR}/bin" "${ROOT_DIR}/python" "${ROOT_DIR}/data" \
  "${ROOT_DIR}/public" "${ROOT_DIR}/cache/fulltext" "${ROOT_DIR}/backups" \
  "${ROOT_DIR}/logs"
if ! test -x "${UV_BIN}"; then
  curl -LsSf https://astral.sh/uv/install.sh | \
    env UV_UNMANAGED_INSTALL="${ROOT_DIR}/bin" sh
fi
export UV_PYTHON_INSTALL_DIR="${ROOT_DIR}/python"
"${UV_BIN}" python install 3.13
cd "${APP_DIR}"
"${UV_BIN}" sync --frozen --no-dev

if ! test -f "${ROOT_DIR}/github_deploy_key"; then
  ssh-keygen -q -t ed25519 -N '' -C daily-paper-report-nano \
    -f "${ROOT_DIR}/github_deploy_key"
fi
chmod 600 "${ROOT_DIR}/github_deploy_key"
chmod +x scripts/server-run-user.sh scripts/cron-dispatch.sh

CRON_LINE="0,30 * * * * ${APP_DIR}/scripts/cron-dispatch.sh >>${ROOT_DIR}/logs/cron.log 2>&1"
{ crontab -l 2>/dev/null | grep -v 'daily-paper-report.*/cron-dispatch.sh' || true; echo "${CRON_LINE}"; } | crontab -
echo "Installed rootless runtime in ${ROOT_DIR}"
crontab -l | grep 'cron-dispatch.sh'
