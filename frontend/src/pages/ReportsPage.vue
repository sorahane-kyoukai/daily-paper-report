<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import StoryCard from '@/components/ui/StoryCard.vue'
  import { matchesSearch, useSearch } from '@/shared/composables/useSearch'
  import type {
    ReportDigest,
    ReportIndex,
    ReportIndexEntry,
    ReportType,
    Story,
  } from '@/types/digest'

  const route = useRoute()
  const { searchQuery, isSearchFocused, clearSearch, setFocus } = useSearch()

  const report = ref<ReportDigest | null>(null)
  const reportIndex = ref<ReportIndex | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const routeReportType = computed<ReportType | null>(() => {
    const value = route.params.type
    if (value === 'weekly' || value === 'monthly') return value
    return null
  })

  const routePeriod = computed(() => {
    const value = route.params.period
    return typeof value === 'string' ? value : null
  })

  const isDetailMode = computed(() => routeReportType.value !== null && routePeriod.value !== null)

  const latestEntries = computed(() => {
    const index = reportIndex.value
    if (!index) return []

    const latest: ReportIndexEntry[] = []
    const weekly = index.weekly.find((entry) => entry.period_id === index.latest.weekly)
    const monthly = index.monthly.find((entry) => entry.period_id === index.latest.monthly)
    if (weekly) latest.push(weekly)
    if (monthly) latest.push(monthly)
    return latest
  })

  const allEntries = computed(() => {
    const index = reportIndex.value
    if (!index) return []
    return [...index.weekly, ...index.monthly]
      .filter((e) => e.period_start)
      .sort((a, b) => b.period_start.localeCompare(a.period_start))
  })

  const archiveEntries = computed(() => {
    const latestKeys = new Set(
      latestEntries.value.map((entry) => `${entry.report_type}:${entry.period_id}`),
    )
    return allEntries.value.filter(
      (entry) => !latestKeys.has(`${entry.report_type}:${entry.period_id}`),
    )
  })

  const blogRecommendations = computed(() => report.value?.blog_recommendations ?? [])

  const filteredPaperRecommendations = computed(() => {
    const recommendations = report.value?.recommendations ?? []
    const query = searchQuery.value.trim()
    if (!query) return recommendations
    return recommendations.filter((story: Story) => matchesSearch(story, query))
  })

  const filteredBlogRecommendations = computed(() => {
    const recommendations = blogRecommendations.value
    const query = searchQuery.value.trim()
    if (!query) return recommendations
    return recommendations.filter((story: Story) => matchesSearch(story, query))
  })

  const filteredReportItemCount = computed(
    () => filteredPaperRecommendations.value.length + filteredBlogRecommendations.value.length,
  )

  const reportItemCount = computed(
    () => (report.value?.recommendations.length ?? 0) + blogRecommendations.value.length,
  )

  const reportStats = computed(() => {
    const current = report.value
    if (!current) return []
    return [
      { label: 'Papers', value: current.recommendations.length.toString(), tone: 'paper' },
      { label: 'Blogs', value: blogRecommendations.value.length.toString(), tone: 'blog' },
      { label: 'Covered', value: current.covered_dates.length.toString(), tone: 'success' },
      { label: 'Missing', value: current.missing_dates.length.toString(), tone: 'warning' },
      { label: 'Considered', value: current.stories_considered.toString(), tone: 'muted' },
    ]
  })

  const reportIndexStats = computed(() => {
    const index = reportIndex.value
    const weekly = index?.weekly ?? []
    const monthly = index?.monthly ?? []
    const all = [...weekly, ...monthly]

    return [
      { label: 'Reports', value: all.length.toString(), detail: 'weekly + monthly' },
      {
        label: 'Papers',
        value: all
          .reduce((total, entry) => total + entry.recommendation_count, 0)
          .toLocaleString('en-US'),
        detail: 'recommended',
      },
      {
        label: 'Blogs',
        value: all
          .reduce((total, entry) => total + (entry.blog_recommendation_count ?? 0), 0)
          .toLocaleString('en-US'),
        detail: 'recommended',
      },
      {
        label: 'Weekly',
        value: weekly.length.toString(),
        detail: index?.latest.weekly ?? 'none',
      },
      {
        label: 'Monthly',
        value: monthly.length.toString(),
        detail: index?.latest.monthly ?? 'none',
      },
    ]
  })

  const reportTypeLabel = computed(() => {
    if (report.value?.report_type === 'weekly') return 'Weekly'
    if (report.value?.report_type === 'monthly') return 'Monthly'
    return 'Reports'
  })

  const reportPeriodLabel = computed(() => {
    const current = report.value
    if (!current) return null
    return `${formatDate(current.period_start)} - ${formatDate(current.period_end)}`
  })

  const generatedAtLabel = computed(() => {
    const dateText = report.value?.generated_at ?? reportIndex.value?.generated_at
    if (!dateText) return null
    return formatGeneratedAt(dateText)
  })

  const hasGeneratedReports = computed(
    () => latestEntries.value.length > 0 || archiveEntries.value.length > 0,
  )

  async function loadReports(): Promise<void> {
    isLoading.value = true
    error.value = null
    report.value = null

    try {
      const indexResponse = await fetch('/api/reports/index.json')
      if (indexResponse.ok) {
        reportIndex.value = await indexResponse.json()
      } else if (indexResponse.status === 404) {
        reportIndex.value = null
      } else {
        throw new Error(`Failed to fetch reports index: ${indexResponse.status}`)
      }

      if (isDetailMode.value && routeReportType.value && routePeriod.value) {
        const response = await fetch(
          `/api/reports/${routeReportType.value}/${routePeriod.value}.json`,
        )
        if (!response.ok) {
          throw new Error(`Failed to fetch report: ${response.status} ${response.statusText}`)
        }
        report.value = await response.json()
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown report loading error'
    } finally {
      isLoading.value = false
    }
  }

  function formatDate(dateText: string): string {
    return new Date(`${dateText}T00:00:00`).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }

  function formatGeneratedAt(dateText: string): string {
    return new Date(dateText).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  }

  function entryRoute(entry: ReportIndexEntry): string {
    return `/reports/${entry.report_type}/${entry.period_id}`
  }

  function reportTypeName(type: ReportType): string {
    return type === 'weekly' ? 'Weekly' : 'Monthly'
  }

  onMounted(loadReports)
  watch(() => route.fullPath, loadReports)
</script>

<template>
  <div class="reports-page">
    <header class="reports-hero">
      <div class="reports-hero__copy">
        <p class="reports-kicker">
          {{ reportTypeLabel }}
        </p>
        <h1 class="reports-title">
          {{ report?.title ?? 'AI Paper Reports' }}
        </h1>
        <p v-if="report?.summary" class="reports-summary">
          {{ report.summary }}
        </p>
        <p v-if="reportPeriodLabel" class="reports-period">
          {{ reportPeriodLabel }}
        </p>
        <p v-else class="reports-period">Weekly and monthly research selections</p>
      </div>

      <div class="reports-hero__meta">
        <span v-if="generatedAtLabel" class="reports-generated">
          Updated {{ generatedAtLabel }}
        </span>
        <RouterLink v-if="isDetailMode" to="/reports" class="reports-back-link">
          All reports
        </RouterLink>
      </div>
    </header>

    <main v-if="isLoading" class="reports-loading" aria-live="polite">
      <div class="reports-loading__bar" />
      <div class="reports-loading__grid">
        <span
          v-for="index in 4"
          :key="index"
          class="reports-loading__line"
          :style="{ '--delay': `${index * 70}ms` }"
        />
      </div>
    </main>

    <main v-else-if="error" class="reports-error" role="alert">
      <span class="reports-status-dot reports-status-dot--error" />
      <div>
        <strong>Report data is unavailable</strong>
        <p>{{ error }}</p>
      </div>
    </main>

    <main v-else-if="report" class="report-detail">
      <section class="report-stats-grid">
        <article
          v-for="stat in reportStats"
          :key="stat.label"
          class="report-stat"
          :class="`report-stat--${stat.tone}`"
        >
          <span class="report-stat-value">{{ stat.value }}</span>
          <span class="report-stat-label">{{ stat.label }}</span>
        </article>
      </section>

      <section v-if="report.missing_dates.length > 0" class="report-warning">
        <span class="reports-status-dot reports-status-dot--warning" />
        <div>
          <strong
            >{{ report.missing_dates.length }} missing archive date{{
              report.missing_dates.length > 1 ? 's' : ''
            }}</strong
          >
          <span>{{ report.missing_dates.join(', ') }}</span>
        </div>
      </section>

      <section class="report-toolbar">
        <div class="report-search" :class="{ 'report-search--focused': isSearchFocused }">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            id="report-search"
            v-model="searchQuery"
            name="report-search"
            type="search"
            placeholder="Search report items..."
            aria-label="Search report items"
            @focus="setFocus(true)"
            @blur="setFocus(false)"
          />
          <button
            v-if="searchQuery"
            type="button"
            class="report-search__clear"
            aria-label="Clear search"
            @click="clearSearch"
          >
            Clear
          </button>
        </div>
        <span class="report-count">
          {{ filteredReportItemCount }} / {{ reportItemCount }}
        </span>
      </section>

      <section v-if="filteredPaperRecommendations.length > 0" class="report-section">
        <header class="report-section__header">
          <span>Papers</span>
          <small>{{ filteredPaperRecommendations.length }} selected</small>
        </header>
        <section class="report-paper-list">
          <TransitionGroup name="report-list">
            <StoryCard
              v-for="(story, index) in filteredPaperRecommendations"
              :key="story.story_id"
              :story="story"
              :rank="story.report_rank ?? index + 1"
              accent-type="papers"
              :show-entities="true"
              :show-categories="true"
              :show-source="true"
              :show-authors="true"
              :show-summary="true"
              :show-arxiv="true"
              :style="{ '--idx': index }"
            />
          </TransitionGroup>
        </section>
      </section>

      <section v-if="filteredBlogRecommendations.length > 0" class="report-section">
        <header class="report-section__header">
          <span>Blog Articles</span>
          <small>{{ filteredBlogRecommendations.length }} selected</small>
        </header>
        <section class="report-paper-list">
          <TransitionGroup name="report-list">
            <StoryCard
              v-for="(story, index) in filteredBlogRecommendations"
              :key="story.story_id"
              :story="story"
              :rank="story.report_rank ?? index + 1"
              accent-type="radar"
              :show-entities="true"
              :show-categories="true"
              :show-source="true"
              :show-authors="false"
              :show-summary="true"
              :show-arxiv="false"
              :style="{ '--idx': index }"
            />
          </TransitionGroup>
        </section>
      </section>

      <section v-if="reportItemCount > 0 && filteredReportItemCount === 0" class="reports-empty">
        <span class="reports-status-dot" />
        <div>
          <strong>No matching report items</strong>
          <p>Try a broader search across papers and blog articles.</p>
        </div>
      </section>
    </main>

    <main v-else class="reports-index">
      <section class="report-index-stats">
        <article v-for="stat in reportIndexStats" :key="stat.label" class="report-index-stat">
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
          <small>{{ stat.detail }}</small>
        </article>
      </section>

      <section v-if="latestEntries.length > 0" class="report-entry-grid">
        <RouterLink
          v-for="entry in latestEntries"
          :key="`${entry.report_type}-${entry.period_id}`"
          :to="entryRoute(entry)"
          class="report-entry report-entry--latest"
        >
          <span class="report-entry-type">{{ reportTypeName(entry.report_type) }}</span>
          <strong>{{ entry.title }}</strong>
          <p v-if="entry.summary" class="report-entry-summary">{{ entry.summary }}</p>
          <span class="report-entry-period">
            {{ formatDate(entry.period_start) }} - {{ formatDate(entry.period_end) }}
          </span>
          <span class="report-entry-foot">
            <small>{{ entry.recommendation_count }} papers</small>
            <small>{{ entry.blog_recommendation_count ?? 0 }} blogs</small>
            <small v-if="entry.missing_dates.length > 0">
              {{ entry.missing_dates.length }} missing
            </small>
          </span>
        </RouterLink>
      </section>

      <section v-if="archiveEntries.length > 0" class="report-archive-list">
        <header class="report-archive-list__header">
          <span>Archive</span>
          <small
            >{{ archiveEntries.length }} previous report{{
              archiveEntries.length === 1 ? '' : 's'
            }}</small
          >
        </header>
        <RouterLink
          v-for="entry in archiveEntries"
          :key="`${entry.report_type}-${entry.period_id}-archive`"
          :to="entryRoute(entry)"
          class="report-row"
        >
          <span class="report-row-type">{{ reportTypeName(entry.report_type) }}</span>
          <span class="report-row-title">{{ entry.title }}</span>
          <span v-if="entry.summary" class="report-row-summary">{{ entry.summary }}</span>
          <span class="report-row-meta">
            {{ entry.recommendation_count }} papers ·
            {{ entry.blog_recommendation_count ?? 0 }} blogs ·
            {{ formatGeneratedAt(entry.generated_at) }}
          </span>
        </RouterLink>
      </section>

      <section v-else-if="!hasGeneratedReports" class="reports-empty">
        <span class="reports-status-dot" />
        <div>
          <strong>No generated reports yet</strong>
          <p>The report list has no weekly or monthly entries.</p>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
  .reports-page {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .reports-hero {
    position: relative;
    display: flex;
    min-height: 10rem;
    align-items: stretch;
    justify-content: space-between;
    gap: 1.25rem;
    overflow: hidden;
    padding: 1.25rem;
    background:
      linear-gradient(135deg, rgb(216 189 122 / 0.1), transparent 38%),
      linear-gradient(100deg, var(--color-surface-secondary), var(--color-surface-primary));
    border: 1px solid var(--color-border-default);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
    animation: fade-in-up var(--duration-slow) var(--ease-out) both;
  }

  .reports-hero::before {
    content: '';
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
      linear-gradient(90deg, rgb(243 239 230 / 0.045) 1px, transparent 1px),
      linear-gradient(rgb(243 239 230 / 0.035) 1px, transparent 1px);
    background-size: 28px 28px;
    mask-image: linear-gradient(90deg, black, transparent 74%);
  }

  .reports-hero__copy,
  .reports-hero__meta {
    position: relative;
    z-index: 1;
  }

  .reports-hero__copy {
    display: flex;
    min-width: 0;
    flex-direction: column;
    justify-content: flex-end;
  }

  .reports-hero__meta {
    display: flex;
    flex-shrink: 0;
    flex-direction: column;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
  }

  .reports-kicker,
  .report-entry-type,
  .report-row-type,
  .report-stat-label {
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
    color: var(--color-accent-primary);
  }

  .reports-title {
    max-width: 50rem;
    margin-top: 0.35rem;
    font-size: clamp(1.75rem, 4vw, 3.15rem);
    letter-spacing: 0;
    text-wrap: balance;
  }

  .reports-summary {
    max-width: 44rem;
    margin-top: 0.7rem;
    color: var(--color-text-secondary);
    font-size: 0.98rem;
    line-height: 1.7;
    text-wrap: pretty;
  }

  .reports-period {
    margin-top: 0.5rem;
    color: var(--color-text-secondary);
    font-family: var(--font-mono);
    font-size: 0.86rem;
  }

  .reports-generated {
    max-width: 14rem;
    color: var(--color-text-muted);
    font-family: var(--font-mono);
    font-size: 0.72rem;
    text-align: right;
  }

  .reports-back-link {
    flex-shrink: 0;
    padding: 0.6rem 0.85rem;
    color: var(--color-text-primary);
    text-decoration: none;
    border: 1px solid var(--color-border-default);
    border-radius: var(--radius-md);
    background: rgb(243 239 230 / 0.04);
    transition:
      transform var(--duration-fast) var(--ease-out),
      border-color var(--duration-fast) var(--ease-out),
      background var(--duration-fast) var(--ease-out);
  }

  .reports-back-link:hover {
    border-color: var(--color-border-strong);
    background: rgb(243 239 230 / 0.07);
    transform: translateY(-1px);
  }

  .reports-back-link:active {
    transform: translateY(0) scale(0.98);
  }

  .reports-loading,
  .reports-error,
  .reports-empty {
    display: flex;
    min-height: 18rem;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: var(--color-text-secondary);
    background: var(--color-surface-primary);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-lg);
    animation: fade-in-up var(--duration-slow) var(--ease-out) both;
  }

  .reports-loading {
    flex-direction: column;
    align-items: stretch;
    gap: 1.25rem;
  }

  .reports-loading__bar,
  .reports-loading__line {
    border-radius: var(--radius-md);
    background: linear-gradient(
      90deg,
      var(--color-surface-secondary),
      var(--color-surface-overlay),
      var(--color-surface-secondary)
    );
    background-size: 220% 100%;
    animation: skeleton-shimmer 1.2s var(--ease-in-out) infinite;
  }

  .reports-loading__bar {
    width: min(22rem, 70%);
    height: 0.8rem;
  }

  .reports-loading__grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
  }

  .reports-loading__line {
    height: 5rem;
    animation-delay: var(--delay);
  }

  .reports-error,
  .reports-empty,
  .report-warning {
    justify-content: flex-start;
    gap: 0.8rem;
    text-align: left;
  }

  .reports-error,
  .report-warning {
    border-color: rgb(213 139 139 / 0.35);
    background: rgb(213 139 139 / 0.08);
    color: var(--color-text-primary);
  }

  .reports-error p,
  .reports-empty p {
    margin-top: 0.2rem;
    color: var(--color-text-tertiary);
  }

  .reports-status-dot {
    display: inline-flex;
    width: 0.6rem;
    height: 0.6rem;
    flex-shrink: 0;
    margin-top: 0.45rem;
    border-radius: var(--radius-full);
    background: var(--color-accent-primary);
    box-shadow: 0 0 0 0.35rem rgb(216 189 122 / 0.1);
  }

  .reports-status-dot--error {
    background: var(--color-accent-error);
    box-shadow: 0 0 0 0.35rem var(--color-accent-error-glow);
  }

  .reports-status-dot--warning {
    background: var(--color-accent-warning);
    box-shadow: 0 0 0 0.35rem rgb(214 168 109 / 0.12);
  }

  .report-detail,
  .reports-index {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .report-stats-grid,
  .report-entry-grid,
  .report-index-stats {
    display: grid;
    gap: 0.75rem;
  }

  .report-stats-grid,
  .report-index-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .report-entry-grid {
    grid-template-columns: 1fr;
  }

  @media (min-width: 760px) {
    .report-stats-grid,
    .report-index-stats {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    .report-entry-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  .report-stat,
  .report-index-stat,
  .report-entry,
  .report-row {
    background:
      linear-gradient(180deg, rgb(243 239 230 / 0.035), transparent), var(--color-surface-primary);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-xs);
  }

  .report-stat,
  .report-index-stat {
    position: relative;
    overflow: hidden;
    padding: 1rem;
    animation: fade-in-up var(--duration-slow) var(--ease-out) both;
  }

  .report-stat::after,
  .report-index-stat::after {
    content: '';
    position: absolute;
    inset: auto 0 0;
    height: 2px;
    background: var(--color-border-default);
  }

  .report-stat--paper::after {
    background: var(--color-section-papers);
  }

  .report-stat--blog::after {
    background: var(--color-section-radar);
  }

  .report-stat--success::after {
    background: var(--color-accent-success);
  }

  .report-stat--warning::after {
    background: var(--color-accent-warning);
  }

  .report-stat--muted::after {
    background: var(--color-text-muted);
  }

  .report-stat-value,
  .report-index-stat strong {
    display: block;
    color: var(--color-text-primary);
    font-family: var(--font-mono);
    font-size: 1.75rem;
    font-weight: 800;
    line-height: 1;
  }

  .report-index-stat {
    min-height: 6.5rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }

  .report-index-stat span,
  .report-index-stat small {
    color: var(--color-text-tertiary);
    font-size: 0.76rem;
  }

  .report-warning {
    display: flex;
    align-items: flex-start;
    padding: 0.875rem 1rem;
    border: 1px solid;
    border-radius: var(--radius-lg);
  }

  .report-warning span:not(.reports-status-dot) {
    display: block;
    margin-top: 0.2rem;
    color: var(--color-text-tertiary);
  }

  .report-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem;
    background: var(--color-surface-secondary);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-xs);
  }

  .report-search {
    display: flex;
    width: min(100%, 34rem);
    align-items: center;
    gap: 0.65rem;
    padding: 0.7rem 0.85rem;
    background: var(--color-surface-sunken);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-md);
    transition:
      border-color var(--duration-fast) var(--ease-out),
      box-shadow var(--duration-fast) var(--ease-out),
      background var(--duration-fast) var(--ease-out);
  }

  .report-search--focused {
    border-color: var(--color-accent-primary);
    box-shadow: 0 0 0 3px var(--color-accent-primary-glow);
  }

  .report-search svg {
    width: 1rem;
    height: 1rem;
    color: var(--color-text-muted);
  }

  .report-search input {
    width: 100%;
    color: var(--color-text-primary);
    background: transparent;
    border: none;
    outline: none;
  }

  .report-search__clear {
    padding: 0.3rem 0.5rem;
    color: var(--color-accent-primary-hover);
    font-size: 0.75rem;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    transition:
      color var(--duration-fast) var(--ease-out),
      background var(--duration-fast) var(--ease-out),
      transform var(--duration-fast) var(--ease-out);
  }

  .report-search__clear:hover {
    color: var(--color-text-inverse);
    background: var(--color-accent-primary);
    transform: translateY(-1px);
  }

  .report-search__clear:active {
    transform: translateY(0) scale(0.97);
  }

  .report-count {
    flex-shrink: 0;
    color: var(--color-text-tertiary);
    font-family: var(--font-mono);
  }

  .report-section {
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
  }

  .report-section__header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    padding-inline: 0.15rem;
  }

  .report-section__header span {
    color: var(--color-text-primary);
    font-size: 1rem;
    font-weight: 800;
  }

  .report-section__header small {
    color: var(--color-text-tertiary);
    font-family: var(--font-mono);
    font-size: 0.75rem;
  }

  .report-paper-list {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
  }

  .report-list-enter-active,
  .report-list-move {
    transition:
      opacity var(--duration-slow) var(--ease-out),
      transform var(--duration-slow) var(--ease-out);
  }

  .report-list-enter-from {
    opacity: 0;
    transform: translateY(10px);
  }

  .report-entry {
    position: relative;
    display: flex;
    min-height: 11rem;
    flex-direction: column;
    justify-content: space-between;
    gap: 0.65rem;
    overflow: hidden;
    padding: 1.25rem;
    color: inherit;
    text-decoration: none;
    transition:
      transform var(--duration-base) var(--ease-out),
      border-color var(--duration-base) var(--ease-out),
      box-shadow var(--duration-base) var(--ease-out),
      background var(--duration-base) var(--ease-out);
    animation: fade-in-up var(--duration-slow) var(--ease-out) both;
  }

  .report-entry::before {
    content: '';
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(135deg, rgb(216 189 122 / 0.1), transparent 45%);
    opacity: 0;
    transition: opacity var(--duration-base) var(--ease-out);
  }

  .report-entry:hover,
  .report-row:hover {
    border-color: var(--color-accent-primary);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
  }

  .report-entry:hover::before {
    opacity: 1;
  }

  .report-entry:active,
  .report-row:active {
    transform: translateY(0) scale(0.99);
  }

  .report-entry strong {
    position: relative;
    color: var(--color-text-primary);
    font-size: 1.05rem;
    line-height: 1.45;
  }

  .report-entry-summary {
    position: relative;
    display: -webkit-box;
    overflow: hidden;
    margin: 0;
    color: var(--color-text-secondary);
    font-size: 0.86rem;
    line-height: 1.6;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
  }

  .report-entry span,
  .report-entry small,
  .report-row-meta {
    color: var(--color-text-tertiary);
  }

  .report-entry-type,
  .report-entry-period,
  .report-entry-foot {
    position: relative;
  }

  .report-entry-foot {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .report-archive-list {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    animation: fade-in-up var(--duration-slow) var(--ease-out) both;
  }

  .report-archive-list__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    color: var(--color-text-secondary);
    font-weight: 700;
  }

  .report-archive-list__header small {
    color: var(--color-text-muted);
    font-weight: 500;
  }

  .report-row {
    display: grid;
    grid-template-columns: 5.5rem 1fr;
    gap: 0.35rem 1rem;
    padding: 0.9rem 1rem;
    color: inherit;
    text-decoration: none;
    transition:
      transform var(--duration-base) var(--ease-out),
      border-color var(--duration-base) var(--ease-out),
      box-shadow var(--duration-base) var(--ease-out);
  }

  .report-row-title {
    color: var(--color-text-primary);
    font-weight: 700;
  }

  .report-row-meta {
    grid-column: 2;
    font-size: 0.8125rem;
  }

  .report-row-summary {
    grid-column: 2;
    color: var(--color-text-tertiary);
    font-size: 0.82rem;
    line-height: 1.5;
  }

  @media (max-width: 640px) {
    .reports-hero,
    .report-toolbar {
      align-items: stretch;
      flex-direction: column;
    }

    .reports-hero__meta {
      align-items: flex-start;
    }

    .reports-generated {
      max-width: none;
      text-align: left;
    }

    .report-index-stats,
    .reports-loading__grid {
      grid-template-columns: 1fr;
    }

    .report-row {
      grid-template-columns: 1fr;
    }

    .report-row-meta {
      grid-column: auto;
    }

    .report-row-summary {
      grid-column: auto;
    }
  }
</style>
