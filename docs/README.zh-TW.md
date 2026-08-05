# Daily Paper Report

本專案在 Nano 上以 Docker 執行每日論文收集、全文擷取、DeepSeek 評分與繁中導讀，
再把通過驗證的靜態網站推送到 `gh-pages`，由 GitHub Pages 提供網站服務。

- 唯一 LLM：`deepseek-v4-flash`，使用 1M context。
- 論文全文只保存在 Nano，不推送或公開。
- 每日 00:00、週一 00:30、每月 1 日 01:00 UTC 執行。
- SQLite 與小型 JSON cache 備份至 `state` branch。
- repo 不含自訂 workflow；GitHub 只負責 Pages 平台發布。

完整開發、部署與操作命令請參考 [README](../README.md)，復原程序請參考
[RESET-GUIDE](RESET-GUIDE.md)。
