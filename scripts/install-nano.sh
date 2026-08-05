#!/usr/bin/env bash
# Install the checked-out project on the Nano. Run with sudo from the repository.
set -euo pipefail

test "$(id -u)" -eq 0 || { echo "Run with sudo" >&2; exit 1; }
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="/srv/daily-paper-report"
APP_DIR="${APP_ROOT}/app"
SERVICE_USER="${SERVICE_USER:-dennysora-nano}"

install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${APP_ROOT}"
install -d -o 10001 -g 10001 \
  "${APP_ROOT}/data" "${APP_ROOT}/public" "${APP_ROOT}/cache/fulltext"
install -d -o root -g root "${APP_ROOT}/backups"
install -d -m 700 /etc/daily-paper-report

if ! test -f /etc/daily-paper-report/github_deploy_key; then
  ssh-keygen -q -t ed25519 -N '' \
    -C daily-paper-report-nano \
    -f /etc/daily-paper-report/github_deploy_key
  chmod 600 /etc/daily-paper-report/github_deploy_key
  echo "Register this write deploy key for the repository:" >&2
  cat /etc/daily-paper-report/github_deploy_key.pub >&2
fi

if test "${SOURCE_DIR}" != "${APP_DIR}"; then
  install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${APP_DIR}"
  cp -R "${SOURCE_DIR}/." "${APP_DIR}/"
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
fi

if ! test -f /etc/daily-paper-report/daily-paper-report.env; then
  install -m 600 "${APP_DIR}/.env.example" \
    /etc/daily-paper-report/daily-paper-report.env
  echo "Set DEEPSEEK_API_KEY in /etc/daily-paper-report/daily-paper-report.env" >&2
fi

install -m 644 "${APP_DIR}/deploy/systemd/daily-paper-report@.service" /etc/systemd/system/
install -m 644 "${APP_DIR}/deploy/systemd/"*.timer /etc/systemd/system/
cd "${APP_DIR}"
ENV_FILE=/etc/daily-paper-report/daily-paper-report.env \
DATA_DIR="${APP_ROOT}/data" PUBLIC_DIR="${APP_ROOT}/public" \
CACHE_DIR="${APP_ROOT}/cache" docker compose build
systemctl daemon-reload
systemctl enable --now daily-paper-report-daily.timer \
  daily-paper-report-weekly.timer daily-paper-report-monthly.timer
systemctl list-timers 'daily-paper-report-*' --no-pager
