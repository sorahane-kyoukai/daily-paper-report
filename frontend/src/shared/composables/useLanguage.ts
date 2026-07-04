/**
 * Composable for managing locale state between English and Traditional Chinese.
 *
 * Persists the selected locale to localStorage so the preference
 * survives page reloads. Defaults to Traditional Chinese for new
 * visitors while individual cards fall back to source text when a
 * story has not been translated yet.
 */

import { computed, ref, watchEffect } from 'vue'

export type Locale = 'en' | 'zh-TW'

const STORAGE_KEY = 'dpr-locale'

const stored = (
  typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
) as Locale | null

const locale = ref<Locale>(stored === 'en' ? 'en' : 'zh-TW')

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
