# RESET GUIDE

目前資料 CICD 保留三個操作：

1. 重跑指定日期（`daily-digest.yaml`）
2. 刪除全部資料（`reset-site.yaml`）
3. 依日期區間逐日補跑（`backfill-date-range.yaml`）

## 1) 重跑指定日期

只會重建你指定的那一天資料（依 `Asia/Taipei` 當地日界線 00:00~24:00），不會跑完整日常 pipeline。

```bash
gh workflow run daily-digest.yaml \
  --repo DennySORA/Daily-Paper-Report \
  --ref main \
  -f target_date=2026-03-05
```

## 2) 刪除全部資料

會刪除 state branch，並部署空站（`archive_dates` 清空、各區塊為空陣列）。

```bash
gh workflow run reset-site.yaml \
  --repo DennySORA/Daily-Paper-Report \
  --ref main \
  -f confirm_reset=RESET
```

## 3) 依日期區間逐日補跑

會先依起始日自動放大 `lookback` 收集足夠資料，再按照日期順序逐天 backfill。前一天做完才會接下一天。

```bash
gh workflow run backfill-date-range.yaml \
  --repo DennySORA/Daily-Paper-Report \
  --ref main \
  -f start_date=2026-03-03 \
  -f end_date=2026-03-05
```

## 驗證

```bash
curl -s https://paper.sorahane-kyoukai.org/api/daily.json | jq '{
  run_date,
  archive_dates_count: (.archive_dates | length),
  papers_count: (.papers | length)
}'
```

## 常見問題

### Q: 重跑指定日會不會影響其他日期？
不會。流程只覆寫 `api/day/<target_date>.json`（及對應 day HTML），其他日期保留。

### Q: 什麼時候會更新首頁 `api/daily.json`？
重跑指定日會保留既有 `daily.json` 主體，只同步 `archive_dates` 清單。

### Q: 為什麼不用 `backfill_days`？
此參數已移除。現在只支援精準重跑單日，避免誤覆蓋與不必要計算。
