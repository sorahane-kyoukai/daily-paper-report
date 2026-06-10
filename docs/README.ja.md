# Auto Paper Report

[English](../README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

複数のソースから収集、重複排除、ランキング、日次レポートを生成する自動化された研究論文とAIニュースダイジェストパイプライン。

## 機能

### マルチソースデータ収集

- **arXiv** - RSSとAPIによる学術論文の収集
- **RSS/Atomフィード** - 任意のRSSソースからブログ記事やニュースを収集
- **GitHub Releases** - リポジトリのリリースを追跡
- **Hugging Face** - 組織別のモデルリリースを追跡
- **OpenReview** - 学会論文の投稿
- **Papers With Code** - トレンド論文と実装
- **HTMLスクレイピング** - カスタムHTMLリストとプロファイル抽出

### インテリジェント処理

- **ストーリーリンキング** - ソース間で関連アイテムを自動リンク
- **重複排除** - 重複コンテンツの識別と統合
- **エンティティマッチング** - アイテムを追跡エンティティ（企業、研究所、研究者）に関連付け
- **トピックマッチング** - 設定可能なトピックパターンでコンテンツを分類

### スマートランキング

- **設定可能なスコアリング** - ティア、鮮度、エンティティ関連性、トピックヒットの重み係数
- **クォータ管理** - セクション全体の出力配分を制御
- **セクション割り当て** - コンテンツをTop 5、モデルリリース、論文、レーダーセクションに整理

### 静的サイト生成

- **レスポンシブHTML** - モバイルフレンドリーな日次ダイジェストページ
- **アーカイブページ** - 過去の日次レポート
- **ソースステータス** - 全ソースのヘルスモニタリングダッシュボード
- **JSON API** - 機械可読な日次出力

### 自動化とデプロイ

- **GitHub Actions** - 日次パイプラインの自動実行
- **GitHub Pages** - ゼロコンフィグの静的サイトデプロイ
- **状態永続化** - インクリメンタル更新をサポートするSQLiteデータベース
- **構造化ロギング** - 可観測性のための実行コンテキスト付きJSONログ

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                          設定ファイル                            │
│              (sources.yaml, entities.yaml, topics.yaml)         │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         コレクター                               │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│   │  arXiv  │ │   RSS   │ │ GitHub  │ │   HF    │ │  HTML   │  │
│   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ストーリーリンカー                          │
│              (重複排除、エンティティマッチング、リンキング)      │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                          ランカー                                │
│            (スコアリング、クォータフィルタリング、セクション割当) │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         レンダラー                               │
│             (HTMLテンプレート、JSON API、アーカイブ)            │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                           出力                                   │
│                  (GitHub Pages / 静的ファイル)                  │
└─────────────────────────────────────────────────────────────────┘
```

## クイックスタート

### 前提条件

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) パッケージマネージャー

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/DennySORA/auto_paper_report.git
cd auto_paper_report

# 依存関係をインストール
uv sync
```

### 設定

設定ファイルを作成：

**sources.yaml** - データソースを定義
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

**entities.yaml** - 追跡エンティティを定義
```yaml
version: "1.0"
entities:
  - id: openai
    name: OpenAI
    aliases: ["OpenAI", "open-ai"]
    prefer_links: [official, github, arxiv]
```

**topics.yaml** - トピックパターンとスコアリングを定義
```yaml
version: "1.0"
topics:
  - id: llm
    name: Large Language Models
    patterns: ["LLM", "language model", "GPT", "transformer"]
```

### パイプラインの実行

```bash
# 設定を検証
uv run python main.py validate \
    --config config/sources.yaml \
    --entities config/entities.yaml \
    --topics config/topics.yaml

# フルパイプラインを実行
uv run python main.py run \
    --config config/sources.yaml \
    --entities config/entities.yaml \
    --topics config/topics.yaml \
    --state state.sqlite \
    --out public \
    --tz Asia/Taipei
```

### CLIコマンド

| コマンド | 説明 |
|----------|------|
| `run` | フルダイジェストパイプラインを実行 |
| `validate` | 設定ファイルを検証 |
| `render` | テストデータから静的ページをレンダリング |
| `db-stats` | 状態データベースの統計を表示 |

## 開発

### テストの実行

```bash
# 全テストを実行
uv run pytest

# カバレッジ付きで実行
uv run pytest --cov=src --cov-report=html

# 特定のテストファイルを実行
uv run pytest tests/unit/test_ranker/test_scorer.py
```

### コード品質

```bash
# リンティング
uv run ruff check .
uv run ruff check . --fix

# フォーマット
uv run ruff format .

# 型チェック
uv run mypy .

# セキュリティスキャン
uv run bandit -r src/
```

## GitHub Actionsデプロイ

本プロジェクトには日次自動実行用のGitHub Actionsワークフローが含まれています：

1. このリポジトリをフォーク
2. リポジトリ設定でGitHub Pagesを有効化
3. シークレットを設定（認証が必要なAPIを使用する場合）：
   - `HF_TOKEN` - Hugging Face APIトークン
   - `OPENREVIEW_TOKEN` - OpenReview APIトークン
4. ワークフローは毎日台北時間07:00に実行

## プロジェクト構造

```
auto_paper_report/
├── src/
│   ├── cli/            # コマンドラインインターフェース
│   ├── collectors/     # データソースコレクター
│   │   ├── arxiv/      # arXiv APIとRSS
│   │   ├── platform/   # GitHub, HuggingFace, OpenReview
│   │   └── html_profile/  # HTMLスクレイピングプロファイル
│   ├── config/         # 設定ロードとスキーマ
│   ├── evidence/       # 監査証跡キャプチャ
│   ├── fetch/          # キャッシュ付きHTTPクライアント
│   ├── linker/         # ストーリーリンキングと重複排除
│   ├── ranker/         # スコアリングとランキング
│   ├── renderer/       # HTML/JSON生成
│   ├── status/         # ソースヘルスモニタリング
│   └── store/          # SQLite状態永続化
├── tests/
│   ├── unit/           # ユニットテスト
│   ├── integration/    # 統合テスト
│   └── fixtures/       # テストデータ
├── public/             # 生成された静的サイト
└── .github/workflows/  # CI/CDパイプライン
```

## 設定リファレンス

### ソースメソッド

| メソッド | 説明 |
|----------|------|
| `rss_atom` | RSS/Atomフィード解析 |
| `arxiv_api` | arXiv APIクエリ |
| `github_releases` | GitHubリポジトリリリース |
| `hf_org` | Hugging Face組織モデル |
| `hf_daily_papers` | Hugging Face Daily Papers |
| `openreview_venue` | OpenReview学会投稿 |
| `papers_with_code` | Papers With Codeトレンド |
| `html_list` | HTMLページリンク抽出 |

### ソースティア

| ティア | 説明 |
|--------|------|
| 0 | 一次ソース（公式ブログ、リリース） |
| 1 | 二次ソース（アグリゲーター、ニュース） |
| 2 | 三次ソース（ソーシャルメディア、フォーラム） |

## ライセンス

MITライセンス - 詳細は[LICENSE](../LICENSE)を参照。

## コントリビューション

コントリビューションを歓迎します！コーディングガイドラインと開発標準については[CLAUDE.md](../CLAUDE.md)をお読みください。
