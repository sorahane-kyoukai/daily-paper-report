# Nano recovery guide

Stop timers before changing canonical state:

```bash
sudo systemctl stop daily-paper-report-daily.timer \
  daily-paper-report-weekly.timer daily-paper-report-monthly.timer
```

Restore the newest local SQLite backup, verify it, then run a digest:

```bash
cd /srv/daily-paper-report
gzip -dc backups/state-YYYYMMDDTHHMMSSZ.sqlite.gz > data/state.sqlite.restore
sqlite3 data/state.sqlite.restore 'PRAGMA integrity_check;'
mv data/state.sqlite.restore data/state.sqlite
sudo systemctl start daily-paper-report@daily.service
```

If no local backup exists, retrieve `state.sqlite` from the repository's `state` branch.
Never restore files from `gh-pages` into the private full-text cache. To republish an already
validated local payload without fetching data:

```bash
cd /srv/daily-paper-report/app
PUBLIC_DIR=/srv/daily-paper-report/public ./scripts/publish-pages.sh
```

After verification, re-enable all timers:

```bash
sudo systemctl enable --now daily-paper-report-daily.timer \
  daily-paper-report-weekly.timer daily-paper-report-monthly.timer
```
