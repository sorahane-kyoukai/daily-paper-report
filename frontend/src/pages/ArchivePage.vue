<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useDigestStore } from '@/stores/digest'

const digestStore = useDigestStore()

const isLoading = computed(() => digestStore.isLoading)
const archiveDates = computed(() => digestStore.archiveDates)

// Fetch data on mount if not already loaded
onMounted(async () => {
  if (!digestStore.hasData) {
    await digestStore.fetchDigest()
  }
})

// Format date for display (YYYY-MM-DD -> more readable format)
const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

// Check if a date is today (current run date)
const isToday = (dateStr: string): boolean => {
  return dateStr === digestStore.runDate
}
</script>

<template>
  <div data-testid="archive-page">
    <div class="mb-8 animate-fade-in-up">
      <h1 class="text-2xl font-bold text-[var(--color-text-primary)] tracking-tight">
        Archive
      </h1>
      <p class="text-[var(--color-text-muted)] mt-1">
        Browse past digests
      </p>
    </div>

    <!-- Loading State -->
    <div
      v-if="isLoading"
      class="space-y-3"
    >
      <div
        v-for="i in 5"
        :key="i"
        class="h-14 skeleton rounded-lg"
      />
    </div>

    <!-- Archive List -->
    <div
      v-else-if="archiveDates.length > 0"
      class="space-y-2"
    >
      <RouterLink
        v-for="date in archiveDates"
        :key="date"
        :to="`/day/${date}`"
        class="archive-item group"
        :class="{ 'archive-item--today': isToday(date) }"
      >
        <div class="flex items-center gap-3">
          <span class="archive-date-icon">
            {{ isToday(date) ? '📌' : '📄' }}
          </span>
          <div>
            <span class="archive-date">{{ date }}</span>
            <span class="archive-date-formatted">{{ formatDate(date) }}</span>
          </div>
        </div>
        <span
          v-if="isToday(date)"
          class="today-badge"
        >
          Today
        </span>
        <svg
          class="archive-arrow"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M9 5l7 7-7 7"
          />
        </svg>
      </RouterLink>
    </div>

    <!-- Empty State -->
    <div
      v-else
      class="flex flex-col items-center justify-center py-20 bg-[var(--color-surface-secondary)] rounded-xl border border-dashed border-[var(--color-border-default)] animate-fade-in-scale transition-all duration-[var(--duration-base)] hover:border-[var(--color-border-strong)]"
    >
      <span
        class="text-5xl mb-4 animate-float"
        aria-hidden="true"
      >📚</span>
      <p class="text-[var(--color-text-secondary)] font-medium">
        No archived digests available
      </p>
      <p class="text-sm text-[var(--color-text-muted)] mt-1">
        Past digests will appear here after the first run
      </p>
    </div>
  </div>
</template>

<style scoped>
.archive-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  background: var(--color-surface-primary);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  text-decoration: none;
  transition: all var(--duration-base) var(--ease-out);
}

.archive-item:hover {
  background: var(--color-surface-secondary);
  border-color: var(--color-border-strong);
  transform: translateX(4px);
}

.archive-item--today {
  border-color: var(--color-accent-highlight);
  background: color-mix(in srgb, var(--color-accent-highlight) 5%, var(--color-surface-primary));
}

.archive-item--today:hover {
  background: color-mix(in srgb, var(--color-accent-highlight) 10%, var(--color-surface-primary));
}

.archive-date-icon {
  font-size: 1.25rem;
}

.archive-date {
  display: block;
  font-family: var(--font-mono);
  font-weight: 500;
  color: var(--color-text-primary);
  font-size: 0.9375rem;
}

.archive-date-formatted {
  display: block;
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  margin-top: 0.125rem;
}

.today-badge {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-accent-highlight);
  background: var(--color-accent-highlight-light);
  padding: 0.25rem 0.625rem;
  border-radius: var(--radius-full);
}

.archive-arrow {
  width: 1.25rem;
  height: 1.25rem;
  color: var(--color-text-muted);
  opacity: 0;
  transform: translateX(-4px);
  transition: all var(--duration-base) var(--ease-out);
}

.archive-item:hover .archive-arrow {
  opacity: 1;
  transform: translateX(0);
}
</style>
