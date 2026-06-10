# Auto Paper Report

[繁體中文](docs/README.zh-TW.md) | [简体中文](docs/README.zh-CN.md) | [日本語](docs/README.ja.md)

An automated research paper and AI news digest pipeline that collects, deduplicates, ranks, and renders daily reports from multiple sources.

## Features

### Multi-Source Data Collection

- **arXiv** - Academic papers via RSS and API
- **RSS/Atom Feeds** - Blog posts and news from any RSS source
- **GitHub Releases** - Track releases from repositories
- **Hugging Face** - Model releases by organization
- **OpenReview** - Conference paper submissions
- **Papers With Code** - Trending papers and implementations
- **HTML Scraping** - Custom HTML list and profile extraction

### Intelligent Processing

- **Story Linking** - Automatically links related items across sources
- **Deduplication** - Identifies and merges duplicate content
- **Entity Matching** - Associates items with tracked entities (companies, labs, researchers)
- **Topic Matching** - Categorizes content by configurable topic patterns

### Smart Ranking

- **Configurable Scoring** - Weight factors for tier, recency, entity relevance, and topic hits
- **Quota Management** - Control output distribution across sections
- **Section Assignment** - Organizes content into Top 5, Model Releases, Papers, and Radar sections

### Static Site Generation

- **Responsive HTML** - Mobile-friendly daily digest pages
- **Archive Pages** - Historical daily reports
- **Source Status** - Health monitoring dashboard for all sources
- **JSON API** - Machine-readable daily output

### Automation & Deployment

- **GitHub Actions** - Automated daily pipeline execution
- **GitHub Pages** - Zero-config static site deployment
- **State Persistence** - SQLite database with incremental updates
- **Structured Logging** - JSON logs with run context for observability

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Configuration                             │
│              (sources.yaml, entities.yaml, topics.yaml)         │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Collectors                               │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│   │  arXiv  │ │   RSS   │ │ GitHub  │ │   HF    │ │  HTML   │  │
│   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Story Linker                                │
│            (Deduplication, Entity Matching, Linking)            │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Ranker                                   │
│           (Scoring, Quota Filtering, Section Assignment)        │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Renderer                                  │
│              (HTML Templates, JSON API, Archive)                │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Output                                   │
│                  (GitHub Pages / Static Files)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Clone the repository
git clone https://github.com/DennySORA/auto_paper_report.git
cd auto_paper_report

# Install dependencies
uv sync
```

### Configuration

Create your configuration files:

**sources.yaml** - Define data sources
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

**entities.yaml** - Define tracked entities
```yaml
version: "1.0"
entities:
  - id: openai
    name: OpenAI
    aliases: ["OpenAI", "open-ai"]
    prefer_links: [official, github, arxiv]
```

**topics.yaml** - Define topic patterns and scoring
```yaml
version: "1.0"
topics:
  - id: llm
    name: Large Language Models
    patterns: ["LLM", "language model", "GPT", "transformer"]
```

### Running the Pipeline

```bash
# Validate configuration
uv run python main.py validate \
    --config config/sources.yaml \
    --entities config/entities.yaml \
    --topics config/topics.yaml

# Run the full pipeline
uv run python main.py run \
    --config config/sources.yaml \
    --entities config/entities.yaml \
    --topics config/topics.yaml \
    --state state.sqlite \
    --out public \
    --tz Asia/Taipei
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `run` | Execute the full digest pipeline |
| `validate` | Validate configuration files |
| `render` | Render static pages from test data |
| `db-stats` | Display state database statistics |

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/unit/test_ranker/test_scorer.py
```

### Code Quality

```bash
# Linting
uv run ruff check .
uv run ruff check . --fix

# Formatting
uv run ruff format .

# Type checking
uv run mypy .

# Security scanning
uv run bandit -r src/
```

## GitHub Actions Deployment

The project includes two manual data workflows:

1. Fork this repository
2. Enable GitHub Pages in repository settings
3. Configure secrets (if using authenticated APIs):
   - `GEMINI_*` - Optional, used for translation/relevance enrichment
4. Run one of the workflows:
   - `daily-digest.yaml` with `target_date=YYYY-MM-DD` to rerun one day
   - `reset-site.yaml` with `confirm_reset=RESET` to clear all data

## Project Structure

```
auto_paper_report/
├── src/
│   ├── cli/            # Command-line interface
│   ├── collectors/     # Data source collectors
│   │   ├── arxiv/      # arXiv API and RSS
│   │   ├── platform/   # GitHub, HuggingFace, OpenReview
│   │   └── html_profile/  # HTML scraping profiles
│   ├── config/         # Configuration loading and schemas
│   ├── evidence/       # Audit trail capture
│   ├── fetch/          # HTTP client with caching
│   ├── linker/         # Story linking and deduplication
│   ├── ranker/         # Scoring and ranking
│   ├── renderer/       # HTML/JSON generation
│   ├── status/         # Source health monitoring
│   └── store/          # SQLite state persistence
├── tests/
│   ├── unit/           # Unit tests
│   ├── integration/    # Integration tests
│   └── fixtures/       # Test data
├── public/             # Generated static site
└── .github/workflows/  # CI/CD pipelines
```

## Configuration Reference

### Source Methods

| Method | Description |
|--------|-------------|
| `rss_atom` | RSS/Atom feed parsing |
| `arxiv_api` | arXiv API queries |
| `github_releases` | GitHub repository releases |
| `hf_org` | Hugging Face organization models |
| `hf_daily_papers` | Hugging Face Daily Papers |
| `openreview_venue` | OpenReview venue submissions |
| `papers_with_code` | Papers With Code trending |
| `html_list` | HTML page link extraction |

### Source Tiers

| Tier | Description |
|------|-------------|
| 0 | Primary sources (official blogs, releases) |
| 1 | Secondary sources (aggregators, news) |
| 2 | Tertiary sources (social media, forums) |

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read the [CLAUDE.md](CLAUDE.md) file for coding guidelines and development standards.
