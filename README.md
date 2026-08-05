# Daily Paper Report

Daily Paper Report collects AI research and technical news, deduplicates stories,
extracts complete paper text, scores papers with DeepSeek, writes Traditional Chinese
research guides, and publishes a static Vue site.

## Runtime architecture

- The data pipeline runs on the Nano server in an ARM64 Docker container.
- `deepseek-v4-flash` is the only LLM and uses its 1M-token context window.
- Full paper text is cached only on the Nano; it is never published or pushed to GitHub.
- The Nano pushes validated static output to `gh-pages`; GitHub Pages serves
  `paper.sorahane-kyoukai.org` from that branch.
- SQLite and small JSON caches are backed up to the `state` branch.
- There are no repository workflow files. GitHub's internal Pages publication run is
  still expected when `gh-pages` changes.

## Local development

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js 22, and pnpm.

```bash
cp .env.example .env
# Set DEEPSEEK_API_KEY in .env
uv sync --frozen
uv run pytest
uv run ruff check .
uv run mypy src
cd frontend && pnpm install --frozen-lockfile && pnpm run build-only
```

Run one UTC digest:

```bash
uv run python main.py run \
  --config config/sources.yaml \
  --entities config/entities.yaml \
  --topics config/topics.yaml \
  --state runtime/data/state.sqlite \
  --out runtime/public \
  --tz UTC \
  --date "$(date -u +%F)" \
  --lookback 24
```

The score cache is versioned. Each entry contains the final score, six scorecard
components, confidence, evidence, matched topics, model/prompt versions, and full-text
provenance hash/status. Translation cache entries are invalidated when the paper content
or prompt changes.

## Nano installation and operation

The target host is `dennysora-nano@192.168.30.100:19845`. From a checked-out copy:

```bash
sudo ./scripts/install-nano.sh
sudoedit /etc/daily-paper-report/daily-paper-report.env
sudo systemctl start daily-paper-report@daily.service
journalctl -u daily-paper-report@daily.service -f
```

If the SSH account cannot run passwordless sudo, place the checkout and a
prebuilt `frontend/dist` under `~/daily-paper-report`, then run
`scripts/install-nano-user.sh`. This rootless mode uses user cron and a
uv-managed Python 3.13. Its dispatcher wakes every 30 minutes but starts work
only at the exact UTC times below.

Timers use UTC and a shared six-hour lock:

- Daily: every day at 00:00
- Weekly: Monday at 00:30, covering the previous ISO week
- Monthly: day 1 at 01:00, covering the previous month

Publishing is performed by `scripts/publish-pages.sh`; state snapshots use
`scripts/publish-state.sh`. Both refuse invalid inputs before pushing. The Nano requires a
repository-specific SSH deploy key with write access; personal SSH keys must not be copied.

## Storage

Default Nano paths:

```text
/srv/daily-paper-report/app       checked-out application
/srv/daily-paper-report/data      canonical SQLite state
/srv/daily-paper-report/public    generated static site
/srv/daily-paper-report/cache     private extracted full text
/srv/daily-paper-report/backups   rotating SQLite backups
```

See [the recovery guide](docs/RESET-GUIDE.md) for restore and republish procedures.
