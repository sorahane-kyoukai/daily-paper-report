import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDigestStore } from '../digest'
import type { DigestData } from '@/types/digest'

const mockDigestData: DigestData = {
  generated_at: '2026-01-20T10:00:00Z',
  run_date: '2026-01-20',
  run_id: 'test-run-id',
  run_info: {
    run_id: 'test-run-id',
    started_at: '2026-01-20T09:55:00Z',
    finished_at: '2026-01-20T10:00:00Z',
    success: true,
    items_total: 100,
    stories_total: 10,
    error_summary: null,
  },
  top5: [
    {
      story_id: 'story-1',
      title: 'Top Story 1',
      arxiv_id: null,
      entities: [],
      github_release_url: null,
      hf_model_id: null,
      item_count: 1,
      links: [],
      primary_link: {
        link_type: 'blog',
        source_id: 'test',
        tier: 0,
        title: 'Top Story 1',
        url: 'https://example.com/1',
      },
      published_at: '2026-01-20T08:00:00Z',
      first_seen_at: '2026-01-20T08:00:00Z',
      section: null,
      authors: [],
      summary: null,
      categories: [],
      source_name: null,
    },
  ],
  papers: [],
  model_releases_by_entity: {
    OpenAI: [
      {
        story_id: 'model-1',
        title: 'GPT-5',
        arxiv_id: null,
        entities: ['OpenAI'],
        github_release_url: null,
        hf_model_id: null,
        item_count: 1,
        links: [],
        primary_link: {
          link_type: 'model',
          source_id: 'test',
          tier: 0,
          title: 'GPT-5',
          url: 'https://example.com/gpt5',
        },
        published_at: '2026-01-20T09:00:00Z',
        first_seen_at: '2026-01-20T09:00:00Z',
        section: null,
        authors: [],
        summary: null,
        categories: [],
        source_name: null,
      },
    ],
  },
  radar: [],
  sources_status: [
    {
      source_id: 'test-source',
      name: 'Test Source',
      method: 'rss_atom',
      category: 'blog',
      tier: 0,
      status: 'HAS_UPDATE',
      reason_code: 'FETCH_PARSE_OK_HAS_NEW',
      reason_text: 'Fetch succeeded',
      remediation_hint: null,
      items_new: 5,
      items_updated: 0,
      newest_item_date: '2026-01-20T10:00:00Z',
      last_fetch_status_code: 200,
    },
  ],
  archive_dates: ['2026-01-20', '2026-01-19', '2026-01-18'],
  entity_catalog: {},
}

describe('useDigestStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('initializes with default state', () => {
    const store = useDigestStore()

    expect(store.data).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
    expect(store.hasData).toBe(false)
  })

  it('setData updates the store data', () => {
    const store = useDigestStore()

    store.setData(mockDigestData)

    expect(store.data).toEqual(mockDigestData)
    expect(store.hasData).toBe(true)
  })

  it('top5 getter returns top5 stories', () => {
    const store = useDigestStore()
    store.setData(mockDigestData)

    expect(store.top5).toHaveLength(1)
    expect(store.top5[0].title).toBe('Top Story 1')
  })

  it('modelReleases getter returns model releases by entity', () => {
    const store = useDigestStore()
    store.setData(mockDigestData)

    expect(store.modelReleases).toHaveProperty('OpenAI')
    expect(store.modelReleases.OpenAI).toHaveLength(1)
  })

  it('hasModelReleases returns true when there are models', () => {
    const store = useDigestStore()
    store.setData(mockDigestData)

    expect(store.hasModelReleases).toBe(true)
  })

  it('hasModelReleases returns false when there are no models', () => {
    const store = useDigestStore()
    store.setData({ ...mockDigestData, model_releases_by_entity: {} })

    expect(store.hasModelReleases).toBe(false)
  })

  it('runDate getter returns the run date', () => {
    const store = useDigestStore()
    store.setData(mockDigestData)

    expect(store.runDate).toBe('2026-01-20')
  })

  it('totalStories computes total story count', () => {
    const store = useDigestStore()
    store.setData(mockDigestData)

    // 1 top5 + 0 papers + 1 model + 0 radar = 2
    expect(store.totalStories).toBe(2)
  })

  it('getStoriesByEntity returns stories for given entity', () => {
    const store = useDigestStore()
    store.setData(mockDigestData)

    const openaiStories = store.getStoriesByEntity('OpenAI')
    expect(openaiStories).toHaveLength(1)
    expect(openaiStories[0].title).toBe('GPT-5')
  })

  it('getStoriesByEntity returns empty array for unknown entity', () => {
    const store = useDigestStore()
    store.setData(mockDigestData)

    const stories = store.getStoriesByEntity('Unknown')
    expect(stories).toEqual([])
  })

  describe('fetchDigest', () => {
    it('sets isLoading during fetch', async () => {
      const store = useDigestStore()

      global.fetch = vi.fn().mockImplementation(
        () =>
          new Promise((resolve) => {
            setTimeout(() => {
              resolve({
                ok: true,
                json: () => Promise.resolve(mockDigestData),
              })
            }, 10)
          }),
      )

      const fetchPromise = store.fetchDigest()
      expect(store.isLoading).toBe(true)

      await fetchPromise
      expect(store.isLoading).toBe(false)
    })

    it('fetches and stores data successfully', async () => {
      const store = useDigestStore()

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockDigestData),
      })

      await store.fetchDigest()

      expect(store.data).toEqual(mockDigestData)
      expect(store.error).toBeNull()
    })

    it('handles fetch errors', async () => {
      const store = useDigestStore()

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      })

      await store.fetchDigest()

      expect(store.error).toBe('Failed to fetch digest: 404 Not Found')
      expect(store.data).toBeNull()
    })

    it('handles network errors', async () => {
      const store = useDigestStore()

      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))

      await store.fetchDigest()

      expect(store.error).toBe('Network error')
    })
  })
})
