/**
 * Composable for managing locale state between English and Traditional Chinese.
 *
 * Persists the selected locale to localStorage so the preference
 * survives page reloads. Falls back to English when no translation
 * data is available.
 */

import { computed, ref, watchEffect } from 'vue'

export type Locale = 'en' | 'zh-TW'

const STORAGE_KEY = 'dpr-locale'

const stored = (
  typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
) as Locale | null

const locale = ref<Locale>(stored === 'zh-TW' ? 'zh-TW' : 'en')

watchEffect(() => {
  if (typeof window !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, locale.value)
  }
})

export function useLanguage() {
  const isZh = computed(() => locale.value === 'zh-TW')

  function toggleLocale() {
    locale.value = locale.value === 'en' ? 'zh-TW' : 'en'
  }

  return {
    locale,
    isZh,
    toggleLocale,
  }
}
