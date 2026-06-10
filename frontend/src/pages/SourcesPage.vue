<script setup lang="ts">
  import { computed, ref, onMounted } from 'vue'
  import { useDigestStore } from '@/stores/digest'

  const digestStore = useDigestStore()
  const sources = computed(() => digestStore.sourcesStatus)

  // Fetch data on mount if not already loaded
  onMounted(async () => {
    if (!digestStore.hasData) {
      await digestStore.fetchDigest()
    }
  })

  // Filter state
  type StatusFilter = 'all' | 'has_update' | 'no_change' | 'failed'
  const activeFilter = ref<StatusFilter>('all')

  const filters: { id: StatusFilter; label: string; icon: string }[] = [
    { id: 'all', label: 'All', icon: '📋' },
    { id: 'has_update', label: 'New Data', icon: '✨' },
    { id: 'no_change', label: 'Synced', icon: '✓' },
    { id: 'failed', label: 'Failed', icon: '⚠️' },
  ]

  // Filter counts
  const filterCounts = computed(() => {
    const counts = { all: 0, has_update: 0, no_change: 0, failed: 0 }
    sources.value.forEach(source => {
      counts.all++
      if (source.status === 'HAS_UPDATE') counts.has_update++
      else if (source.status === 'NO_UPDATE') counts.no_change++
      else if (source.status === 'FETCH_FAILED' || source.status === 'PARSE_FAILED') counts.failed++
    })
    return counts
  })

  // Filtered sources
  const filteredSources = computed(() => {
    if (activeFilter.value === 'all') return sources.value
    return sources.value.filter(source => {
      switch (activeFilter.value) {
        case 'has_update':
          return source.status === 'HAS_UPDATE'
        case 'no_change':
          return source.status === 'NO_UPDATE'
        case 'failed':
          return source.status === 'FETCH_FAILED' || source.status === 'PARSE_FAILED'
        default:
          return true
      }
    })
  })


  // Get story count per source
  const storiesBySource = computed(() => digestStore.allStoriesBySource)

  // Determine if source has papers (for color differentiation)
  const sourceHasPapers = (sourceId: string): boolean => {
    return (storiesBySource.value[sourceId]?.length ?? 0) > 0
  }

  const getStatusLabel = (status: string, sourceId: string): string => {
    switch (status) {
      case 'HAS_UPDATE':
        return 'New Data'
      case 'NO_UPDATE':
        // Show "Synced" if has papers, "No Change" if empty
        return sourceHasPapers(sourceId) ? 'Synced' : 'No Change'
      case 'FETCH_FAILED':
        return 'Fetch Failed'
      case 'PARSE_FAILED':
        return 'Parse Failed'
      default:
        return status
    }
  }

  const getStatusColor = (status: string, sourceId: string): string => {
    switch (status) {
      case 'HAS_UPDATE':
        return 'status-badge status-badge--success'
      case 'NO_UPDATE':
        // Green if has papers, gray if empty
        return sourceHasPapers(sourceId)
          ? 'status-badge status-badge--synced'
          : 'status-badge status-badge--muted'
      case 'FETCH_FAILED':
      case 'PARSE_FAILED':
        return 'status-badge status-badge--error'
      default:
        return 'status-badge status-badge--warning'
    }
  }

  const getRowClass = (status: string, sourceId: string): string => {
    switch (status) {
      case 'HAS_UPDATE':
        return 'source-row source-row--success'
      case 'NO_UPDATE':
        return sourceHasPapers(sourceId)
          ? 'source-row source-row--synced'
          : 'source-row source-row--muted'
      case 'FETCH_FAILED':
      case 'PARSE_FAILED':
        return 'source-row source-row--error'
      default:
        return 'source-row source-row--warning'
    }
  }

  const getStatusIcon = (status: string): string => {
    switch (status) {
      case 'HAS_UPDATE':
        return '✓'
      case 'NO_UPDATE':
        return '–'
      case 'FETCH_FAILED':
      case 'PARSE_FAILED':
        return '✕'
      default:
        return '?'
    }
  }

</script>

<template>
  <div
    data-testid="sources-page"
    class="sources-page"
  >
    <!-- Header -->
    <header class="sources-header">
      <div class="header-title-area">
        <h1 class="sources-title">
          <span class="title-icon">📡</span>
          Sources
        </h1>
        <p class="sources-subtitle">
          Data sources and their current status
        </p>
      </div>

      <!-- Summary Stats -->
      <div
        v-if="sources.length > 0"
        class="summary-stats"
      >
        <div class="summary-stat summary-stat--success">
          <span class="summary-stat-value">{{ filterCounts.has_update }}</span>
          <span class="summary-stat-label">New Data</span>
        </div>
        <div class="summary-stat summary-stat--synced">
          <span class="summary-stat-value">{{ filterCounts.no_change }}</span>
          <span class="summary-stat-label">Synced</span>
        </div>
        <div class="summary-stat summary-stat--error">
          <span class="summary-stat-value">{{ filterCounts.failed }}</span>
          <span class="summary-stat-label">Failed</span>
        </div>
      </div>
    </header>

    <!-- Filter Bar -->
    <nav
      v-if="sources.length > 0"
      class="filter-bar"
    >
      <div class="filter-track">
        <button
          v-for="filter in filters"
          :key="filter.id"
          class="filter-btn"
          :class="{
            'filter-btn--active': activeFilter === filter.id,
            'filter-btn--success': filter.id === 'has_update',
            'filter-btn--muted': filter.id === 'no_change',
            'filter-btn--error': filter.id === 'failed',
          }"
          @click="activeFilter = filter.id"
        >
          <span class="filter-icon">{{ filter.icon }}</span>
          <span class="filter-label">{{ filter.label }}</span>
          <span class="filter-count">{{ filterCounts[filter.id] }}</span>
        </button>
      </div>
    </nav>

    <!-- Sources List -->
    <div
      v-if="filteredSources.length > 0"
      class="sources-list"
    >
      <TransitionGroup name="source-list">
        <div
          v-for="(source, index) in filteredSources"
          :key="source.source_id"
          :class="getRowClass(source.status, source.source_id)"
          :style="{ '--idx': index }"
          :data-testid="`source-card-${source.source_id}`"
        >
          <!-- Status Indicator -->
          <div class="status-indicator">
            <span class="status-icon">{{ getStatusIcon(source.status) }}</span>
          </div>

          <!-- Source Info -->
          <div class="source-info">
            <div class="source-header">
              <h3 class="source-name">
                {{ source.name }}
              </h3>
              <span :class="getStatusColor(source.status, source.source_id)">
                {{ getStatusLabel(source.status, source.source_id) }}
              </span>
            </div>

            <div class="source-meta">
              <span class="method-badge">{{ source.method }}</span>
              <span class="meta-divider">·</span>
              <span class="tier-label">Tier {{ source.tier + 1 }}</span>
              <template v-if="storiesBySource[source.source_id]?.length > 0">
                <span class="meta-divider">·</span>
                <span class="papers-count">{{ storiesBySource[source.source_id].length }} papers</span>
              </template>
              <template v-if="source.items_new > 0">
                <span class="meta-divider">·</span>
                <span class="new-items">+{{ source.items_new }} new</span>
              </template>
            </div>

            <p
              v-if="source.reason_text"
              class="source-reason"
            >
              {{ source.reason_text }}
            </p>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <!-- Empty State for Filter -->
    <div
      v-else-if="sources.length > 0 && filteredSources.length === 0"
      class="empty-filter-state"
    >
      <span class="empty-icon">🔍</span>
      <p class="empty-text">
        No sources match this filter
      </p>
      <button
        class="reset-filter-btn"
        @click="activeFilter = 'all'"
      >
        Show All Sources
      </button>
    </div>

    <!-- Empty State -->
    <div
      v-else
      class="empty-state"
    >
      <span
        class="empty-state-icon"
        aria-hidden="true"
      >📡</span>
      <p class="empty-state-title">
        No source data available
      </p>
      <p class="empty-state-desc">
        Source status will appear here after the next data refresh.
      </p>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   SOURCES PAGE - Premium Data Status View
   ═══════════════════════════════════════════════════════════════════════════ */

.sources-page {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  animation: pageReveal 0.5s var(--ease-out) both;
}

@keyframes pageReveal {
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

.sources-header {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid var(--color-border-subtle);
}

@media (min-width: 768px) {
  .sources-header {
    flex-direction: row;
    align-items: flex-start;
    justify-content: space-between;
  }
}

.header-title-area {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sources-title {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: 0;
}

.title-icon {
  font-size: 1.25rem;
}

.sources-subtitle {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

/* Summary Stats */
.summary-stats {
  display: flex;
  gap: 0.75rem;
}

.summary-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.75rem 1.25rem;
  background: var(--color-surface-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  min-width: 5rem;
  transition: all var(--duration-fast) var(--ease-out);
}

.summary-stat:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.summary-stat--success {
  border-left: 3px solid var(--color-accent-success);
}

.summary-stat--synced {
  border-left: 3px solid var(--color-accent-success);
}

.summary-stat--error {
  border-left: 3px solid var(--color-accent-error);
}

.summary-stat-value {
  font-family: var(--font-mono);
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1;
}

.summary-stat--success .summary-stat-value { color: var(--color-accent-success); }
.summary-stat--synced .summary-stat-value { color: var(--color-accent-success); }
.summary-stat--error .summary-stat-value { color: var(--color-accent-error); }

.summary-stat-label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0;
  margin-top: 0.25rem;
}

/* ═══════════════════════════════════════════════════════════════════════════
   FILTER BAR
   ═══════════════════════════════════════════════════════════════════════════ */

.filter-bar {
  background: var(--color-surface-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  padding: 0.5rem;
}

.filter-track {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.filter-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  font-family: var(--font-display);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-tertiary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.filter-btn:hover:not(.filter-btn--active) {
  color: var(--color-text-secondary);
  background: var(--color-surface-overlay);
}

.filter-btn--active {
  color: var(--color-text-primary);
  background: var(--color-surface-primary);
  border-color: var(--color-border-default);
  box-shadow: var(--shadow-sm);
  font-weight: 600;
}

/* Colored active states */
.filter-btn--active.filter-btn--success {
  border-color: rgb(52 211 153 / 0.4);
  background: linear-gradient(135deg, rgb(52 211 153 / 0.1) 0%, var(--color-surface-primary) 100%);
}

.filter-btn--active.filter-btn--error {
  border-color: rgb(248 113 113 / 0.4);
  background: linear-gradient(135deg, rgb(248 113 113 / 0.1) 0%, var(--color-surface-primary) 100%);
}

.filter-icon {
  font-size: 1rem;
}

.filter-label {
  white-space: nowrap;
}

.filter-count {
  padding: 0.125rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  background: var(--color-surface-overlay);
  border-radius: var(--radius-full);
  transition: all var(--duration-fast) var(--ease-out);
}

.filter-btn--active .filter-count {
  background: var(--color-accent-primary);
  color: #fff;
}

.filter-btn--active.filter-btn--success .filter-count {
  background: var(--color-accent-success);
}

.filter-btn--active.filter-btn--error .filter-count {
  background: var(--color-accent-error);
}

/* ═══════════════════════════════════════════════════════════════════════════
   SOURCES LIST
   ═══════════════════════════════════════════════════════════════════════════ */

.sources-list {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

/* Source Row */
.source-row {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1rem 1.25rem;
  background: var(--color-surface-primary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  transition: all var(--duration-base) var(--ease-out);
  animation: rowReveal 0.35s var(--ease-out) both;
  animation-delay: calc(var(--idx, 0) * 30ms);
}

@keyframes rowReveal {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.source-row:hover {
  border-color: var(--color-border-default);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

/* Row Status Variants */
.source-row--success {
  border-left: 3px solid var(--color-accent-success);
  background: linear-gradient(90deg, rgb(52 211 153 / 0.04) 0%, var(--color-surface-primary) 20%);
}

.source-row--success:hover {
  background: linear-gradient(90deg, rgb(52 211 153 / 0.08) 0%, var(--color-surface-primary) 30%);
}

.source-row--synced {
  border-left: 3px solid var(--color-accent-success);
  background: linear-gradient(90deg, rgb(52 211 153 / 0.03) 0%, var(--color-surface-primary) 15%);
}

.source-row--synced:hover {
  background: linear-gradient(90deg, rgb(52 211 153 / 0.06) 0%, var(--color-surface-primary) 25%);
}

.source-row--muted {
  border-left: 3px solid var(--color-text-muted);
  opacity: 0.75;
}

.source-row--muted:hover {
  opacity: 0.9;
}

.source-row--error {
  border-left: 3px solid var(--color-accent-error);
  background: linear-gradient(90deg, rgb(248 113 113 / 0.06) 0%, var(--color-surface-primary) 20%);
}

.source-row--error:hover {
  background: linear-gradient(90deg, rgb(248 113 113 / 0.1) 0%, var(--color-surface-primary) 30%);
  border-color: rgb(248 113 113 / 0.3);
}

.source-row--warning {
  border-left: 3px solid var(--color-accent-warning);
  background: linear-gradient(90deg, rgb(216 189 122 / 0.07) 0%, var(--color-surface-primary) 20%);
}

/* Status Indicator */
.status-indicator {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: var(--radius-md);
  background: var(--color-surface-secondary);
  border: 1px solid var(--color-border-subtle);
  transition: all var(--duration-fast) var(--ease-out);
}

.source-row--success .status-indicator {
  background: rgb(52 211 153 / 0.15);
  border-color: rgb(52 211 153 / 0.3);
  color: var(--color-accent-success);
}

.source-row--synced .status-indicator {
  background: rgb(52 211 153 / 0.1);
  border-color: rgb(52 211 153 / 0.2);
  color: var(--color-accent-success);
}

.source-row--error .status-indicator {
  background: rgb(248 113 113 / 0.15);
  border-color: rgb(248 113 113 / 0.3);
  color: var(--color-accent-error);
}

.source-row--muted .status-indicator {
  color: var(--color-text-muted);
}

.status-icon {
  font-size: 0.875rem;
  font-weight: 700;
}

/* Source Info */
.source-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.source-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.625rem;
}

.source-name {
  font-family: var(--font-display);
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* Status Badge */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  font-size: 0.6875rem;
  font-weight: 700;
  border-radius: var(--radius-full);
  text-transform: uppercase;
  letter-spacing: 0;
  transition: all var(--duration-fast) var(--ease-out);
}

.status-badge--success {
  background: rgb(52 211 153 / 0.15);
  color: var(--color-accent-success);
  border: 1px solid rgb(52 211 153 / 0.3);
}

.status-badge--synced {
  background: rgb(52 211 153 / 0.12);
  color: var(--color-accent-success);
  border: 1px solid rgb(52 211 153 / 0.25);
}

.status-badge--muted {
  background: var(--color-surface-secondary);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-subtle);
}

.status-badge--error {
  background: rgb(248 113 113 / 0.15);
  color: var(--color-accent-error);
  border: 1px solid rgb(248 113 113 / 0.3);
}

.status-badge--warning {
  background: rgb(216 189 122 / 0.15);
  color: var(--color-accent-warning);
  border: 1px solid rgb(216 189 122 / 0.3);
}

/* Source Meta */
.source-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.method-badge {
  padding: 0.1875rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 600;
  font-family: var(--font-mono);
  background: var(--color-surface-secondary);
  color: var(--color-text-tertiary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-subtle);
  transition: all var(--duration-fast) var(--ease-out);
}

.source-row:hover .method-badge {
  background: var(--color-surface-overlay);
  border-color: var(--color-border-default);
}

.meta-divider {
  color: var(--color-border-strong);
}

.tier-label {
  font-size: 0.75rem;
}

.papers-count {
  color: var(--color-accent-primary);
  font-weight: 600;
}

.new-items {
  color: var(--color-accent-success);
  font-weight: 600;
}

.source-reason {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  line-height: 1.5;
  padding-top: 0.25rem;
}

.source-row--error .source-reason {
  color: var(--color-accent-error);
  opacity: 0.9;
}

/* ═══════════════════════════════════════════════════════════════════════════
   EMPTY STATES
   ═══════════════════════════════════════════════════════════════════════════ */

.empty-filter-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 2rem;
  text-align: center;
  background: var(--color-surface-secondary);
  border: 1px dashed var(--color-border-default);
  border-radius: var(--radius-xl);
}

.empty-icon {
  font-size: 2.5rem;
  margin-bottom: 0.75rem;
  opacity: 0.5;
}

.empty-text {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  margin-bottom: 1rem;
}

.reset-filter-btn {
  padding: 0.5rem 1rem;
  font-family: var(--font-display);
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-accent-primary);
  background: transparent;
  border: 1px solid var(--color-accent-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.reset-filter-btn:hover {
  background: var(--color-accent-primary);
  color: #fff;
}

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

.empty-state-icon {
  font-size: 3.5rem;
  margin-bottom: 1rem;
  opacity: 0.5;
  animation: float 3s var(--ease-in-out) infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.empty-state-title {
  font-family: var(--font-display);
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}

.empty-state-desc {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

/* ═══════════════════════════════════════════════════════════════════════════
   TRANSITION GROUP
   ═══════════════════════════════════════════════════════════════════════════ */

.source-list-enter-active,
.source-list-leave-active {
  transition: all var(--duration-slow) var(--ease-out);
}

.source-list-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.source-list-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.source-list-move {
  transition: transform var(--duration-slow) var(--ease-out);
}
</style>
