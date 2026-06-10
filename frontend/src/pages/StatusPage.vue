<script setup lang="ts">
  import { computed, onMounted } from 'vue'
  import { useDigestStore } from '@/stores/digest'

  const digestStore = useDigestStore()
  const runInfo = computed(() => digestStore.runInfo)
  const sourcesStatus = computed(() => digestStore.sourcesStatus)

  // Fetch data on mount if not already loaded
  onMounted(async () => {
    if (!digestStore.hasData) {
      await digestStore.fetchDigest()
    }
  })

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return 'N/A'
    return new Date(dateStr).toLocaleString()
  }

  const healthySources = computed(() => {
    return sourcesStatus.value.filter((s) => s.status === 'HAS_UPDATE' || s.status === 'NO_UPDATE')
      .length
  })

  const failedSources = computed(() => {
    return sourcesStatus.value.filter(
      (s) => s.status === 'FETCH_FAILED' || s.status === 'PARSE_FAILED',
    ).length
  })
</script>

<template>
  <div data-testid="status-page">
    <div class="mb-8 animate-fade-in-up">
      <h1 class="text-2xl font-bold text-[var(--color-text-primary)] tracking-tight">
        Status
      </h1>
      <p class="text-[var(--color-text-muted)] mt-1">
        System health and pipeline status
      </p>
    </div>

    <div
      v-if="runInfo"
      class="space-y-6"
    >
      <!-- Overall Status -->
      <div class="card p-6 animate-fade-in-up hover-lift">
        <div class="flex items-center gap-3 mb-4">
          <div
            class="w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-[var(--duration-base)] ease-[var(--ease-out)]"
            :class="
              runInfo.success
                ? 'bg-[var(--color-success)]/10 text-[var(--color-success)]'
                : 'bg-[var(--color-error)]/10 text-[var(--color-error)]'
            "
          >
            <span class="text-2xl animate-scale-in">{{ runInfo.success ? '✓' : '✗' }}</span>
          </div>
          <div>
            <h2 class="text-lg font-semibold text-[var(--color-text-primary)]">
              {{ runInfo.success ? 'System Healthy' : 'Issues Detected' }}
            </h2>
            <p class="text-sm text-[var(--color-text-muted)]">
              Last run: {{ formatDate(runInfo.finished_at) }}
            </p>
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div
            class="bg-[var(--color-surface-secondary)] rounded-lg p-3 text-center transition-all duration-[var(--duration-fast)] hover:bg-[var(--color-surface-tertiary)] hover:shadow-[var(--shadow-sm)]"
          >
            <p class="text-2xl font-bold text-[var(--color-text-primary)]">
              {{ runInfo.items_total }}
            </p>
            <p class="text-xs text-[var(--color-text-muted)]">
              Items Processed
            </p>
          </div>
          <div
            class="bg-[var(--color-surface-secondary)] rounded-lg p-3 text-center transition-all duration-[var(--duration-fast)] hover:bg-[var(--color-surface-tertiary)] hover:shadow-[var(--shadow-sm)]"
          >
            <p class="text-2xl font-bold text-[var(--color-text-primary)]">
              {{ runInfo.stories_total }}
            </p>
            <p class="text-xs text-[var(--color-text-muted)]">
              Stories Created
            </p>
          </div>
          <div
            class="bg-[var(--color-surface-secondary)] rounded-lg p-3 text-center transition-all duration-[var(--duration-fast)] hover:bg-[var(--color-surface-tertiary)] hover:shadow-[var(--shadow-sm)]"
          >
            <p class="text-2xl font-bold text-[var(--color-success)]">
              {{ healthySources }}
            </p>
            <p class="text-xs text-[var(--color-text-muted)]">
              Sources OK
            </p>
          </div>
          <div
            class="bg-[var(--color-surface-secondary)] rounded-lg p-3 text-center transition-all duration-[var(--duration-fast)] hover:bg-[var(--color-surface-tertiary)] hover:shadow-[var(--shadow-sm)]"
          >
            <p
              class="text-2xl font-bold"
              :class="
                failedSources > 0 ? 'text-[var(--color-error)]' : 'text-[var(--color-text-primary)]'
              "
            >
              {{ failedSources }}
            </p>
            <p class="text-xs text-[var(--color-text-muted)]">
              Sources Failed
            </p>
          </div>
        </div>
      </div>

      <!-- Run Details -->
      <div class="card p-6 animate-fade-in-up stagger-2 hover-lift">
        <h2 class="text-lg font-semibold text-[var(--color-text-primary)] mb-4">
          Run Details
        </h2>
        <dl class="space-y-3">
          <div
            class="flex justify-between py-2 border-b border-[var(--color-border-subtle)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-secondary)]/50 -mx-2 px-2 rounded"
          >
            <dt class="text-[var(--color-text-muted)]">
              Run ID
            </dt>
            <dd class="font-mono text-sm text-[var(--color-text-secondary)]">
              {{ runInfo.run_id }}
            </dd>
          </div>
          <div
            class="flex justify-between py-2 border-b border-[var(--color-border-subtle)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-secondary)]/50 -mx-2 px-2 rounded"
          >
            <dt class="text-[var(--color-text-muted)]">
              Started
            </dt>
            <dd class="text-[var(--color-text-secondary)]">
              {{ formatDate(runInfo.started_at) }}
            </dd>
          </div>
          <div
            class="flex justify-between py-2 border-b border-[var(--color-border-subtle)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-secondary)]/50 -mx-2 px-2 rounded"
          >
            <dt class="text-[var(--color-text-muted)]">
              Finished
            </dt>
            <dd class="text-[var(--color-text-secondary)]">
              {{ formatDate(runInfo.finished_at) }}
            </dd>
          </div>
          <div
            v-if="runInfo.error_summary"
            class="py-2"
          >
            <dt class="text-[var(--color-text-muted)] mb-1">
              Error
            </dt>
            <dd class="text-sm text-[var(--color-error)] bg-[var(--color-error)]/10 p-3 rounded-lg">
              {{ runInfo.error_summary }}
            </dd>
          </div>
        </dl>
      </div>
    </div>

    <div
      v-else
      class="flex flex-col items-center justify-center py-20 bg-[var(--color-surface-secondary)] rounded-xl border border-dashed border-[var(--color-border-default)] animate-fade-in-scale transition-all duration-[var(--duration-base)] hover:border-[var(--color-border-strong)]"
    >
      <span
        class="text-5xl mb-4 animate-float"
        aria-hidden="true"
      >📊</span>
      <p class="text-[var(--color-text-secondary)] font-medium">
        No status data available
      </p>
    </div>
  </div>
</template>
