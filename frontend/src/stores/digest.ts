import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { DigestData, Story, SourceStatus, EntityDetail } from '@/types/digest'

// Japanese source IDs — used for the 🇯🇵 Japan tab
const JP_SOURCE_IDS = new Set([
  'pfn-tech-blog-llm',
  'elyza-official-blog',
  'sakana-ai-blog',
  'llm-jp-blog',
  'awesome-japanese-llm',
  'abeja-tech-blog-llm',
  'layerx-eng-blog',
  'aishift-tech-blog',
  'ivry-ai-magazine',
  'aidb',
  'npaka-note',
  'kun432-zenn',
  'qiita-llm-tag',
  'qiita-genai-tag',
  'zenn-llm-topic',
  'llm-tech-blog-rss-feed',
  'techplay-llm-tag',
])

// Source metadata for display
const SOURCE_DISPLAY_NAMES: Record<string, { name: string; category: 'arxiv' | 'huggingface' | 'blog' | 'other' }> = {
  'arxiv-cs-ai': { name: 'arXiv cs.AI', category: 'arxiv' },
  'arxiv-cs-cl': { name: 'arXiv cs.CL', category: 'arxiv' },
  'arxiv-cs-cv': { name: 'arXiv cs.CV', category: 'arxiv' },
  'arxiv-cs-lg': { name: 'arXiv cs.LG', category: 'arxiv' },
  'arxiv-stat-ml': { name: 'arXiv stat.ML', category: 'arxiv' },
  'hf-daily-papers': { name: 'HF Daily Papers', category: 'huggingface' },
  'hf-qwen': { name: 'Qwen', category: 'huggingface' },
  'hf-openai': { name: 'OpenAI', category: 'huggingface' },
  'hf-meta-llama': { name: 'Meta Llama', category: 'huggingface' },
  'hf-google': { name: 'Google', category: 'huggingface' },
  'hf-microsoft': { name: 'Microsoft', category: 'huggingface' },
  'hf-mistralai': { name: 'Mistral AI', category: 'huggingface' },
  'hf-deepseek-ai': { name: 'DeepSeek', category: 'huggingface' },
  'hf-stabilityai': { name: 'Stability AI', category: 'huggingface' },
  'hf-cohere': { name: 'Cohere', category: 'huggingface' },
  'hf-01-ai': { name: '01.AI (Yi)', category: 'huggingface' },
  'google-ai-blog': { name: 'Google AI', category: 'blog' },
  'openai-blog': { name: 'OpenAI', category: 'blog' },
  'anthropic-research-publications': { name: 'Anthropic Research', category: 'blog' },
  'deepmind-blog': { name: 'DeepMind', category: 'blog' },
  'meta-ai-blog': { name: 'Meta AI', category: 'blog' },
  'aws-ml-blog': { name: 'AWS ML', category: 'blog' },
  'microsoft-research-blog': { name: 'Microsoft Research', category: 'blog' },
  'nvidia-ai-blog': { name: 'NVIDIA AI', category: 'blog' },
  'papers-with-code': { name: 'Papers With Code', category: 'other' },

  // Japanese AI/LLM sources
  'pfn-tech-blog-llm': { name: 'PFN Tech Blog', category: 'blog' },
  'elyza-official-blog': { name: 'ELYZA', category: 'blog' },
  'sakana-ai-blog': { name: 'Sakana AI', category: 'blog' },
  'llm-jp-blog': { name: 'LLM-jp', category: 'blog' },
  'awesome-japanese-llm': { name: '日本語LLMまとめ', category: 'other' },
  'abeja-tech-blog-llm': { name: 'ABEJA Tech', category: 'blog' },
  'layerx-eng-blog': { name: 'LayerX', category: 'blog' },
  'aishift-tech-blog': { name: 'AI Shift', category: 'blog' },
  'ivry-ai-magazine': { name: 'IVRy AI', category: 'blog' },
  'aidb': { name: 'AIDB', category: 'other' },
  'npaka-note': { name: 'npaka', category: 'blog' },
  'kun432-zenn': { name: 'kun432', category: 'blog' },
  'qiita-llm-tag': { name: 'Qiita LLM', category: 'other' },
  'qiita-genai-tag': { name: 'Qiita 生成AI', category: 'other' },
  'zenn-llm-topic': { name: 'Zenn LLM', category: 'other' },
  'llm-tech-blog-rss-feed': { name: 'LLM Blog RSS', category: 'other' },
  'techplay-llm-tag': { name: 'TECH PLAY', category: 'other' },
}

// Category display names for arXiv categories (bilingual)
const CATEGORY_DISPLAY_NAMES: Record<string, string> = {
  'cs.AI': 'Artificial Intelligence',
  'cs.CL': 'Computation & Language',
  'cs.CV': 'Computer Vision',
  'cs.LG': 'Machine Learning',
  'stat.ML': 'Statistical ML',
  'cs.NE': 'Neural & Evolutionary',
  'cs.RO': 'Robotics',
  'cs.SE': 'Software Engineering',
  // Japanese LLM / NLP topic names (from topics.yaml)
  'Japanese LLM & NLP': '日本語LLM・NLP',
  'Large Language Models': '大規模言語モデル',
}

export const useDigestStore = defineStore('digest', () => {
  // State
  const data = ref<DigestData | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const timeFilter = ref<'all' | '24h'>('24h') // Default to 24h for strict time filter

  // Getters
  const hasData = computed(() => data.value !== null)

  const top5 = computed(() => data.value?.top5 ?? [])

  const papers = computed(() => data.value?.papers ?? [])

  const modelReleases = computed(() => data.value?.model_releases_by_entity ?? {})

  const hasModelReleases = computed(() => Object.keys(modelReleases.value).length > 0)

  const radar = computed(() => data.value?.radar ?? [])

  const sourcesStatus = computed(() => data.value?.sources_status ?? [])

  const runDate = computed(() => data.value?.run_date ?? '')

  const runInfo = computed(() => data.value?.run_info ?? null)

  const archiveDates = computed(() => data.value?.archive_dates ?? [])

  const entityCatalog = computed(() => data.value?.entity_catalog ?? {})

  const totalStories = computed(() => {
    if (!data.value) return 0
    const modelStoriesCount = Object.values(data.value.model_releases_by_entity).reduce(
      (sum, stories) => sum + stories.length,
      0,
    )
    return (
      data.value.top5.length +
      data.value.papers.length +
      modelStoriesCount +
      data.value.radar.length
    )
  })

  // Group papers by category (arXiv category or first category tag)
  const papersByCategory = computed(() => {
    const grouped: Record<string, Story[]> = {}
    for (const paper of papers.value) {
      const category = paper.categories?.[0] ?? 'Uncategorized'
      if (!grouped[category]) {
        grouped[category] = []
      }
      grouped[category].push(paper)
    }
    return grouped
  })

  // Get all unique categories from papers
  const paperCategories = computed(() => Object.keys(papersByCategory.value).sort())

  // Group stories by source (source_id from primary_link)
  const allStoriesBySource = computed(() => {
    const allStories = [
      ...top5.value,
      ...papers.value,
      ...radar.value,
      ...Object.values(modelReleases.value).flat(),
    ]

    const grouped: Record<string, Story[]> = {}
    for (const story of allStories) {
      const sourceId = story.primary_link.source_id
      if (!grouped[sourceId]) {
        grouped[sourceId] = []
      }
      grouped[sourceId].push(story)
    }
    return grouped
  })

  // Get source names from sources_status
  const sourceNames = computed(() => {
    const names: Record<string, string> = {}
    for (const source of sourcesStatus.value) {
      names[source.source_id] = source.name
    }
    return names
  })

  // Get all unique source IDs with stories
  const sourceIdsWithStories = computed(() => Object.keys(allStoriesBySource.value).sort())

  // Filter stories within last 24 hours (based on report generation time, not current time)
  // Uses first_seen_at (when crawler first saw the item) for accurate filtering
  const storiesLast24Hours = computed(() => {
    // Use report generation time as baseline, fallback to current time
    const baseTime = runInfo.value?.finished_at
      ? new Date(runInfo.value.finished_at)
      : new Date()
    const cutoff = new Date(baseTime.getTime() - 24 * 60 * 60 * 1000)

    const filterRecent = (stories: Story[]) =>
      stories.filter((s) => {
        // Use first_seen_at (crawler discovery time) as primary filter
        // Fall back to published_at if first_seen_at is not available
        const timeStr = s.first_seen_at || s.published_at
        if (!timeStr) return false
        return new Date(timeStr) >= cutoff
      })

    return {
      top5: filterRecent(top5.value),
      papers: filterRecent(papers.value),
      radar: filterRecent(radar.value),
      modelReleases: Object.fromEntries(
        Object.entries(modelReleases.value).map(([key, stories]) => [key, filterRecent(stories)]),
      ),
    }
  })

  // Filtered getters based on time filter setting
  const filteredTop5 = computed(() =>
    timeFilter.value === '24h' ? storiesLast24Hours.value.top5 : top5.value,
  )

  const filteredPapers = computed(() =>
    timeFilter.value === '24h' ? storiesLast24Hours.value.papers : papers.value,
  )

  const filteredRadar = computed(() =>
    timeFilter.value === '24h' ? storiesLast24Hours.value.radar : radar.value,
  )

  const filteredModelReleases = computed(() =>
    timeFilter.value === '24h' ? storiesLast24Hours.value.modelReleases : modelReleases.value,
  )

  // Filtered papers by category
  const filteredPapersByCategory = computed(() => {
    const papersToGroup = filteredPapers.value
    const grouped: Record<string, Story[]> = {}
    for (const paper of papersToGroup) {
      const category = paper.categories?.[0] ?? 'Uncategorized'
      if (!grouped[category]) {
        grouped[category] = []
      }
      grouped[category].push(paper)
    }
    return grouped
  })

  const filteredPaperCategories = computed(() => Object.keys(filteredPapersByCategory.value).sort())

  // Filtered total count
  const filteredTotalStories = computed(() => {
    const modelStoriesCount = Object.values(filteredModelReleases.value).reduce(
      (sum, stories) => sum + stories.length,
      0,
    )
    return (
      filteredTop5.value.length +
      filteredPapers.value.length +
      modelStoriesCount +
      filteredRadar.value.length
    )
  })

  // Action to toggle time filter
  function setTimeFilter(filter: 'all' | '24h'): void {
    timeFilter.value = filter
  }

  // Get source display name and category info
  function getSourceInfo(sourceId: string): { name: string; category: string } {
    const info = SOURCE_DISPLAY_NAMES[sourceId]
    if (info) return info
    // Fallback: format source ID
    const name = sourceId
      .replace(/^(hf|arxiv)-/, '')
      .replace(/-/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase())
    return { name, category: 'other' }
  }

  // Get category display name
  function getCategoryDisplayName(category: string): string {
    return CATEGORY_DISPLAY_NAMES[category] || category
  }

  // Get entity display detail by ID
  function getEntityDetail(entityId: string): EntityDetail | null {
    return entityCatalog.value[entityId] ?? null
  }

  // ── 🇯🇵 JAPAN SOURCES ──────────────────────────────────────────

  /** True when a story comes from a Japanese source. */
  function isJapaneseStory(story: Story): boolean {
    return JP_SOURCE_IDS.has(story.primary_link.source_id)
  }

  /** All stories from Japanese sources (deduplicated). */
  const japanStories = computed(() => {
    const seen = new Set<string>()
    const stories: Story[] = []
    for (const story of [
      ...filteredTop5.value,
      ...filteredPapers.value,
      ...filteredRadar.value,
      ...Object.values(filteredModelReleases.value).flat(),
    ]) {
      if (isJapaneseStory(story) && !seen.has(story.story_id)) {
        seen.add(story.story_id)
        stories.push(story)
      }
    }
    stories.sort((a, b) => {
      const da = a.published_at ? new Date(a.published_at).getTime() : 0
      const db = b.published_at ? new Date(b.published_at).getTime() : 0
      return db - da
    })
    return stories
  })

  /** Japanese stories grouped by source (for the Japan tab pill nav). */
  const japanStoriesBySource = computed(() => {
    const grouped: Record<
      string,
      { sourceId: string; name: string; stories: Story[] }
    > = {}
    for (const story of japanStories.value) {
      const sid = story.primary_link.source_id
      if (!grouped[sid]) {
        grouped[sid] = {
          sourceId: sid,
          name: sourceNames.value[sid] || getSourceInfo(sid).name,
          stories: [],
        }
      }
      grouped[sid].stories.push(story)
    }
    // Sort groups by story count
    return Object.values(grouped).sort(
      (a, b) => b.stories.length - a.stories.length,
    )
  })

  /** Count of Japanese stories. */
  const japanStoryCount = computed(() => japanStories.value.length)

  /** Count of Japanese sources with content. */
  const japanSourceCount = computed(() => japanStoriesBySource.value.length)

  // Group all stories by source category (arXiv, HuggingFace, Blogs)
  const allStoriesBySourceCategory = computed(() => {
    const allStories = [
      ...filteredTop5.value,
      ...filteredPapers.value,
      ...filteredRadar.value,
      ...Object.values(filteredModelReleases.value).flat(),
    ]

    const grouped: Record<string, { sourceId: string; name: string; stories: Story[] }[]> = {
      arxiv: [],
      huggingface: [],
      blog: [],
      other: [],
    }

    // First group by source_id
    const bySourceId: Record<string, Story[]> = {}
    for (const story of allStories) {
      const sourceId = story.primary_link.source_id
      if (!bySourceId[sourceId]) bySourceId[sourceId] = []
      bySourceId[sourceId].push(story)
    }

    // Then organize by category
    for (const [sourceId, stories] of Object.entries(bySourceId)) {
      const info = getSourceInfo(sourceId)
      const category = info.category as keyof typeof grouped
      // Sort stories by published_at descending
      const sortedStories = [...stories].sort((a, b) => {
        const dateA = a.published_at ? new Date(a.published_at).getTime() : 0
        const dateB = b.published_at ? new Date(b.published_at).getTime() : 0
        return dateB - dateA
      })
      grouped[category].push({ sourceId, name: info.name, stories: sortedStories })
    }

    // Sort each category by story count descending
    for (const category of Object.keys(grouped)) {
      grouped[category].sort((a, b) => b.stories.length - a.stories.length)
    }

    return grouped
  })

  // Get top picks from each source (most recent item from each source)
  const topPicksBySource = computed(() => {
    const picks: Story[] = []
    for (const categoryGroups of Object.values(allStoriesBySourceCategory.value)) {
      for (const group of categoryGroups) {
        if (group.stories.length > 0) {
          picks.push(group.stories[0]) // First story is most recent due to sorting
        }
      }
    }
    return picks.sort((a, b) => {
      const dateA = a.published_at ? new Date(a.published_at).getTime() : 0
      const dateB = b.published_at ? new Date(b.published_at).getTime() : 0
      return dateB - dateA
    })
  })

  // Group ALL stories by category (not just papers) with top pick per category
  // This includes stories from top5, papers, model_releases, and radar that have categories
  const papersByCategoryWithPicks = computed(() => {
    const grouped: Record<string, { stories: Story[]; topPick: Story | null; displayName: string }> = {}

    // Collect all stories that might have categories
    const allCategorizedStories = [
      ...filteredPapers.value,
      ...filteredTop5.value,
      ...filteredRadar.value,
      ...Object.values(filteredModelReleases.value).flat(),
    ]

    for (const story of allCategorizedStories) {
      // Only include stories that have categories
      if (!story.categories || story.categories.length === 0) continue

      // Use first category
      const category = story.categories[0]
      if (!grouped[category]) {
        grouped[category] = {
          stories: [],
          topPick: null,
          displayName: getCategoryDisplayName(category),
        }
      }
      grouped[category].stories.push(story)
    }

    // Sort stories within each category by date and set top pick
    for (const category of Object.keys(grouped)) {
      grouped[category].stories.sort((a, b) => {
        const dateA = a.published_at ? new Date(a.published_at).getTime() : 0
        const dateB = b.published_at ? new Date(b.published_at).getTime() : 0
        return dateB - dateA
      })
      grouped[category].topPick = grouped[category].stories[0] || null
    }

    return grouped
  })

  // Get all category names sorted by story count
  const sortedCategories = computed(() => {
    return Object.entries(papersByCategoryWithPicks.value)
      .sort(([, a], [, b]) => b.stories.length - a.stories.length)
      .map(([category]) => category)
  })

  // Get sources grouped by status
  const sourcesByStatus = computed(() => {
    const healthy: SourceStatus[] = []
    const failed: SourceStatus[] = []
    const noUpdate: SourceStatus[] = []

    for (const source of sourcesStatus.value) {
      if (source.status === 'HAS_UPDATE') {
        healthy.push(source)
      } else if (source.status === 'FETCH_FAILED' || source.status === 'PARSE_FAILED') {
        failed.push(source)
      } else {
        noUpdate.push(source)
      }
    }

    return { healthy, failed, noUpdate }
  })

  // Actions
  /**
   * Fetch digest data.
   * @param targetDate - Optional date (YYYY-MM-DD) to fetch specific archive data.
   *                     If not provided, fetches latest daily.json.
   */
  async function fetchDigest(targetDate?: string): Promise<void> {
    isLoading.value = true
    error.value = null

    // For archive pages (specific date), use 'all' filter since backfill data
    // has first_seen_at set to current time, making 24h filter ineffective
    if (targetDate) {
      timeFilter.value = 'all'
    }

    try {
      // Determine the endpoint based on targetDate
      const endpoint = targetDate
        ? `/api/day/${targetDate}.json`
        : '/api/daily.json'

      const response = await fetch(endpoint)
      if (!response.ok) {
        // If specific date not found, fall back to daily.json
        if (targetDate && response.status === 404) {
          console.warn(`Archive for ${targetDate} not found, falling back to daily.json`)
          const fallbackResponse = await fetch('/api/daily.json')
          if (!fallbackResponse.ok) {
            throw new Error(`Failed to fetch digest: ${fallbackResponse.status} ${fallbackResponse.statusText}`)
          }
          data.value = await fallbackResponse.json()
          return
        }
        throw new Error(`Failed to fetch digest: ${response.status} ${response.statusText}`)
      }
      data.value = await response.json()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error occurred'
      console.error('Failed to fetch digest:', err)
    } finally {
      isLoading.value = false
    }
  }

  function setData(newData: DigestData): void {
    data.value = newData
  }

  function getStoriesByEntity(entityId: string): Story[] {
    return modelReleases.value[entityId] ?? []
  }

  return {
    // State
    data,
    isLoading,
    error,
    timeFilter,
    // Getters
    hasData,
    top5,
    papers,
    modelReleases,
    hasModelReleases,
    radar,
    sourcesStatus,
    runDate,
    runInfo,
    archiveDates,
    entityCatalog,
    totalStories,
    // New grouping getters
    papersByCategory,
    paperCategories,
    allStoriesBySource,
    sourceNames,
    sourceIdsWithStories,
    storiesLast24Hours,
    sourcesByStatus,
    // Filtered getters (based on time filter)
    filteredTop5,
    filteredPapers,
    filteredRadar,
    filteredModelReleases,
    filteredPapersByCategory,
    filteredPaperCategories,
    filteredTotalStories,
    // Enhanced grouping with top picks
    allStoriesBySourceCategory,
    topPicksBySource,
    papersByCategoryWithPicks,
    sortedCategories,
    // Actions
    fetchDigest,
    setData,
    getStoriesByEntity,
    setTimeFilter,
    // 🇯🇵 Japan sources
    japanStories,
    japanStoriesBySource,
    japanStoryCount,
    japanSourceCount,
    isJapaneseStory,
    // Utility functions
    getSourceInfo,
    getCategoryDisplayName,
    getEntityDetail,
  }
})
