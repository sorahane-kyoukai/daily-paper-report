<script setup lang="ts">
import { computed } from 'vue'
import { useDigestStore } from '@/stores/digest'

const digestStore = useDigestStore()
const runInfo = computed(() => digestStore.runInfo)

const formatDate = (dateStr: string | null): string => {
  if (!dateStr) return 'N/A'
  return new Date(dateStr).toLocaleString()
}
</script>

<template>
  <footer
    class="border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-sunken)] py-4"
    role="contentinfo"
  >
    <div class="container-app">
      <div class="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
        <div
          class="flex items-center gap-1.5 text-[var(--color-text-quaternary)] transition-colors duration-[var(--duration-fast)] hover:text-[var(--color-text-tertiary)]"
        >
          <svg
            class="w-3.5 h-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
            />
          </svg>
          <span style="font-family: var(--font-display)">Daily Paper Report</span>
        </div>

        <div
          v-if="runInfo"
          class="flex items-center gap-3 text-[var(--color-text-quaternary)]"
        >
          <span
            class="tabular-nums"
            style="font-family: var(--font-mono)"
          >
            Last updated: {{ formatDate(runInfo.finished_at) }}
          </span>
          <span
            v-if="runInfo.success"
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--color-success-surface)] text-[var(--color-success)] text-[10px] font-medium"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
            Healthy
          </span>
        </div>
      </div>
    </div>
  </footer>
</template>
