import { describe, expect, it } from 'vitest'
import { filterStoriesBySearch, matchesSearch } from '../useSearch'
import type { Story } from '@/shared/types'

function makeStory(overrides: Partial<Story> = {}): Story {
  return {
    story_id: 'story-1',
    title: 'Efficient Sparse Attention',
    arxiv_id: '2605.00001',
    entities: ['OpenAI'],
    github_release_url: null,
    hf_model_id: null,
    item_count: 1,
    links: [],
    primary_link: {
      link_type: 'arxiv',
      source_id: 'arxiv-cs-lg',
      tier: 0,
      title: 'Efficient Sparse Attention',
      url: 'https://arxiv.org/abs/2605.00001',
    },
    published_at: '2026-05-20T00:00:00+00:00',
    section: 'papers',
    authors: ['Ada Lovelace'],
    summary: 'A sparse attention paper.',
    categories: ['cs.LG'],
    source_name: 'arXiv cs.LG',
    first_seen_at: '2026-05-20T00:00:00+00:00',
    ...overrides,
  }
}

describe('matchesSearch', () => {
  it('matches Traditional Chinese report translations', () => {
    const story = makeStory({
      title_zh: '\u9ad8\u6548\u7387 Sparse Attention \u67b6\u69cb',
      summary_zh:
        '\u672c\u6587\u63d0\u51fa\u9069\u5408\u9577\u6587\u8108\u7d61\u7684\u6ce8\u610f\u529b\u6a5f\u5236\u3002',
    })

    expect(matchesSearch(story, '\u9577\u6587\u8108\u7d61')).toBe(true)
    expect(matchesSearch(story, '\u9ad8\u6548\u7387')).toBe(true)
  })

  it('matches report metadata and taxonomy fields', () => {
    const story = makeStory({
      categories: ['cs.CL', 'stat.ML'],
      report_source_section: 'top5',
      report_source_date: '2026-05-20',
      source_name: 'Hugging Face Daily Papers',
    })

    expect(matchesSearch(story, 'top5')).toBe(true)
    expect(matchesSearch(story, 'stat.ml')).toBe(true)
    expect(matchesSearch(story, 'hugging face')).toBe(true)
  })

  it('filters stories with a trimmed query', () => {
    const stories = [
      makeStory({ story_id: 'story-1', title: 'Sparse Attention' }),
      makeStory({ story_id: 'story-2', title: 'Video Diffusion' }),
    ]

    expect(filterStoriesBySearch(stories, '  video  ')).toEqual([stories[1]])
  })
})
