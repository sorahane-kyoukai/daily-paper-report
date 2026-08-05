#!/usr/bin/env bash
# Publish a validated, prebuilt static payload to the gh-pages branch.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_DIR="${PUBLIC_DIR:-${ROOT_DIR}/runtime/public}"
REMOTE_URL="${REMOTE_URL:-git@github.com:sorahane-kyoukai/daily-paper-report.git}"
PAGES_BRANCH="${PAGES_BRANCH:-gh-pages}"
DOMAIN="${PAGES_DOMAIN:-paper.sorahane-kyoukai.org}"
DEPLOY_KEY="${DEPLOY_KEY:-/etc/daily-paper-report/github_deploy_key}"
if test -f "${DEPLOY_KEY}"; then
  export GIT_SSH_COMMAND="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
fi

python3 - "${PUBLIC_DIR}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
required = [root / "index.html", root / "api" / "daily.json"]
missing = [str(path) for path in required if not path.is_file()]
if missing:
    raise SystemExit(f"Refusing to publish; missing: {', '.join(missing)}")
json.loads((root / "api" / "daily.json").read_text(encoding="utf-8"))
for forbidden in (".env", "state.sqlite", "fulltext", "backups"):
    if any(path.name == forbidden for path in root.rglob("*")):
        raise SystemExit(f"Refusing to publish forbidden artifact: {forbidden}")
PY

TEMP_DIR="$(mktemp -d)"
cleanup() { rm -rf -- "${TEMP_DIR}"; }
trap cleanup EXIT

git -C "${TEMP_DIR}" init --initial-branch="${PAGES_BRANCH}" >/dev/null
git -C "${TEMP_DIR}" remote add origin "${REMOTE_URL}"
if git -C "${TEMP_DIR}" fetch --depth=1 origin "${PAGES_BRANCH}" >/dev/null 2>&1; then
  git -C "${TEMP_DIR}" checkout -B "${PAGES_BRANCH}" FETCH_HEAD >/dev/null
else
  git -C "${TEMP_DIR}" checkout --orphan "${PAGES_BRANCH}" >/dev/null
fi

find "${TEMP_DIR}" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf -- {} +
cp -R "${PUBLIC_DIR}/." "${TEMP_DIR}/"
: > "${TEMP_DIR}/.nojekyll"
printf '%s\n' "${DOMAIN}" > "${TEMP_DIR}/CNAME"

git -C "${TEMP_DIR}" add -A
if git -C "${TEMP_DIR}" diff --cached --quiet; then
  echo "Pages payload unchanged."
  exit 0
fi
git -C "${TEMP_DIR}" config user.name "daily-paper-report-nano"
git -C "${TEMP_DIR}" config user.email "daily-paper-report-nano@users.noreply.github.com"
git -C "${TEMP_DIR}" commit -m "chore(pages): publish $(date -u +%F)" >/dev/null
git -C "${TEMP_DIR}" push --force-with-lease origin "HEAD:${PAGES_BRANCH}"
