# Auto Paper Report

[English](../README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

一個自動化的研究論文與 AI 新聞摘要管線，從多個來源收集、去重、排名並生成每日報告。

## 功能特色

### 多來源資料收集

- **arXiv** - 透過 RSS 和 API 收集學術論文
- **RSS/Atom 訂閱** - 從任何 RSS 來源收集部落格文章和新聞
- **GitHub Releases** - 追蹤儲存庫的版本發布
- **Hugging Face** - 按組織追蹤模型發布
- **OpenReview** - 會議論文投稿
- **Papers With Code** - 熱門論文和實作
- **HTML 爬蟲** - 自訂 HTML 列表和設定檔提取

### 智慧處理

- **故事連結** - 自動連結跨來源的相關項目
- **去重複** - 識別並合併重複內容
- **實體匹配** - 將項目與追蹤的實體（公司、實驗室、研究人員）關聯
- **主題匹配** - 根據可配置的主題模式對內容進行分類

### 智慧排名

- **可配置評分** - 來源層級、時效性、實體相關性和主題命中的權重因子
- **配額管理** - 控制各區段的輸出分配
- **區段分配** - 將內容組織為 Top 5、模型發布、論文和雷達區段

### 靜態網站生成

- **響應式 HTML** - 行動裝置友善的每日摘要頁面
- **存檔頁面** - 歷史每日報告
- **來源狀態** - 所有來源的健康監控儀表板
- **JSON API** - 機器可讀的每日輸出

### 自動化與部署

- **GitHub Actions** - 自動化每日管線執行
- **GitHub Pages** - 零配置靜態網站部署
- **狀態持久化** - SQLite 資料庫支援增量更新
- **結構化日誌** - 帶有執行上下文的 JSON 日誌，便於觀測

## 架構

```
┌─────────────────────────────────────────────────────────────────┐
│                          配置檔案                                │
│              (sources.yaml, entities.yaml, topics.yaml)         │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                          收集器                                  │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│   │  arXiv  │ │   RSS   │ │ GitHub  │ │   HF    │ │  HTML   │  │
│   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        故事連結器                                │
│               (去重複、實體匹配、連結)                           │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                          排名器                                  │
│              (評分、配額過濾、區段分配)                          │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                          渲染器                                  │
│               (HTML 範本、JSON API、存檔)                       │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                           輸出                                   │
│                  (GitHub Pages / 靜態檔案)                      │
└─────────────────────────────────────────────────────────────────┘
```

## 快速開始

### 前置需求

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) 套件管理器

### 安裝

```bash
# 複製儲存庫
git clone https://github.com/DennySORA/auto_paper_report.git
cd auto_paper_report

# 安裝依賴
uv sync
```

### 配置

建立您的配置檔案：

**sources.yaml** - 定義資料來源
```yaml
version: "1.0"
defaults:
  max_items: 50

sources:
  - id: openai-blog
    name: OpenAI Blog
    url: https://openai.com/blog/rss.xml
    tier: 0
    method: rss_atom
    kind: blog
    timezone: America/Los_Angeles

  - id: arxiv-cs-ai
    name: arXiv cs.AI
    url: https://rss.arxiv.org/rss/cs.AI
    tier: 1
    method: rss_atom
    kind: paper
    timezone: UTC
```

**entities.yaml** - 定義追蹤實體
```yaml
version: "1.0"
entities:
  - id: openai
    name: OpenAI
    aliases: ["OpenAI", "open-ai"]
    prefer_links: [official, github, arxiv]
```

**topics.yaml** - 定義主題模式和評分
```yaml
version: "1.0"
topics:
  - id: llm
    name: Large Language Models
    patterns: ["LLM", "language model", "GPT", "transformer"]
```

### 執行管線

```bash
# 驗證配置
uv run python main.py validate \
    --config config/sources.yaml \
    --entities config/entities.yaml \
    --topics config/topics.yaml

# 執行完整管線
uv run python main.py run \
    --config config/sources.yaml \
    --entities config/entities.yaml \
    --topics config/topics.yaml \
    --state state.sqlite \
    --out public \
    --tz Asia/Taipei
```

### CLI 命令

| 命令 | 說明 |
|------|------|
| `run` | 執行完整摘要管線 |
| `validate` | 驗證配置檔案 |
| `render` | 從測試資料渲染靜態頁面 |
| `db-stats` | 顯示狀態資料庫統計 |

## 開發

### 執行測試

```bash
# 執行所有測試
uv run pytest

# 執行並產生覆蓋率報告
uv run pytest --cov=src --cov-report=html

# 執行特定測試檔案
uv run pytest tests/unit/test_ranker/test_scorer.py
```

### 程式碼品質

```bash
# 程式碼檢查
uv run ruff check .
uv run ruff check . --fix

# 格式化
uv run ruff format .

# 型別檢查
uv run mypy .

# 安全掃描
uv run bandit -r src/
```

## GitHub Actions 部署

本專案包含用於自動化每日執行的 GitHub Actions 工作流程：

1. Fork 此儲存庫
2. 在儲存庫設定中啟用 GitHub Pages
3. 配置密鑰（如果使用需要認證的 API）：
   - `HF_TOKEN` - Hugging Face API 令牌
   - `OPENREVIEW_TOKEN` - OpenReview API 令牌
4. 工作流程每天在台北時間 07:00 執行

## 專案結構

```
auto_paper_report/
├── src/
│   ├── cli/            # 命令列介面
│   ├── collectors/     # 資料來源收集器
│   │   ├── arxiv/      # arXiv API 和 RSS
│   │   ├── platform/   # GitHub, HuggingFace, OpenReview
│   │   └── html_profile/  # HTML 爬蟲設定檔
│   ├── config/         # 配置載入和結構描述
│   ├── evidence/       # 稽核軌跡擷取
│   ├── fetch/          # HTTP 客戶端與快取
│   ├── linker/         # 故事連結和去重複
│   ├── ranker/         # 評分和排名
│   ├── renderer/       # HTML/JSON 生成
│   ├── status/         # 來源健康監控
│   └── store/          # SQLite 狀態持久化
├── tests/
│   ├── unit/           # 單元測試
│   ├── integration/    # 整合測試
│   └── fixtures/       # 測試資料
├── public/             # 生成的靜態網站
└── .github/workflows/  # CI/CD 管線
```

## 配置參考

### 來源方法

| 方法 | 說明 |
|------|------|
| `rss_atom` | RSS/Atom 訂閱解析 |
| `arxiv_api` | arXiv API 查詢 |
| `github_releases` | GitHub 儲存庫版本發布 |
| `hf_org` | Hugging Face 組織模型 |
| `hf_daily_papers` | Hugging Face 每日論文 |
| `openreview_venue` | OpenReview 會議投稿 |
| `papers_with_code` | Papers With Code 熱門 |
| `html_list` | HTML 頁面連結提取 |

### 來源層級

| 層級 | 說明 |
|------|------|
| 0 | 主要來源（官方部落格、版本發布） |
| 1 | 次要來源（聚合器、新聞） |
| 2 | 第三方來源（社群媒體、論壇） |

## 授權

MIT 授權 - 詳見 [LICENSE](../LICENSE)。

## 貢獻

歡迎貢獻！請閱讀 [CLAUDE.md](../CLAUDE.md) 了解程式碼規範和開發標準。
