#!/bin/bash
set -euo pipefail

# Backfill the past 31 days using DeepSeek (reads keys from .env)
BASE="/home/dennysora-wsl/Programming/Python/Daily-Paper-Report"

echo "=== Starting 31-day backfill at $(date) ==="

for d in $(seq 0 30); do
  date=$(date -d "2026-06-08 -$d days" +%Y-%m-%d)
  echo "[$(date +%H:%M:%S)] Backfilling $date..."
  cd "$BASE"
  uv run python main.py backfill \
    --config tests/fixtures/config/sources.yaml \
    --entities tests/fixtures/config/entities.yaml \
    --topics tests/fixtures/config/topics.yaml \
    --state state.sqlite \
    --out public \
    --tz Asia/Taipei \
    --date "$date" \
    --overwrite-existing \
    --json-logs 2>&1 | grep -E '(day_archive_generated|day_archive_skipped|backfill_complete|stories_count|translation_phase|llm_evaluating|llm_all_cached|llm_phase_complete)' || true
done

echo "=== Backfill complete at $(date) ==="

# Generate fresh daily.json from latest day
echo "=== Generating daily.json ==="
cp "$BASE/public/api/day/2026-06-08.json" "$BASE/public/api/daily.json"

# Update archive_dates
DATES=$(find "$BASE/public/api/day" -maxdepth 1 -name "*.json" -printf "%f\n" | sed 's/\.json$//' | sort -r)
DATES_JSON=$(echo "$DATES" | jq -R -s 'split("\n") | map(select(length > 0))')
jq --argjson dates "$DATES_JSON" '.archive_dates = $dates' \
  "$BASE/public/api/daily.json" > "$BASE/public/api/daily.json.tmp"
mv "$BASE/public/api/daily.json.tmp" "$BASE/public/api/daily.json"

echo "=== daily.json updated with $(echo "$DATES" | wc -l) archive dates ==="
