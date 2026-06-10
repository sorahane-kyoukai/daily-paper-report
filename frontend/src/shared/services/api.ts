import type { DigestData } from '@/shared/types'

/**
 * API client for fetching digest data
 */

const API_BASE = '/api'

export interface FetchResult<T> {
  data: T | null
  error: string | null
}

/**
 * Fetch digest data from API
 * @param targetDate - Optional date (YYYY-MM-DD) to fetch specific archive data
 */
export async function fetchDigestData(
  targetDate?: string,
): Promise<FetchResult<DigestData>> {
  try {
    const endpoint = targetDate
      ? `${API_BASE}/day/${targetDate}.json`
      : `${API_BASE}/daily.json`

    const response = await fetch(endpoint)

    if (!response.ok) {
      // If specific date not found, fall back to daily.json
      if (targetDate && response.status === 404) {
        console.warn(
          `Archive for ${targetDate} not found, falling back to daily.json`,
        )
        const fallbackResponse = await fetch(`${API_BASE}/daily.json`)
        if (!fallbackResponse.ok) {
          return {
            data: null,
            error: `Failed to fetch digest: ${fallbackResponse.status} ${fallbackResponse.statusText}`,
          }
        }
        return { data: await fallbackResponse.json(), error: null }
      }
      return {
        data: null,
        error: `Failed to fetch digest: ${response.status} ${response.statusText}`,
      }
    }

    return { data: await response.json(), error: null }
  } catch (err) {
    const error = err instanceof Error ? err.message : 'Unknown error occurred'
    console.error('Failed to fetch digest:', err)
    return { data: null, error }
  }
}
