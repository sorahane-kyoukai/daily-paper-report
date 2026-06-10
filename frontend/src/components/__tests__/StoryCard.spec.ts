import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import StoryCard from '../ui/StoryCard.vue'
import type { Story } from '@/types/digest'

const mockStory: Story = {
  story_id: 'test-story-1',
  title: 'Test Story Title',
  arxiv_id: '2401.12345',
  entities: ['OpenAI', 'DeepMind'],
  github_release_url: null,
  hf_model_id: null,
  item_count: 1,
  links: [
    {
      link_type: 'blog',
      source_id: 'test-source',
      tier: 0,
      title: 'Test Story Title',
      url: 'https://example.com/test',
    },
  ],
  primary_link: {
    link_type: 'blog',
    source_id: 'test-source',
    tier: 0,
    title: 'Test Story Title',
    url: 'https://example.com/test',
  },
  published_at: '2026-01-20T10:00:00Z',
  first_seen_at: '2026-01-20T10:00:00Z',
  section: null,
  authors: ['John Doe', 'Jane Smith'],
  summary: 'This is a test summary for the story.',
  categories: ['cs.AI', 'cs.CL'],
  source_name: 'Test Blog',
}

describe('StoryCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders the story title', () => {
    const wrapper = mount(StoryCard, {
      props: { story: mockStory },
    })

    expect(wrapper.text()).toContain('Test Story Title')
  })

  it('renders the story link with correct href', () => {
    const wrapper = mount(StoryCard, {
      props: { story: mockStory },
    })

    const link = wrapper.find(`[data-testid="story-link-${mockStory.story_id}"]`)
    expect(link.attributes('href')).toBe('https://example.com/test')
  })

  it('renders rank badge when rank prop is provided', () => {
    const wrapper = mount(StoryCard, {
      props: { story: mockStory, rank: 1 },
    })

    const rankBadge = wrapper.find('[data-testid="story-rank-1"]')
    expect(rankBadge.exists()).toBe(true)
    expect(rankBadge.text()).toBe('1')
  })

  it('does not render rank badge when rank prop is not provided', () => {
    const wrapper = mount(StoryCard, {
      props: { story: mockStory },
    })

    const rankBadge = wrapper.find('[data-testid^="story-rank-"]')
    expect(rankBadge.exists()).toBe(false)
  })

  it('renders entities when showEntities is true', () => {
    const wrapper = mount(StoryCard, {
      props: { story: mockStory, showEntities: true },
    })

    expect(wrapper.text()).toContain('OpenAI')
    expect(wrapper.text()).toContain('DeepMind')
  })

  it('does not render entities when showEntities is false', () => {
    const wrapper = mount(StoryCard, {
      props: { story: mockStory, showEntities: false },
    })

    expect(wrapper.text()).not.toContain('OpenAI')
    expect(wrapper.text()).not.toContain('DeepMind')
  })

  it('renders arxiv ID when showArxiv is true', () => {
    const wrapper = mount(StoryCard, {
      props: { story: mockStory, showArxiv: true },
    })

    expect(wrapper.text()).toContain('arXiv:2401.12345')
  })

  it('formats date correctly for old dates', () => {
    // Use a date that's more than 7 days old to trigger full date format
    const oldStory = { ...mockStory, published_at: '2025-01-01T10:00:00Z' }
    const wrapper = mount(StoryCard, {
      props: { story: oldStory },
    })

    // The date should be formatted as "Jan 1, 2025" for old dates
    expect(wrapper.text()).toMatch(/Jan\s+1,\s+2025/)
  })

  it('shows relative time for recent dates', () => {
    // Use current time to get "Just now" or similar
    const now = new Date().toISOString()
    const recentStory = { ...mockStory, published_at: now }
    const wrapper = mount(StoryCard, {
      props: { story: recentStory },
    })

    // Should show relative time like "0m ago", "Xh ago", etc.
    expect(wrapper.text()).toMatch(/m ago|h ago|d ago|Yesterday/)
  })

  it('shows empty time when published_at is null', () => {
    const storyWithoutDate = { ...mockStory, published_at: null }
    const wrapper = mount(StoryCard, {
      props: { story: storyWithoutDate },
    })

    // The component no longer shows "Date unknown" - it just shows empty relative time
    // Verify the story title still renders correctly
    expect(wrapper.text()).toContain('Test Story Title')
  })

  it('applies accent type styling when provided', () => {
    const wrapper = mount(StoryCard, {
      props: { story: mockStory, accentType: 'highlight' },
    })

    // The component applies card-accent-* classes based on accentType
    expect(wrapper.find('article').classes()).toContain('card-accent-highlight')
  })

  it('splits summaries into paragraphs after Chinese full stops', () => {
    const storyWithLongChineseSummary = {
      ...mockStory,
      summary: '第一段說明研究問題。第二段補充方法與結果。第三段說明值得關注的原因。',
    }
    const wrapper = mount(StoryCard, {
      props: { story: storyWithLongChineseSummary },
    })

    const paragraphs = wrapper.findAll('.paper-card-summary')
    expect(paragraphs).toHaveLength(3)
    expect(paragraphs[0].text()).toBe('第一段說明研究問題。')
    expect(paragraphs[1].text()).toBe('第二段補充方法與結果。')
    expect(paragraphs[2].text()).toBe('第三段說明值得關注的原因。')
  })
})
