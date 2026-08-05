#!/usr/bin/env bash
# Translate the host-local cron clock into exact UTC job times.
set -euo pipefail

ROOT_DIR="${NANO_ROOT:-${HOME}/daily-paper-report}"
RUNNER="${ROOT_DIR}/app/scripts/server-run-user.sh"
UTC_TIME="$(date -u +%H%M)"
UTC_WEEKDAY="$(date -u +%u)"
UTC_DAY="$(date -u +%d)"

if test "${UTC_TIME}" = "0000"; then
  exec "${RUNNER}" daily
fi
if test "${UTC_TIME}" = "0030" && test "${UTC_WEEKDAY}" = "1"; then
  exec "${RUNNER}" weekly
fi
if test "${UTC_TIME}" = "0100" && test "${UTC_DAY}" = "01"; then
  exec "${RUNNER}" monthly
fi
