<script setup lang="ts">
  import { computed, ref, onMounted, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDigestStore } from '@/stores/digest'
  import { useSearch, matchesSearch } from '@/shared/composables/useSearch'
  import StoryCard from '@/components/ui/StoryCard.vue'
  import type { Story } from '@/types/digest'

  const route = useRoute()
  const digestStore = useDigestStore()
  const { searchQuery, isSearchFocused, clearSearch, setFocus } = useSearch()

  // Get target date from route params (for /day/:date routes)
  const targetDate = computed(() => {
    const dateParam = route.params.date
    if (typeof dateParam === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateParam)) {
      return dateParam
    }
    return undefined
  })

  // Fetch data when component mounts or route changes
  async function loadData(): Promise<void> {
    await digestStore.fetchDigest(targetDate.value)
  }

  onMounted(loadData)

  // Watch for route parameter changes to reload data
  watch(targetDate, loadData)

  // Core state
  const isLoading = computed(() => digestStore.isLoading)
  const hasError = computed(() => digestStore.error !== null)
  const errorMessage = computed(() => digestStore.error)
  const runDate = computed(() => digestStore.runDate)
  const runInfo = computed(() => digestStore.runInfo)

  // Tab state
  type TabView = 'category' | 'source' | 'japan'
  const activeTab = ref<TabView>('category')

  // Sub-tab state for nested navigation
  const activeCategory = ref<string | null>(null)
  const activeSource = ref<string | null>(null)
  const activeJapanSourceId = ref<string | null>(null)

  // Stats computation
  const stats = computed(() => {
    const sourceStats = digestStore.sourcesByStatus
    const working = sourceStats.healthy.length + sourceStats.noUpdate.length
    const failed = sourceStats.failed.length

    return {
      papers: digestStore.filteredTotalStories,
      categories: Object.keys(digestStore.papersByCategoryWithPicks).length,
      sourcesOk: working,
      sourcesFailed: failed,
      lastUpdated: runInfo.value?.finished_at
        ? new Date(runInfo.value.finished_at).toLocaleTimeString('en-US', {
            hour: 'numeric',
            minute: '2-digit',
            hour12: true,
          })
        : null,
    }
  })

  // Papers by category with top pick
  const categoriesWithPapers = computed(() => {
    const data = digestStore.papersByCategoryWithPicks
    const query = searchQuery.value.trim()

    return digestStore.sortedCategories
      .filter((cat) => data[cat])
      .map((category) => {
        const allPapers = data[category].stories
        const filteredPapers = query ? allPapers.filter((s) => matchesSearch(s, query)) : allPapers
        const topPick =
          filteredPapers.length > 0
            ? data[category].topPick && matchesSearch(data[category].topPick!, query)
              ? data[category].topPick
              : filteredPapers[0]
            : null

        return {
          category,
          papers: filteredPapers,
          topPick,
          count: filteredPapers.length,
        }
      })
      .filter((cat) => cat.count > 0)
  })

  // Visible stories grouped by source. Papers stay curated, while non-paper
  // sources remain fully visible because radar no longer drops them.
  const sourceGroups = computed(() => {
    const query = searchQuery.value.trim()
    const icons: Record<string, string> = {
      arxiv: '📄',
      huggingface: '🤗',
      blog: '📝',
      other: '📌',
    }
    const deduped = new Map<string, Story>()

    for (const story of [
      ...digestStore.filteredTop5,
      ...digestStore.filteredPapers,
      ...digestStore.filteredRadar,
      ...Object.values(digestStore.filteredModelReleases).flat(),
    ]) {
      deduped.set(story.story_id, story)
    }

    const storiesBySource: Record<string, Story[]> = {}
    for (const story of deduped.values()) {
      const sourceId = story.primary_link.source_id
      if (!storiesBySource[sourceId]) {
        storiesBySource[sourceId] = []
      }
      storiesBySource[sourceId].push(story)
    }

    return Object.entries(storiesBySource)
      .map(([sourceId, stories]) => {
        const sourceInfo = digestStore.getSourceInfo(sourceId)
        const filteredStories = query ? stories.filter((s) => matchesSearch(s, query)) : stories
        const sortedStories = [...filteredStories].sort((a, b) => {
          const dateA = a.published_at ? new Date(a.published_at).getTime() : 0
          const dateB = b.published_at ? new Date(b.published_at).getTime() : 0
          return dateB - dateA
        })
        const newestAt = sortedStories[0]?.published_at
          ? new Date(sortedStories[0].published_at!).getTime()
          : 0

        return {
          sourceId,
          sourceType: sourceId,
          stories: sortedStories,
          topPick: sortedStories[0] || null,
          count: sortedStories.length,
          label: digestStore.sourceNames[sourceId] || sourceInfo.name,
          icon: icons[sourceInfo.category] || '📌',
          newestAt,
        }
      })
      .filter((group) => group.count > 0)
      .sort((a, b) => b.newestAt - a.newestAt || b.count - a.count)
  })

  // ── 🇯🇵 JAPAN TAB ──────────────────────────────────────────────
  const japanSourceGroups = computed(() => {
    const query = searchQuery.value.trim()
    const groups = digestStore.japanStoriesBySource

    return groups
      .map((g) => {
        const filtered = query
          ? g.stories.filter((s) => matchesSearch(s, query))
          : g.stories
        return { ...g, stories: filtered, count: filtered.length }
      })
      .filter((g) => g.count > 0)
  })

  const currentJapanSource = computed(() => {
    if (!activeJapanSourceId.value) return null
    return (
      japanSourceGroups.value.find(
        (g) => g.sourceId === activeJapanSourceId.value,
      ) || null
    )
  })

  // Total search results count
  const totalSearchResults = computed(() => {
    if (!searchQuery.value.trim()) return null
    if (activeTab.value === 'source') {
      return sourceGroups.value.reduce((sum, group) => sum + group.count, 0)
    }
    if (activeTab.value === 'japan') {
      return japanSourceGroups.value.reduce((sum, group) => sum + group.count, 0)
    }
    return categoriesWithPapers.value.reduce((sum, cat) => sum + cat.count, 0)
  })

  // Auto-select first category/source/japan-source on mount
  onMounted(() => {
    if (categoriesWithPapers.value.length > 0) {
      activeCategory.value = categoriesWithPapers.value[0].category
    }
    if (sourceGroups.value.length > 0) {
      activeSource.value = sourceGroups.value[0].sourceType
    }
    if (japanSourceGroups.value.length > 0) {
      activeJapanSourceId.value = japanSourceGroups.value[0].sourceId
    }
  })

  // Reset sub-tab selection when data changes
  watch(
    categoriesWithPapers,
    (cats) => {
      if (cats.length > 0 && !cats.find((c) => c.category === activeCategory.value)) {
        activeCategory.value = cats[0].category
      }
    },
    { deep: true },
  )

  watch(
    sourceGroups,
    (groups) => {
      if (groups.length > 0 && !groups.find((g) => g.sourceType === activeSource.value)) {
        activeSource.value = groups[0].sourceType
      }
    },
    { deep: true },
  )

  watch(
    japanSourceGroups,
    (groups) => {
      if (
        groups.length > 0 &&
        !groups.find((g) => g.sourceId === activeJapanSourceId.value)
      ) {
        activeJapanSourceId.value = groups[0].sourceId
      }
    },
    { deep: true },
  )

  // Get current category papers
  const currentCategoryData = computed(() => {
    if (!activeCategory.value) return null
    return categoriesWithPapers.value.find((c) => c.category === activeCategory.value)
  })

  // Get current source papers
  const currentSourceData = computed(() => {
    if (!activeSource.value) return null
    return sourceGroups.value.find((g) => g.sourceType === activeSource.value)
  })

  // Tab definitions
  const tabs = [
    { id: 'category' as const, label: 'By Category', icon: '📁' },
    { id: 'source' as const, label: 'By Source', icon: '🔗' },
    { id: 'japan' as const, label: '🇯🇵 Japan', icon: '🗾' },
  ]

  function getTabCount(tabId: TabView): number {
    switch (tabId) {
      case 'category':
        return categoriesWithPapers.value.length
      case 'source':
        return sourceGroups.value.length
      case 'japan':
        return japanSourceGroups.value.length
    }
  }
</script>

<template>
  <div
    data-testid="home-page"
    class="dashboard"
  >
    <!-- ═══════════════════════════════════════════════════════════════
         DASHBOARD HEADER
         ═══════════════════════════════════════════════════════════════ -->
    <header class="dashboard-header">
      <div class="header-content">
        <div class="header-title-group">
          <p class="header-kicker">
            Research Desk
          </p>
          <h1 class="header-title">
            Daily Paper Report
          </h1>
          <div
            v-if="runDate"
            class="header-meta"
          >
            <span class="header-date">{{ runDate }}</span>
            <span class="meta-dot">•</span>
            <RouterLink
              :to="`/day/${runDate}`"
              class="header-link"
            >
              Permalink
            </RouterLink>
          </div>
        </div>
        <RouterLink
          to="/reports"
          class="header-report-link"
        >
          Weekly / Monthly
        </RouterLink>
      </div>
    </header>

    <!-- ═══════════════════════════════════════════════════════════════
         STATS DASHBOARD
         ═══════════════════════════════════════════════════════════════ -->
    <section
      v-if="!isLoading && !hasError"
      class="stats-grid"
    >
      <article class="stat-card stat-papers">
        <div class="stat-icon-wrap">
          <svg
            class="stat-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line
              x1="16"
              y1="13"
              x2="8"
              y2="13"
            />
            <line
              x1="16"
              y1="17"
              x2="8"
              y2="17"
            />
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-number">{{ stats.papers }}</span>
          <span class="stat-label">Items</span>
        </div>
      </article>

      <article class="stat-card stat-categories">
        <div class="stat-icon-wrap">
          <svg
            class="stat-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-number">{{ stats.categories }}</span>
          <span class="stat-label">Categories</span>
        </div>
      </article>

      <article class="stat-card stat-healthy">
        <div class="stat-icon-wrap">
          <svg
            class="stat-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-number">{{ stats.sourcesOk }}</span>
          <span class="stat-label">Sources OK</span>
        </div>
      </article>

      <article
        class="stat-card"
        :class="stats.sourcesFailed > 0 ? 'stat-error' : 'stat-neutral'"
      >
        <div class="stat-icon-wrap">
          <svg
            v-if="stats.sourcesFailed > 0"
            class="stat-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line
              x1="18"
              y1="6"
              x2="6"
              y2="18"
            />
            <line
              x1="6"
              y1="6"
              x2="18"
              y2="18"
            />
          </svg>
          <svg
            v-else
            class="stat-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle
              cx="12"
              cy="12"
              r="10"
            />
            <line
              x1="8"
              y1="12"
              x2="16"
              y2="12"
            />
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-number">{{ stats.sourcesFailed }}</span>
          <span class="stat-label">Failed</span>
        </div>
      </article>

      <article class="stat-card stat-time">
        <div class="stat-icon-wrap">
          <svg
            class="stat-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <circle
              cx="12"
              cy="12"
              r="10"
            />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-number stat-number-time">{{ stats.lastUpdated || '—' }}</span>
          <span class="stat-label">Updated</span>
        </div>
      </article>
    </section>

    <!-- Stats Skeleton -->
    <section
      v-else-if="isLoading"
      class="stats-grid"
    >
      <div
        v-for="i in 5"
        :key="i"
        class="stat-card stat-skeleton"
      >
        <div class="stat-icon-skeleton" />
        <div class="stat-body">
          <div class="stat-number-skeleton" />
          <div class="stat-label-skeleton" />
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         SEARCH BAR
         ═══════════════════════════════════════════════════════════════ -->
    <div
      v-if="!isLoading && !hasError"
      class="search-container"
    >
      <div
        class="search-box"
        role="search"
        :class="{
          'search-box--focused': isSearchFocused,
          'search-box--has-query': searchQuery.length > 0,
        }"
      >
        <svg
          class="search-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <circle
            cx="11"
            cy="11"
            r="8"
          />
          <path d="m21 21-4.35-4.35" />
        </svg>
        <input
          v-model="searchQuery"
          type="search"
          class="search-input"
          placeholder="Search updates by title, author, or content..."
          aria-label="Search updates"
          @focus="setFocus(true)"
          @blur="setFocus(false)"
        >
        <Transition name="fade">
          <button
            v-if="searchQuery.length > 0"
            type="button"
            class="search-clear-btn"
            title="Clear search"
            aria-label="Clear search"
            @click="clearSearch"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line
                x1="18"
                y1="6"
                x2="6"
                y2="18"
              />
              <line
                x1="6"
                y1="6"
                x2="18"
                y2="18"
              />
            </svg>
          </button>
        </Transition>
      </div>
      <Transition name="slide-fade">
        <div
          v-if="totalSearchResults !== null"
          class="search-results-indicator"
        >
          <span class="results-count">{{ totalSearchResults }}</span>
          <span class="results-label">{{ totalSearchResults === 1 ? 'result' : 'results' }}</span>
        </div>
      </Transition>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════
         TAB NAVIGATION
         ═══════════════════════════════════════════════════════════════ -->
    <nav
      v-if="!isLoading && !hasError"
      class="main-tabs"
    >
      <div class="tabs-track">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="main-tab"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          <span class="tab-emoji">{{ tab.icon }}</span>
          <span class="tab-text">{{ tab.label }}</span>
          <span class="tab-badge">{{ getTabCount(tab.id) }}</span>
        </button>
      </div>
    </nav>

    <!-- ═══════════════════════════════════════════════════════════════
         CONTENT AREA
         ═══════════════════════════════════════════════════════════════ -->

    <!-- Loading State -->
    <div
      v-if="isLoading"
      class="content-skeleton"
    >
      <div
        v-for="i in 5"
        :key="i"
        class="card-skeleton"
        :style="{ '--delay': `${i * 50}ms` }"
      >
        <div class="skeleton-badge" />
        <div class="skeleton-title" />
        <div class="skeleton-meta" />
        <div class="skeleton-body" />
      </div>
    </div>

    <!-- Error State -->
    <div
      v-else-if="hasError"
      class="error-state"
    >
      <div class="error-icon">
        ⚠️
      </div>
      <h3 class="error-title">
        Unable to Load Data
      </h3>
      <p class="error-desc">
        {{ errorMessage }}
      </p>
      <button
        class="error-retry-btn"
        @click="digestStore.fetchDigest()"
      >
        <svg
          class="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        Retry
      </button>
    </div>

    <!-- Main Content -->
    <main
      v-else
      class="content-area"
    >
      <!-- BY CATEGORY VIEW -->
      <div
        v-show="activeTab === 'category'"
        class="content-panel"
      >
        <div
          v-if="categoriesWithPapers.length > 0"
          class="panel-layout"
        >
          <!-- Category Pills -->
          <nav class="pill-nav">
            <button
              v-for="(cat, idx) in categoriesWithPapers"
              :key="cat.category"
              class="pill-btn"
              :class="{ active: activeCategory === cat.category }"
              :style="{ '--idx': idx }"
              @click="activeCategory = cat.category"
            >
              <span class="pill-label">{{ cat.category }}</span>
              <span class="pill-count">{{ cat.count }}</span>
            </button>
          </nav>

          <!-- Category Content -->
          <div
            v-if="currentCategoryData"
            :key="currentCategoryData.category"
            class="panel-content"
          >
            <!-- Top Pick -->
            <section
              v-if="currentCategoryData.topPick"
              class="top-pick-section"
            >
              <header class="section-header">
                <span class="section-badge">⭐ Top Pick</span>
                <span class="section-hint">Most relevant paper in this category</span>
              </header>
              <StoryCard
                :story="currentCategoryData.topPick"
                :rank="1"
                accent-type="highlight"
                :featured="true"
                :show-entities="true"
                :show-categories="false"
                :show-source="true"
                :show-authors="true"
                :show-summary="true"
                class="featured-card"
              />
            </section>

            <!-- Other Papers -->
            <section class="papers-section">
              <header
                v-if="
                  currentCategoryData.papers.filter(
                    (s) => s.story_id !== currentCategoryData?.topPick?.story_id,
                  ).length > 0
                "
                class="section-header"
              >
                <span class="section-badge section-badge-muted">📑 All Papers</span>
              </header>
              <div class="papers-list">
                <StoryCard
                  v-for="(story, idx) in currentCategoryData.papers.filter(
                    (s) => s.story_id !== currentCategoryData?.topPick?.story_id,
                  )"
                  :key="story.story_id"
                  :story="story"
                  :show-entities="true"
                  :show-categories="false"
                  :show-source="true"
                  :show-authors="true"
                  :show-summary="true"
                  class="paper-card-item"
                  :style="{ '--idx': idx }"
                />
              </div>
            </section>
          </div>
        </div>

        <!-- Empty State -->
        <div
          v-else
          class="empty-state"
        >
          <div class="empty-icon">
            📁
          </div>
          <h3 class="empty-title">
            No Categories Found
          </h3>
          <p class="empty-desc">
            No categorized papers available for this time range.
          </p>
        </div>
      </div>

      <!-- BY SOURCE VIEW -->
      <div
        v-show="activeTab === 'source'"
        class="content-panel"
      >
        <div
          v-if="sourceGroups.length > 0"
          class="panel-layout"
        >
          <!-- Source Pills -->
          <nav class="pill-nav">
            <button
              v-for="(group, idx) in sourceGroups"
              :key="group.sourceId"
              class="pill-btn"
              :class="{ active: activeSource === group.sourceType }"
              :style="{ '--idx': idx }"
              @click="activeSource = group.sourceType"
            >
              <span class="pill-emoji">{{ group.icon }}</span>
              <span class="pill-label">{{ group.label }}</span>
              <span class="pill-count">{{ group.count }}</span>
            </button>
          </nav>

          <!-- Source Content -->
          <div
            v-if="currentSourceData"
            :key="currentSourceData.sourceId"
            class="panel-content"
          >
            <section class="papers-section">
              <header class="section-header">
                <span class="section-badge">✨ Source View</span>
                <span class="section-hint">
                  {{ currentSourceData.count }} visible item{{
                    currentSourceData.count !== 1 ? 's' : ''
                  }}
                  from {{ currentSourceData.label }}
                </span>
              </header>
              <div class="papers-list">
                <StoryCard
                  v-for="(story, idx) in currentSourceData.stories"
                  :key="story.story_id"
                  :story="story"
                  accent-type="highlight"
                  :show-entities="true"
                  :show-categories="true"
                  :show-source="false"
                  :show-authors="true"
                  :show-summary="true"
                  class="paper-card-item"
                  :style="{ '--idx': idx }"
                />
              </div>
            </section>
          </div>
        </div>

        <!-- Empty State -->
        <div
          v-else
          class="empty-state"
        >
          <div class="empty-icon">
            🔗
          </div>
          <h3 class="empty-title">
            No Sources Found
          </h3>
          <p class="empty-desc">
            No source updates available for this time range.
          </p>
        </div>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════
           🇯🇵 JAPAN VIEW — Japanese LLM / AI Sources
           ═══════════════════════════════════════════════════════════════ -->
      <div
        v-show="activeTab === 'japan'"
        class="content-panel"
      >
        <div
          v-if="japanSourceGroups.length > 0"
          class="panel-layout"
        >
          <!-- Japan Source Pills -->
          <nav class="pill-nav japan-pill-nav">
            <div class="japan-banner">
              <span class="japan-banner-flag">🇯🇵</span>
              <span class="japan-banner-label">Japanese LLM / AI Sources</span>
              <span class="japan-banner-count">
                {{ digestStore.japanStoryCount }} articles from
                {{ digestStore.japanSourceCount }} sources
              </span>
            </div>
            <button
              v-for="(group, idx) in japanSourceGroups"
              :key="group.sourceId"
              class="pill-btn japan-pill"
              :class="{ active: activeJapanSourceId === group.sourceId }"
              :style="{ '--idx': idx }"
              @click="activeJapanSourceId = group.sourceId"
            >
              <span class="pill-label">{{ group.name }}</span>
              <span class="pill-count">{{ group.count }}</span>
            </button>
          </nav>

          <!-- Japan Source Content -->
          <div
            v-if="currentJapanSource"
            :key="currentJapanSource.sourceId"
            class="panel-content"
          >
            <section
              v-if="currentJapanSource.stories[0]"
              class="top-pick-section"
            >
              <header class="section-header">
                <span class="section-badge japan-badge">🇯🇵 Top Pick</span>
                <span class="section-hint">
                  Latest from
                  {{ currentJapanSource.name }}
                </span>
              </header>
              <StoryCard
                :story="currentJapanSource.stories[0]"
                :rank="1"
                accent-type="highlight"
                :featured="true"
                :show-entities="true"
                :show-categories="false"
                :show-source="true"
                :show-authors="true"
                :show-summary="true"
                class="featured-card"
              />
            </section>

            <!-- Other articles from this Japanese source -->
            <section
              v-if="currentJapanSource.stories.length > 1"
              class="papers-section"
            >
              <header class="section-header">
                <span class="section-badge section-badge-muted">
                  📰 More from {{ currentJapanSource.name }}
                </span>
              </header>
              <div class="papers-list">
                <StoryCard
                  v-for="(story, idx) in currentJapanSource.stories.slice(1)"
                  :key="story.story_id"
                  :story="story"
                  :show-entities="true"
                  :show-categories="false"
                  :show-source="false"
                  :show-authors="true"
                  :show-summary="true"
                  class="paper-card-item"
                  :style="{ '--idx': idx }"
                />
              </div>
            </section>
          </div>
        </div>

        <!-- Empty State -->
        <div
          v-else
          class="empty-state"
        >
          <div class="empty-icon">
            🗾
          </div>
          <h3 class="empty-title">
            No Japanese Sources Found
          </h3>
          <p class="empty-desc">
            No updates from Japanese LLM / AI sources are available for this time range.
          </p>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
  /* ═══════════════════════════════════════════════════════════════════════════
   RESEARCH DASHBOARD - Premium, Data-Focused Design
   ═══════════════════════════════════════════════════════════════════════════ */

  .dashboard {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    animation: dashboardReveal 0.5s var(--ease-out) both;
  }

  @keyframes dashboardReveal {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   HEADER
   ═══════════════════════════════════════════════════════════════════════════ */

  .dashboard-header {
    padding: 1.35rem;
    min-height: 10rem;
    background:
      linear-gradient(135deg, rgb(244 63 94 / 0.16), transparent 38%),
      linear-gradient(105deg, var(--color-surface-secondary), var(--color-surface-primary));
    border: 1px solid var(--color-border-default);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
  }

  .header-content {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  @media (min-width: 640px) {
    .header-content {
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
    }
  }

  .header-title-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .header-kicker {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
    color: var(--color-accent-primary);
  }

  .header-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-family: var(--font-display);
    font-size: clamp(2rem, 5vw, 4rem);
    font-weight: 700;
    color: var(--color-text-primary);
    letter-spacing: 0;
  }

  @media (min-width: 640px) {
    .dashboard-header {
      padding: 1.75rem;
    }
  }

  .header-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8125rem;
    color: var(--color-text-muted);
  }

  .header-date {
    font-family: var(--font-mono);
    color: var(--color-text-secondary);
    font-weight: 500;
  }

  .meta-dot {
    opacity: 0.4;
  }

  .header-link {
    color: var(--color-accent-primary);
    text-decoration: none;
    transition: all var(--duration-fast) var(--ease-out);
  }

  .header-link:hover {
    color: var(--color-accent-primary-hover);
    text-decoration: underline;
  }

  .header-report-link {
    align-self: flex-start;
    padding: 0.65rem 0.85rem;
    color: var(--color-text-primary);
    text-decoration: none;
    background: rgb(255 255 255 / 0.05);
    border: 1px solid var(--color-border-default);
    border-radius: var(--radius-md);
    transition:
      border-color var(--duration-fast) var(--ease-out),
      transform var(--duration-fast) var(--ease-out);
  }

  .header-report-link:hover {
    border-color: var(--color-accent-primary);
    transform: translateY(-1px);
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   STATS GRID
   ═══════════════════════════════════════════════════════════════════════════ */

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
  }

  @media (min-width: 640px) {
    .stats-grid {
      grid-template-columns: repeat(5, 1fr);
    }
  }

  .stat-card {
    display: flex;
    align-items: center;
    gap: 0.875rem;
    padding: 1rem 1.125rem;
    background: var(--color-surface-primary);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-xl);
    position: relative;
    overflow: hidden;
    transition: all var(--duration-base) var(--ease-out);
    animation: statReveal 0.4s var(--ease-out) both;
    animation-delay: calc(var(--idx, 0) * 50ms);
  }

  .stat-card:nth-child(1) {
    --idx: 0;
  }
  .stat-card:nth-child(2) {
    --idx: 1;
  }
  .stat-card:nth-child(3) {
    --idx: 2;
  }
  .stat-card:nth-child(4) {
    --idx: 3;
  }
  .stat-card:nth-child(5) {
    --idx: 4;
  }

  @keyframes statReveal {
    from {
      opacity: 0;
      transform: translateY(12px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .stat-card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, currentColor 0%, transparent 60%);
    opacity: 0.03;
    transition: opacity var(--duration-base) var(--ease-out);
  }

  .stat-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
    border-color: var(--color-border-default);
  }

  .stat-card:hover::before {
    opacity: 0.06;
  }

  .stat-icon-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2.75rem;
    height: 2.75rem;
    background: currentColor;
    border-radius: var(--radius-lg);
    flex-shrink: 0;
    transition: transform var(--duration-base) var(--ease-spring);
  }

  .stat-card:hover .stat-icon-wrap {
    transform: scale(1.05);
  }

  .stat-icon {
    width: 1.25rem;
    height: 1.25rem;
    color: var(--color-surface-base);
  }

  .stat-body {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .stat-number {
    font-family: var(--font-mono);
    font-size: 1.5rem;
    font-weight: 700;
    line-height: 1.1;
    color: var(--color-text-primary);
  }

  .stat-number-time {
    font-size: 1.125rem;
  }

  .stat-label {
    font-size: 0.6875rem;
    font-weight: 600;
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0;
    margin-top: 0.125rem;
  }

  /* Stat Colors */
  .stat-papers {
    color: var(--color-section-papers);
  }
  .stat-categories {
    color: var(--color-section-models);
  }
  .stat-healthy {
    color: var(--color-accent-success);
  }
  .stat-error {
    color: var(--color-accent-error);
  }
  .stat-neutral {
    color: var(--color-text-muted);
  }
  .stat-time {
    color: var(--color-text-tertiary);
  }

  /* Stat Skeleton */
  .stat-skeleton {
    color: var(--color-surface-elevated);
  }

  .stat-icon-skeleton {
    width: 2.75rem;
    height: 2.75rem;
    background: var(--color-surface-secondary);
    border-radius: var(--radius-lg);
    animation: pulse 1.5s var(--ease-in-out) infinite;
  }

  .stat-number-skeleton {
    height: 1.5rem;
    width: 2.5rem;
    background: var(--color-surface-secondary);
    border-radius: var(--radius-sm);
    animation: pulse 1.5s var(--ease-in-out) infinite;
  }

  .stat-label-skeleton {
    height: 0.75rem;
    width: 4rem;
    margin-top: 0.25rem;
    background: var(--color-surface-secondary);
    border-radius: var(--radius-sm);
    animation: pulse 1.5s var(--ease-in-out) infinite;
    animation-delay: 0.1s;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 0.4;
    }
    50% {
      opacity: 0.7;
    }
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   SEARCH BAR
   ═══════════════════════════════════════════════════════════════════════════ */

  .search-container {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    animation: searchReveal 0.4s var(--ease-out) both;
    animation-delay: 100ms;
  }

  @keyframes searchReveal {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @media (min-width: 640px) {
    .search-container {
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
    }
  }

  .search-box {
    position: relative;
    display: flex;
    align-items: center;
    flex: 1;
    max-width: 560px;
    background: var(--color-surface-secondary);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-xl);
    transition: all var(--duration-base) var(--ease-out);
    overflow: hidden;
  }

  .search-box::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, var(--color-accent-primary-glow) 0%, transparent 50%);
    opacity: 0;
    transition: opacity var(--duration-base) var(--ease-out);
    pointer-events: none;
  }

  .search-box--focused {
    border-color: var(--color-accent-primary);
    box-shadow:
      0 0 0 3px var(--color-accent-primary-glow),
      var(--shadow-md);
    background: var(--color-surface-primary);
  }

  .search-box--focused::before {
    opacity: 0.5;
  }

  .search-box--has-query {
    border-color: var(--color-border-default);
  }

  .search-icon {
    position: absolute;
    left: 1rem;
    width: 1.25rem;
    height: 1.25rem;
    color: var(--color-text-muted);
    transition: color var(--duration-fast) var(--ease-out);
    pointer-events: none;
  }

  .search-box--focused .search-icon {
    color: var(--color-accent-primary);
  }

  .search-input {
    width: 100%;
    padding: 0.875rem 3rem 0.875rem 3rem;
    font-family: var(--font-sans);
    font-size: 0.9375rem;
    color: var(--color-text-primary);
    background: transparent;
    border: none;
    outline: none;
  }

  .search-input::placeholder {
    color: var(--color-text-muted);
    transition: color var(--duration-fast) var(--ease-out);
  }

  .search-input:focus::placeholder {
    color: var(--color-text-tertiary);
  }

  .search-clear-btn {
    position: absolute;
    right: 0.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.75rem;
    height: 1.75rem;
    background: var(--color-surface-overlay);
    border: none;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-out);
  }

  .search-clear-btn svg {
    width: 0.875rem;
    height: 0.875rem;
    color: var(--color-text-muted);
  }

  .search-clear-btn:hover {
    background: var(--color-accent-error);
  }

  .search-clear-btn:hover svg {
    color: #fff;
  }

  .search-results-indicator {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    background: var(--color-accent-primary);
    border-radius: var(--radius-full);
    white-space: nowrap;
  }

  .results-count {
    font-family: var(--font-mono);
    font-size: 0.875rem;
    font-weight: 700;
    color: #fff;
  }

  .results-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: rgb(255 255 255 / 0.8);
  }

  /* Transitions */
  .fade-enter-active,
  .fade-leave-active {
    transition: opacity var(--duration-fast) var(--ease-out);
  }

  .fade-enter-from,
  .fade-leave-to {
    opacity: 0;
  }

  .slide-fade-enter-active,
  .slide-fade-leave-active {
    transition: all var(--duration-base) var(--ease-out);
  }

  .slide-fade-enter-from {
    opacity: 0;
    transform: translateX(10px);
  }

  .slide-fade-leave-to {
    opacity: 0;
    transform: translateX(-10px);
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   MAIN TABS
   ═══════════════════════════════════════════════════════════════════════════ */

  .main-tabs {
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .tabs-track {
    display: flex;
    gap: 0;
  }

  .main-tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.875rem 1.25rem;
    font-family: var(--font-display);
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text-muted);
    background: transparent;
    border: none;
    cursor: pointer;
    position: relative;
    transition: all var(--duration-fast) var(--ease-out);
  }

  .main-tab::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--color-accent-primary);
    transform: scaleX(0);
    transform-origin: center;
    transition: transform var(--duration-base) var(--ease-out);
  }

  .main-tab:hover:not(.active) {
    color: var(--color-text-secondary);
  }

  .main-tab.active {
    color: var(--color-text-primary);
    font-weight: 600;
  }

  .main-tab.active::after {
    transform: scaleX(1);
  }

  .tab-emoji {
    font-size: 1.125rem;
  }

  .tab-text {
    display: none;
  }

  @media (min-width: 480px) {
    .tab-text {
      display: inline;
    }
  }

  .tab-badge {
    padding: 0.125rem 0.5rem;
    font-size: 0.6875rem;
    font-weight: 700;
    font-family: var(--font-mono);
    background: var(--color-surface-secondary);
    color: var(--color-text-muted);
    border-radius: var(--radius-full);
    transition: all var(--duration-fast) var(--ease-out);
  }

  .main-tab.active .tab-badge {
    background: var(--color-accent-primary);
    color: #fff;
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   CONTENT AREA
   ═══════════════════════════════════════════════════════════════════════════ */

  .content-area {
    min-height: 400px;
  }

  .content-panel {
    animation: panelFade 0.3s var(--ease-out) both;
  }

  @keyframes panelFade {
    from {
      opacity: 0;
      transform: translateY(6px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .panel-layout {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   PILL NAVIGATION - Prominent Sub-Tab Design
   ═══════════════════════════════════════════════════════════════════════════ */

  .pill-nav {
    display: flex;
    flex-wrap: wrap;
    gap: 0.625rem;
    padding: 1rem 1.25rem;
    background: linear-gradient(
      135deg,
      var(--color-surface-secondary) 0%,
      var(--color-surface-primary) 100%
    );
    border: 1px solid var(--color-border-default);
    border-radius: var(--radius-2xl);
    box-shadow: var(--shadow-sm);
    position: relative;
    overflow: hidden;
  }

  .pill-nav::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--color-accent-primary), transparent);
    opacity: 0.5;
  }

  .pill-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.625rem;
    padding: 0.75rem 1.125rem;
    font-family: var(--font-display);
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-text-secondary);
    background: var(--color-surface-overlay);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-out);
    animation: pillReveal 0.35s var(--ease-out) both;
    animation-delay: calc(var(--idx, 0) * 40ms);
    position: relative;
    overflow: hidden;
  }

  .pill-btn::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgb(255 255 255 / 0.1) 0%, transparent 50%);
    opacity: 0;
    transition: opacity var(--duration-fast) var(--ease-out);
  }

  @keyframes pillReveal {
    from {
      opacity: 0;
      transform: translateY(8px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .pill-btn:hover:not(.active) {
    color: var(--color-text-primary);
    background: var(--color-surface-elevated);
    border-color: var(--color-border-default);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  .pill-btn:hover:not(.active)::before {
    opacity: 1;
  }

  .pill-btn:active:not(.active) {
    transform: translateY(0) scale(0.98);
  }

  .pill-btn.active {
    color: #fff;
    background: linear-gradient(
      135deg,
      var(--color-accent-primary) 0%,
      var(--color-accent-primary-hover) 100%
    );
    border-color: transparent;
    box-shadow: var(--shadow-glow-primary), var(--shadow-md);
    font-weight: 700;
  }

  .pill-btn.active::before {
    opacity: 0.3;
  }

  .pill-btn.active:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-glow-primary), var(--shadow-lg);
  }

  .pill-emoji {
    font-size: 1.125rem;
    transition: transform var(--duration-fast) var(--ease-spring);
  }

  .pill-btn:hover .pill-emoji {
    transform: scale(1.1);
  }

  .pill-btn.active .pill-emoji {
    filter: drop-shadow(0 0 4px rgb(255 255 255 / 0.5));
  }

  .pill-label {
    white-space: nowrap;
    letter-spacing: 0;
  }

  .pill-count {
    padding: 0.1875rem 0.5rem;
    font-size: 0.6875rem;
    font-weight: 700;
    font-family: var(--font-mono);
    color: var(--color-text-tertiary);
    background: var(--color-surface-secondary);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-full);
    transition: all var(--duration-fast) var(--ease-out);
  }

  .pill-btn:hover:not(.active) .pill-count {
    background: var(--color-surface-overlay);
    border-color: var(--color-border-default);
  }

  .pill-btn.active .pill-count {
    background: rgb(255 255 255 / 0.25);
    border-color: transparent;
    color: #fff;
  }

  /* Panel Content */
  .panel-content {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    animation: contentReveal 0.3s var(--ease-out) both;
  }

  @keyframes contentReveal {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Section Headers */
  .section-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .section-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.75rem;
    font-size: 0.6875rem;
    font-weight: 700;
    color: var(--color-accent-highlight);
    background: rgb(216 189 122 / 0.12);
    border: 1px solid rgb(216 189 122 / 0.25);
    border-radius: var(--radius-full);
    text-transform: uppercase;
    letter-spacing: 0;
  }

  .section-badge-muted {
    color: var(--color-text-tertiary);
    background: var(--color-surface-secondary);
    border-color: var(--color-border-subtle);
  }

  .section-hint {
    font-size: 0.75rem;
    color: var(--color-text-muted);
  }

  /* Featured Card */
  .featured-card {
    animation: featuredReveal 0.4s var(--ease-out) both;
  }

  @keyframes featuredReveal {
    from {
      opacity: 0;
      transform: translateY(8px) scale(0.98);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  /* Papers List */
  .papers-section {
    margin-top: 0.5rem;
  }

  .papers-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .paper-card-item {
    animation: paperReveal 0.35s var(--ease-out) both;
    animation-delay: calc(var(--idx, 0) * 40ms);
  }

  @keyframes paperReveal {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   LOADING SKELETON
   ═══════════════════════════════════════════════════════════════════════════ */

  .content-skeleton {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .card-skeleton {
    background: var(--color-surface-primary);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-lg);
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    animation: skeletonReveal 0.4s var(--ease-out) both;
    animation-delay: var(--delay, 0ms);
  }

  @keyframes skeletonReveal {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .skeleton-badge {
    height: 1.25rem;
    width: 30%;
    background: var(--color-surface-secondary);
    border-radius: var(--radius-sm);
    animation: pulse 1.5s var(--ease-in-out) infinite;
  }

  .skeleton-title {
    height: 1.5rem;
    width: 70%;
    background: var(--color-surface-secondary);
    border-radius: var(--radius-sm);
    animation: pulse 1.5s var(--ease-in-out) infinite;
    animation-delay: 0.1s;
  }

  .skeleton-meta {
    height: 1rem;
    width: 45%;
    background: var(--color-surface-secondary);
    border-radius: var(--radius-sm);
    animation: pulse 1.5s var(--ease-in-out) infinite;
    animation-delay: 0.2s;
  }

  .skeleton-body {
    height: 4rem;
    width: 100%;
    background: var(--color-surface-secondary);
    border-radius: var(--radius-md);
    animation: pulse 1.5s var(--ease-in-out) infinite;
    animation-delay: 0.3s;
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   ERROR STATE
   ═══════════════════════════════════════════════════════════════════════════ */

  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem 2rem;
    text-align: center;
    background: var(--color-surface-primary);
    border: 1px solid var(--color-accent-error);
    border-radius: var(--radius-xl);
    animation: errorShake 0.5s var(--ease-out);
  }

  @keyframes errorShake {
    0%,
    100% {
      transform: translateX(0);
    }
    20% {
      transform: translateX(-8px);
    }
    40% {
      transform: translateX(8px);
    }
    60% {
      transform: translateX(-4px);
    }
    80% {
      transform: translateX(4px);
    }
  }

  .error-icon {
    font-size: 3.5rem;
    margin-bottom: 1rem;
  }

  .error-title {
    font-family: var(--font-display);
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--color-accent-error);
    margin-bottom: 0.5rem;
  }

  .error-desc {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    margin-bottom: 1.5rem;
    max-width: 400px;
  }

  .error-retry-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    font-family: var(--font-display);
    font-size: 0.875rem;
    font-weight: 600;
    color: #fff;
    background: var(--color-accent-primary);
    border: none;
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-out);
  }

  .error-retry-btn:hover {
    background: var(--color-accent-primary-hover);
    transform: translateY(-2px);
    box-shadow: var(--shadow-glow-primary);
  }

  .error-retry-btn:active {
    transform: translateY(0);
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   EMPTY STATE
   ═══════════════════════════════════════════════════════════════════════════ */

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem 2rem;
    text-align: center;
    background: var(--color-surface-secondary);
    border: 2px dashed var(--color-border-default);
    border-radius: var(--radius-xl);
  }

  .empty-icon {
    font-size: 3.5rem;
    margin-bottom: 1rem;
    opacity: 0.5;
    animation: float 3s var(--ease-in-out) infinite;
  }

  @keyframes float {
    0%,
    100% {
      transform: translateY(0);
    }
    50% {
      transform: translateY(-8px);
    }
  }

  .empty-title {
    font-family: var(--font-display);
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: 0.375rem;
  }

  .empty-desc {
    font-size: 0.875rem;
    color: var(--color-text-muted);
  }

  /* ═══════════════════════════════════════════════════════════════════════════
     🇯🇵 JAPAN TAB — Dedicated Japanese LLM / AI section
     ═══════════════════════════════════════════════════════════════════════════ */

  .japan-pill-nav {
    background: linear-gradient(
      135deg,
      rgb(200 80 80 / 0.08) 0%,
      rgb(200 168 78 / 0.05) 50%,
      var(--color-surface-secondary) 100%
    );
    border-color: rgb(200 80 80 / 0.18);
    flex-direction: column;
    gap: 0.5rem;
    padding: 0;
    overflow: visible;
  }

  .japan-banner {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    padding: 0.75rem 1.25rem;
    border-bottom: 1px solid rgb(200 80 80 / 0.15);
    margin-bottom: 0.25rem;
  }

  .japan-banner-flag {
    font-size: 1.5rem;
  }

  .japan-banner-label {
    font-family: var(--font-display);
    font-size: 0.8125rem;
    font-weight: 700;
    color: var(--color-text-primary);
    letter-spacing: 0.01em;
  }

  .japan-banner-count {
    margin-left: auto;
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    color: var(--color-text-muted);
    padding: 0.25rem 0.625rem;
    background: var(--color-surface-base);
    border-radius: var(--radius-full);
    border: 1px solid var(--color-border-subtle);
  }

  .japan-pill {
    margin: 0 0.625rem;
  }

  .japan-pill:last-of-type {
    margin-bottom: 0.75rem;
  }

  .japan-pill.active {
    background: linear-gradient(
      135deg,
      rgb(200 80 80) 0%,
      rgb(180 60 60) 100%
    );
    border-color: transparent;
    box-shadow: 0 0 0 1px rgb(200 80 80 / 0.2), 0 12px 32px rgb(200 80 80 / 0.16);
  }

  .japan-pill.active .pill-count {
    background: rgb(255 255 255 / 0.25);
    border-color: transparent;
    color: #fff;
  }

  .japan-badge {
    background: rgb(200 80 80 / 0.14);
    color: #e8a0a0;
    border-color: rgb(200 80 80 / 0.28);
  }
</style>
