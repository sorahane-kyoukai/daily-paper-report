# Auto Paper Report

[English](../README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

一个自动化的研究论文与 AI 新闻摘要管线，从多个来源收集、去重、排名并生成每日报告。

## 功能特色

### 多来源数据收集

- **arXiv** - 通过 RSS 和 API 收集学术论文
- **RSS/Atom 订阅** - 从任何 RSS 来源收集博客文章和新闻
- **GitHub Releases** - 追踪仓库的版本发布
- **Hugging Face** - 按组织追踪模型发布
- **OpenReview** - 会议论文投稿
- **Papers With Code** - 热门论文和实现
- **HTML 爬虫** - 自定义 HTML 列表和配置文件提取

### 智能处理

- **故事链接** - 自动链接跨来源的相关项目
- **去重复** - 识别并合并重复内容
- **实体匹配** - 将项目与追踪的实体（公司、实验室、研究人员）关联
- **主题匹配** - 根据可配置的主题模式对内容进行分类

### 智能排名

- **可配置评分** - 来源层级、时效性、实体相关性和主题命中的权重因子
- **配额管理** - 控制各区段的输出分配
- **区段分配** - 将内容组织为 Top 5、模型发布、论文和雷达区段

### 静态网站生成

- **响应式 HTML** - 移动设备友好的每日摘要页面
- **存档页面** - 历史每日报告
- **来源状态** - 所有来源的健康监控仪表板
- **JSON API** - 机器可读的每日输出

### 自动化与部署

- **GitHub Actions** - 自动化每日管线执行
- **GitHub Pages** - 零配置静态网站部署
- **状态持久化** - SQLite 数据库支持增量更新
- **结构化日志** - 带有运行上下文的 JSON 日志，便于观测

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                          配置文件                                │
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
│                        故事链接器                                │
│               (去重复、实体匹配、链接)                           │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                          排名器                                  │
│              (评分、配额过滤、区段分配)                          │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                          渲染器                                  │
│               (HTML 模板、JSON API、存档)                       │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                           输出                                   │
│                  (GitHub Pages / 静态文件)                      │
└─────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 前置需求

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) 包管理器

### 安装

```bash
# 克隆仓库
git clone https://github.com/DennySORA/auto_paper_report.git
cd auto_paper_report

# 安装依赖
uv sync
```

### 配置

创建您的配置文件：

**sources.yaml** - 定义数据来源
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

**entities.yaml** - 定义追踪实体
```yaml
version: "1.0"
entities:
  - id: openai
    name: OpenAI
    aliases: ["OpenAI", "open-ai"]
    prefer_links: [official, github, arxiv]
```

**topics.yaml** - 定义主题模式和评分
```yaml
version: "1.0"
topics:
  - id: llm
    name: Large Language Models
    patterns: ["LLM", "language model", "GPT", "transformer"]
```

### 运行管线

```bash
# 验证配置
uv run python main.py validate \
    --config config/sources.yaml \
    --entities config/entities.yaml \
    --topics config/topics.yaml

# 运行完整管线
uv run python main.py run \
    --config config/sources.yaml \
    --entities config/entities.yaml \
    --topics config/topics.yaml \
    --state state.sqlite \
    --out public \
    --tz Asia/Taipei
```

### CLI 命令

| 命令 | 说明 |
|------|------|
| `run` | 执行完整摘要管线 |
| `validate` | 验证配置文件 |
| `render` | 从测试数据渲染静态页面 |
| `db-stats` | 显示状态数据库统计 |

## 开发

### 运行测试

```bash
# 运行所有测试
uv run pytest

# 运行并生成覆盖率报告
uv run pytest --cov=src --cov-report=html

# 运行特定测试文件
uv run pytest tests/unit/test_ranker/test_scorer.py
```

### 代码质量

```bash
# 代码检查
uv run ruff check .
uv run ruff check . --fix

# 格式化
uv run ruff format .

# 类型检查
uv run mypy .

# 安全扫描
uv run bandit -r src/
```

## GitHub Actions 部署

本项目包含用于自动化每日执行的 GitHub Actions 工作流程：

1. Fork 此仓库
2. 在仓库设置中启用 GitHub Pages
3. 配置密钥（如果使用需要认证的 API）：
   - `HF_TOKEN` - Hugging Face API 令牌
   - `OPENREVIEW_TOKEN` - OpenReview API 令牌
4. 工作流程每天在台北时间 07:00 执行

## 项目结构

```
auto_paper_report/
├── src/
│   ├── cli/            # 命令行接口
│   ├── collectors/     # 数据来源收集器
│   │   ├── arxiv/      # arXiv API 和 RSS
│   │   ├── platform/   # GitHub, HuggingFace, OpenReview
│   │   └── html_profile/  # HTML 爬虫配置文件
│   ├── config/         # 配置加载和模式定义
│   ├── evidence/       # 审计追踪捕获
│   ├── fetch/          # HTTP 客户端与缓存
│   ├── linker/         # 故事链接和去重复
│   ├── ranker/         # 评分和排名
│   ├── renderer/       # HTML/JSON 生成
│   ├── status/         # 来源健康监控
│   └── store/          # SQLite 状态持久化
├── tests/
│   ├── unit/           # 单元测试
│   ├── integration/    # 集成测试
│   └── fixtures/       # 测试数据
├── public/             # 生成的静态网站
└── .github/workflows/  # CI/CD 管线
```

## 配置参考

### 来源方法

| 方法 | 说明 |
|------|------|
| `rss_atom` | RSS/Atom 订阅解析 |
| `arxiv_api` | arXiv API 查询 |
| `github_releases` | GitHub 仓库版本发布 |
| `hf_org` | Hugging Face 组织模型 |
| `hf_daily_papers` | Hugging Face 每日论文 |
| `openreview_venue` | OpenReview 会议投稿 |
| `papers_with_code` | Papers With Code 热门 |
| `html_list` | HTML 页面链接提取 |

### 来源层级

| 层级 | 说明 |
|------|------|
| 0 | 主要来源（官方博客、版本发布） |
| 1 | 次要来源（聚合器、新闻） |
| 2 | 第三方来源（社交媒体、论坛） |

## 许可证

MIT 许可证 - 详见 [LICENSE](../LICENSE)。

## 贡献

欢迎贡献！请阅读 [CLAUDE.md](../CLAUDE.md) 了解代码规范和开发标准。
