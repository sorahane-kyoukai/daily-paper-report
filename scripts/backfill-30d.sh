#!/usr/bin/env bash
# Rebuild the latest 31 completed UTC dates through yesterday.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
END_DATE="$(date -u -d yesterday +%F)"
START_DATE="$(date -u -d "${END_DATE} -30 days" +%F)"
exec "${SCRIPT_DIR}/rerun-range-user.sh" "${START_DATE}" "${END_DATE}"
