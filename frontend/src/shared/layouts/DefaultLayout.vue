<script setup lang="ts">
import TheHeader from '@/components/layout/TheHeader.vue'
import TheFooter from '@/components/layout/TheFooter.vue'

interface Props {
  /** ID for the main content area (for skip links) */
  mainId?: string
  /** Whether to show skip-to-content link */
  showSkipLink?: boolean
}

withDefaults(defineProps<Props>(), {
  mainId: 'main-content',
  showSkipLink: true,
})
</script>

<template>
  <div class="layout-wrapper">
    <!-- Skip to main content link for keyboard users -->
    <a
      v-if="showSkipLink"
      href="#main-content"
      class="skip-link"
    >
      Skip to main content
    </a>

    <TheHeader />

    <main
      :id="mainId"
      class="layout-main"
      role="main"
    >
      <div class="container-app py-6 sm:py-8">
        <slot />
      </div>
    </main>

    <TheFooter />
  </div>
</template>

<style scoped>
.layout-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: var(--color-surface-base);
}

.layout-main {
  flex: 1;
}

/* Skip link - visible only on focus for keyboard navigation */
.skip-link {
  position: absolute;
  top: -100%;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  padding: 0.75rem 1.5rem;
  background: var(--color-accent-primary);
  color: white;
  font-weight: 600;
  font-size: 0.875rem;
  border-radius: var(--radius-lg);
  text-decoration: none;
  transition: top var(--duration-fast) var(--ease-out);
}

.skip-link:focus {
  top: 1rem;
  outline: none;
  box-shadow: var(--shadow-glow-primary);
}
</style>
