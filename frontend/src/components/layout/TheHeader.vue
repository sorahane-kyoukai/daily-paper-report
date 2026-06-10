<script setup lang="ts">
  import { computed } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDigestStore } from '@/stores/digest'
  import { useLanguage } from '@/shared/composables/useLanguage'
  import IconGithub from '@/components/icons/IconGithub.vue'

  const digestStore = useDigestStore()
  const { locale, toggleLocale } = useLanguage()
  const route = useRoute()
  const runDate = computed(() => digestStore.runDate)

  const githubRepoUrl = 'https://github.com/DennySORA/Daily-Paper-Report'

  const navLinks = [
    { to: '/', label: 'Today', testId: 'today' },
    { to: '/reports', label: 'Reports', testId: 'reports' },
    { to: '/archive', label: 'Archive', testId: 'archive' },
    { to: '/sources', label: 'Sources', testId: 'sources' },
    { to: '/status', label: 'Status', testId: 'status' },
  ]

  const isActiveRoute = (to: string) => {
    if (to === '/') {
      return route.path === '/' || route.path.startsWith('/day/')
    }
    if (to === '/reports') {
      return route.path.startsWith('/reports')
    }
    return route.path === to
  }
</script>

<template>
  <header class="site-header" role="banner">
    <div class="container-app">
      <div class="site-header__inner">
        <RouterLink
          to="/"
          class="site-brand"
          data-testid="logo-link"
          aria-label="Daily Paper Report - Home"
        >
          <span class="site-brand__mark">
            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
              />
            </svg>
          </span>
          <div class="site-brand__copy">
            <span class="site-brand__title"> Daily Paper Report </span>
            <span v-if="runDate" class="site-brand__date">
              {{ runDate }}
            </span>
          </div>
        </RouterLink>

        <nav class="site-nav" aria-label="Main navigation">
          <RouterLink
            v-for="link in navLinks"
            :key="link.to"
            :to="link.to"
            class="site-nav__link"
            :class="{ 'site-nav__link--active': isActiveRoute(link.to) }"
            :data-testid="`nav-${link.testId}`"
            :aria-current="isActiveRoute(link.to) ? 'page' : undefined"
          >
            {{ link.label }}
          </RouterLink>

          <button
            class="site-header__icon-button site-header__locale"
            :class="{ 'site-header__locale--active': locale === 'zh-TW' }"
            :title="locale === 'en' ? 'Switch to Traditional Chinese' : 'Switch to English'"
            :aria-label="locale === 'en' ? 'Switch to Traditional Chinese' : 'Switch to English'"
            data-testid="locale-toggle"
            @click="toggleLocale"
          >
            {{ locale === 'en' ? '繁中' : 'EN' }}
          </button>

          <a
            :href="githubRepoUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="site-header__icon-button"
            title="View source on GitHub"
            aria-label="View source on GitHub (opens in new tab)"
            data-testid="github-link"
          >
            <IconGithub :size="18" />
          </a>
        </nav>
      </div>
    </div>
  </header>
</template>

<style scoped>
  .site-header {
    position: sticky;
    top: 0;
    z-index: 50;
    border-bottom: 1px solid var(--color-border-subtle);
    background:
      linear-gradient(180deg, rgb(18 21 18 / 0.96), rgb(16 19 16 / 0.9)),
      var(--color-surface-raised);
    backdrop-filter: blur(18px);
  }

  .site-header__inner {
    display: flex;
    min-height: 4rem;
    flex-direction: column;
    gap: 0.75rem;
    padding: 0.7rem 0;
  }

  .site-brand {
    display: inline-flex;
    width: fit-content;
    align-items: center;
    gap: 0.7rem;
    color: inherit;
    text-decoration: none;
    border-radius: var(--radius-lg);
    transition:
      color var(--duration-fast) var(--ease-out),
      transform var(--duration-fast) var(--ease-out);
  }

  .site-brand:hover {
    color: var(--color-accent-primary-hover);
    transform: translateY(-1px);
  }

  .site-brand:active {
    transform: translateY(0) scale(0.99);
  }

  .site-brand:focus-visible,
  .site-nav__link:focus-visible,
  .site-header__icon-button:focus-visible {
    outline: none;
    box-shadow:
      0 0 0 2px var(--color-surface-base),
      0 0 0 4px var(--color-border-focus);
  }

  .site-brand__mark {
    display: inline-flex;
    width: 2rem;
    height: 2rem;
    align-items: center;
    justify-content: center;
    color: var(--color-accent-primary);
    border: 1px solid rgb(200 168 78 / 0.24);
    border-radius: var(--radius-lg);
    background:
      linear-gradient(145deg, rgb(200 168 78 / 0.13), rgb(122 158 143 / 0.06)),
      var(--color-surface-secondary);
    box-shadow: var(--shadow-xs);
    transition:
      border-color var(--duration-fast) var(--ease-out),
      transform var(--duration-fast) var(--ease-spring);
  }

  .site-brand:hover .site-brand__mark {
    border-color: rgb(200 168 78 / 0.42);
    transform: rotate(-2deg) scale(1.03);
  }

  .site-brand__mark svg {
    width: 1rem;
    height: 1rem;
  }

  .site-brand__copy {
    display: flex;
    flex-direction: column;
  }

  .site-brand__title {
    font-family: var(--font-display);
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--color-text-primary);
    line-height: 1.15;
    transition: color var(--duration-fast) var(--ease-out);
  }

  .site-brand:hover .site-brand__title {
    color: var(--color-accent-primary-hover);
  }

  .site-brand__date {
    margin-top: 0.05rem;
    font-family: var(--font-mono);
    font-size: 0.66rem;
    color: var(--color-text-muted);
  }

  .site-nav {
    display: flex;
    width: 100%;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem;
  }

  .site-nav__link,
  .site-header__icon-button {
    display: inline-flex;
    min-height: 2rem;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-md);
    transition:
      color var(--duration-fast) var(--ease-out),
      background var(--duration-fast) var(--ease-out),
      border-color var(--duration-fast) var(--ease-out),
      box-shadow var(--duration-fast) var(--ease-out),
      transform var(--duration-fast) var(--ease-out);
  }

  .site-nav__link {
    padding: 0.42rem 0.72rem;
    color: var(--color-text-tertiary);
    font-size: 0.82rem;
    font-weight: 650;
    text-decoration: none;
  }

  .site-nav__link:hover {
    color: var(--color-text-primary);
    background: var(--color-surface-secondary);
    transform: translateY(-1px);
  }

  .site-nav__link:active,
  .site-header__icon-button:active {
    transform: translateY(0) scale(0.97);
  }

  .site-nav__link--active {
    color: var(--color-text-inverse);
    background: var(--color-accent-primary);
    box-shadow: var(--shadow-glow-primary);
  }

  .site-nav__link--active:hover {
    color: var(--color-text-inverse);
    background: var(--color-accent-primary-hover);
  }

  .site-header__icon-button {
    width: 2rem;
    height: 2rem;
    color: var(--color-text-tertiary);
    border: 1px solid var(--color-border-subtle);
    background: transparent;
  }

  .site-header__icon-button:hover {
    color: var(--color-text-primary);
    border-color: var(--color-border-default);
    background: var(--color-surface-secondary);
    transform: translateY(-1px);
  }

  .site-header__locale {
    width: auto;
    min-width: 2.35rem;
    padding: 0 0.55rem;
    font-size: 0.72rem;
    font-weight: 750;
  }

  .site-header__locale--active {
    color: var(--color-accent-primary-hover);
    border-color: rgb(200 168 78 / 0.32);
    background: rgb(200 168 78 / 0.1);
  }

  @media (min-width: 720px) {
    .site-header__inner {
      min-height: 3.75rem;
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 0;
    }

    .site-nav {
      width: auto;
      flex-wrap: nowrap;
    }
  }
</style>
