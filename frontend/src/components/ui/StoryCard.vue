<script setup lang="ts">
  import type { Story, EntityDetail } from '@/types/digest'
  import { computed } from 'vue'
  import { useDigestStore } from '@/stores/digest'
  import { formatDate, formatRelativeTime } from '@/shared/composables/useTimeFormat'
  import {
    decodeLatex,
    stripHtml,
    cleanArxivPrefix,
    cleanLatexEmphasis,
    looksLikeImageAlt,
  } from '@/shared/composables/useLatexDecoder'
  import {
    formatNumber,
    formatPipelineTag,
    formatSourceId,
  } from '@/shared/composables/useNumberFormat'
  import { useLanguage } from '@/shared/composables/useLanguage'

  const digestStore = useDigestStore()
  const { isZh } = useLanguage()

  interface Props {
    story: Story
    rank?: number
    showEntities?: boolean
    showArxiv?: boolean
    showSummary?: boolean
    showAuthors?: boolean
    showCategories?: boolean
    showSource?: boolean
    showAffiliations?: boolean
    featured?: boolean
    accentType?: 'highlight' | 'papers' | 'models' | 'sources' | 'radar'
    compact?: boolean
  }

  const props = withDefaults(defineProps<Props>(), {
    rank: undefined,
    showEntities: false,
    showArxiv: false,
    showSummary: true,
    showAuthors: true,
    showCategories: true,
    showSource: true,
    showAffiliations: true,
    featured: false,
    accentType: undefined,
    compact: false,
  })

  // Get link type label
  const getLinkTypeLabel = (linkType: string): string => {
    const labels: Record<string, string> = {
      blog: 'Blog',
      paper: 'Paper',
      model: 'Model',
      github: 'GitHub',
      arxiv: 'arXiv',
      huggingface: 'HuggingFace',
      official: 'Official',
    }
    return labels[linkType] ?? linkType
  }

  // Clean and prepare summary (no truncation for scrollable display, locale-aware)
  const cleanedSummary = computed(() => {
    // Use Chinese summary when locale is zh-TW and translation available
    if (isZh.value && props.story.summary_zh) {
      return props.story.summary_zh
    }

    if (!props.story.summary) return null
    let cleanSummary = stripHtml(props.story.summary)
    if (!cleanSummary) return null

    // Remove arXiv metadata prefix
    cleanSummary = cleanArxivPrefix(cleanSummary)
    if (!cleanSummary) return null

    // Clean LaTeX emphasis commands
    cleanSummary = cleanLatexEmphasis(cleanSummary)

    // Filter out summaries that look like image alt text
    if (looksLikeImageAlt(cleanSummary)) return null

    return cleanSummary
  })

  // Truncate summary for compact mode only
  const truncatedSummary = computed(() => {
    if (!cleanedSummary.value) return null

    // Only truncate in compact mode
    if (props.compact) {
      const maxLength = 120
      if (cleanedSummary.value.length <= maxLength) return cleanedSummary.value
      const truncated = cleanedSummary.value.slice(0, maxLength)
      const lastSpace = truncated.lastIndexOf(' ')
      return (
        (lastSpace > maxLength * 0.7 ? truncated.slice(0, lastSpace) : truncated).trim() + '...'
      )
    }

    // For non-compact mode, return full cleaned summary (will be scrollable)
    return cleanedSummary.value
  })

  const summaryParagraphs = computed(() => {
    if (!truncatedSummary.value) return []
    return splitSummaryParagraphs(truncatedSummary.value)
  })

  function splitSummaryParagraphs(text: string): string[] {
    const normalized = text.replace(/\s+/g, ' ').trim()
    if (!normalized) return []
    if (!normalized.includes('。')) return [normalized]

    const parts = normalized.match(/[^。]+。?/g) ?? [normalized]
    return parts.map((part) => part.trim()).filter((part) => part.length > 0)
  }

  // Check if summary is long enough to be scrollable (more than ~4 lines worth)
  const isScrollableSummary = computed(() => {
    if (!cleanedSummary.value || props.compact) return false
    // Approximate: ~80 chars per line, 4 lines = 320 chars threshold
    return cleanedSummary.value.length > 320
  })

  // Display authors with smart truncation and LaTeX decoding
  const displayAuthors = computed(() => {
    if (!props.story.authors || props.story.authors.length === 0) return null
    const decodedAuthors = props.story.authors.map((author) => decodeLatex(author))
    if (decodedAuthors.length <= 3) return decodedAuthors.join(', ')
    return `${decodedAuthors.slice(0, 3).join(', ')} +${decodedAuthors.length - 3} more`
  })

  // Decoded title for display (locale-aware)
  const displayTitle = computed(() => {
    if (isZh.value && props.story.title_zh) {
      return props.story.title_zh
    }
    return decodeLatex(props.story.title)
  })

  // Get category label
  const categoryLabel = computed(() => {
    if (!props.story.categories || props.story.categories.length === 0) return null
    return props.story.categories[0]
  })

  // Get source display name
  const sourceName = computed(() => {
    return props.story.source_name || formatSourceId(props.story.primary_link.source_id)
  })

  // Check if story has HuggingFace metadata
  const hasHfMetadata = computed(() => {
    return (
      props.story.hf_metadata &&
      (props.story.hf_metadata.pipeline_tag ||
        props.story.hf_metadata.downloads !== undefined ||
        props.story.hf_metadata.likes !== undefined)
    )
  })

  // Card classes based on props
  const cardClasses = computed(() => {
    const classes = ['card', 'paper-card', 'group']

    if (props.featured) {
      classes.push('card-featured')
    }

    if (props.accentType) {
      classes.push(`card-accent`, `card-accent-${props.accentType}`)
    }

    if (props.compact) {
      classes.push('paper-card--compact')
    }

    return classes
  })

  // Get badge class for source type
  const getSourceBadgeClass = (sourceId: string): string => {
    if (sourceId.startsWith('arxiv')) return 'badge-source-arxiv'
    if (sourceId.startsWith('hf-')) return 'badge-source-hf'
    if (sourceId.includes('blog')) return 'badge-source-blog'
    return 'badge-muted'
  }

  // Get accent badge class
  const getAccentBadgeClass = computed(() => {
    if (!props.accentType) return 'badge-muted'
    return `badge-${props.accentType}`
  })

  // Resolve entity details for affiliation badges (organizations and institutions only, max 2)
  const affiliationEntities = computed((): { id: string; detail: EntityDetail }[] => {
    if (!props.story.entities || props.story.entities.length === 0) return []

    const results: { id: string; detail: EntityDetail }[] = []
    for (const entityId of props.story.entities) {
      const detail = digestStore.getEntityDetail(entityId)
      if (detail && detail.type !== 'researcher') {
        results.push({ id: entityId, detail })
      }
      if (results.length >= 2) break
    }
    return results
  })

  // Get CSS class for entity type badge
  const getEntityBadgeClass = (entityType: string): string => {
    switch (entityType) {
      case 'organization':
        return 'badge-entity-org'
      case 'institution':
        return 'badge-entity-inst'
      default:
        return 'badge-entity-org'
    }
  }

  // LLM relevance score display (raw 0-1 scale)
  const llmRawScore = computed(() => {
    if (props.story.scores?.llm_raw_score != null) {
      return props.story.scores.llm_raw_score
    }
    // Fallback: estimate raw from weighted score (weight=22 current default)
    if (props.story.scores?.llm_relevance_score != null) {
      const weighted = props.story.scores.llm_relevance_score
      if (weighted > 0) return Math.min(weighted / 22, 1.0)
    }
    return null
  })

  const llmScoreLabel = computed(() => {
    if (llmRawScore.value === null) return null
    return Math.round(llmRawScore.value * 100).toString()
  })

  const llmScoreClass = computed(() => {
    if (llmRawScore.value === null) return ''
    if (llmRawScore.value >= 0.8) return 'badge-score-high'
    if (llmRawScore.value >= 0.6) return 'badge-score-mid'
    return 'badge-score-low'
  })

  // Total score display
  const totalScore = computed(() => {
    if (props.story.scores?.total_score == null) return null
    return props.story.scores.total_score.toFixed(1)
  })

  // Full LLM evaluation: rationale + six weighted component scores
  const llmEvaluation = computed(() => props.story.llm_evaluation ?? null)

  const llmRationale = computed(() => {
    const rationale = llmEvaluation.value?.rationale?.trim()
    return rationale ? rationale : null
  })

  const componentLabels = computed<Record<string, string>>(() =>
    isZh.value
      ? {
          preference_relevance: '偏好相關性',
          novelty: '新穎性',
          rigor: '嚴謹度',
          evidence_strength: '證據強度',
          generalizability: '泛化性',
          reproducibility: '可重現性',
        }
      : {
          preference_relevance: 'Preference relevance',
          novelty: 'Novelty',
          rigor: 'Rigor',
          evidence_strength: 'Evidence strength',
          generalizability: 'Generalizability',
          reproducibility: 'Reproducibility',
        },
  )

  const componentBreakdown = computed(() => {
    const components = llmEvaluation.value?.components
    if (!components) return []
    return Object.entries(components).map(([key, value]) => ({
      key,
      label: componentLabels.value[key] ?? key,
      value: typeof value === 'number' ? value : 0,
    }))
  })

  const formatPercent = (value: number): string => `${Math.round(value * 100)}%`
</script>

<template>
  <article
    :class="cardClasses"
    :data-testid="`story-card-${story.story_id}`"
  >
    <div class="flex items-start gap-3">
      <!-- Rank badge (for top picks) -->
      <div
        v-if="rank"
        class="rank-badge"
        :class="{ 'rank-badge--top': rank <= 3 }"
        style="font-family: var(--font-mono)"
        :data-testid="`story-rank-${rank}`"
      >
        {{ rank }}
      </div>

      <div class="flex-1 min-w-0 space-y-2.5">
        <!-- Header: Featured badge, Category & Source -->
        <div class="flex flex-wrap items-center gap-2">
          <span
            v-if="featured"
            class="badge badge-top-pick"
          >
            <svg
              class="w-3 h-3"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"
              />
            </svg>
            Top Pick
          </span>
          <span
            v-if="showCategories && categoryLabel"
            class="badge badge-category"
            :class="getAccentBadgeClass"
          >
            {{ categoryLabel }}
          </span>
          <!-- Affiliation badges (company/institution) -->
          <span
            v-for="entity in showAffiliations ? affiliationEntities : []"
            :key="entity.id"
            class="badge badge-category badge-entity"
            :class="getEntityBadgeClass(entity.detail.type)"
          >
            <!-- Organization icon: building -->
            <svg
              v-if="entity.detail.type === 'organization'"
              class="badge-entity-icon"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
              />
            </svg>
            <!-- Institution icon: academic cap -->
            <svg
              v-else
              class="badge-entity-icon"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14zm-4 6v-7.5l4-2.222"
              />
            </svg>
            {{ entity.detail.name }}
          </span>
          <span
            v-if="showSource && sourceName"
            class="badge badge-category"
            :class="getSourceBadgeClass(story.primary_link.source_id)"
          >
            {{ sourceName }}
          </span>
          <!-- LLM Relevance Score -->
          <span
            v-if="llmScoreLabel"
            class="badge badge-score"
            :class="llmScoreClass"
            :title="`LLM Relevance: ${llmScoreLabel}% | Total Score: ${totalScore ?? 'N/A'}`"
          >
            <svg
              class="w-3 h-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
              />
            </svg>
            {{ llmScoreLabel }}%
          </span>
        </div>

        <!-- Title -->
        <h3
          class="paper-card-title"
          :class="compact ? 'text-[0.8125rem]' : 'text-[0.9375rem]'"
        >
          <a
            :href="story.primary_link.url"
            target="_blank"
            rel="noopener noreferrer"
            class="paper-card-link group/link"
            :data-testid="`story-link-${story.story_id}`"
          >
            <span :class="compact ? 'line-clamp-2' : 'line-clamp-3'">{{ displayTitle }}</span>
            <svg
              class="paper-card-external-icon"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
              />
            </svg>
          </a>
        </h3>

        <!-- Authors -->
        <p
          v-if="showAuthors && displayAuthors"
          class="paper-card-authors"
        >
          <svg
            class="inline-block w-3.5 h-3.5 mr-1.5 opacity-50"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
            />
          </svg>
          {{ displayAuthors }}
        </p>

        <!-- HuggingFace Model Metadata -->
        <div
          v-if="hasHfMetadata && !compact"
          class="hf-metadata"
        >
          <!-- Pipeline tag (task type) -->
          <span
            v-if="story.hf_metadata?.pipeline_tag"
            class="hf-metadata-tag"
          >
            <svg
              class="w-3 h-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
            {{ formatPipelineTag(story.hf_metadata.pipeline_tag) }}
          </span>

          <!-- Downloads -->
          <span
            v-if="story.hf_metadata?.downloads !== undefined"
            class="hf-metadata-stat"
            title="Downloads"
          >
            <svg
              class="w-3 h-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            {{ formatNumber(story.hf_metadata.downloads) }}
          </span>

          <!-- Likes -->
          <span
            v-if="story.hf_metadata?.likes !== undefined"
            class="hf-metadata-stat"
            title="Likes"
          >
            <svg
              class="w-3 h-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
              />
            </svg>
            {{ formatNumber(story.hf_metadata.likes) }}
          </span>

          <!-- License -->
          <span
            v-if="story.hf_metadata?.license"
            class="hf-metadata-license"
            title="License"
          >
            {{ story.hf_metadata.license }}
          </span>
        </div>

        <!-- Summary/Abstract -->
        <div
          v-if="showSummary && summaryParagraphs.length > 0"
          class="paper-card-summary-wrapper"
          :class="{ 'paper-card-summary-scrollable': isScrollableSummary }"
        >
          <p
            v-for="(paragraph, index) in summaryParagraphs"
            :key="`${story.story_id}-summary-${index}`"
            class="paper-card-summary"
          >
            {{ paragraph }}
          </p>
        </div>

        <!-- LLM evaluation: rationale + component breakdown -->
        <div
          v-if="llmEvaluation"
          class="llm-evaluation"
        >
          <p
            v-if="llmRationale"
            class="llm-evaluation-rationale"
          >
            {{ llmRationale }}
          </p>
          <div
            v-if="componentBreakdown.length > 0"
            class="llm-evaluation-components"
          >
            <div
              v-for="item in componentBreakdown"
              :key="item.key"
              class="llm-component"
            >
              <span class="llm-component-label">{{ item.label }}</span>
              <div class="llm-component-bar">
                <div
                  class="llm-component-fill"
                  :style="{ width: formatPercent(item.value) }"
                ></div>
              </div>
              <span class="llm-component-value">{{ formatPercent(item.value) }}</span>
            </div>
          </div>
        </div>

        <!-- Meta info -->
        <div class="paper-card-meta">
          <!-- Time -->
          <span
            class="paper-card-time"
            :title="formatDate(story.published_at)"
          >
            <svg
              class="w-3.5 h-3.5 opacity-60"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span class="tabular-nums">{{ formatRelativeTime(story.published_at) }}</span>
          </span>

          <!-- Entity badges -->
          <template v-if="showEntities && story.entities.length > 0">
            <span class="meta-divider">·</span>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="entity in story.entities.slice(0, 3)"
                :key="entity"
                class="badge badge-muted text-[0.625rem] py-0.5 px-2"
              >
                {{ entity }}
              </span>
              <span
                v-if="story.entities.length > 3"
                class="badge badge-muted text-[0.625rem] py-0.5 px-2"
              >
                +{{ story.entities.length - 3 }}
              </span>
            </div>
          </template>

          <!-- arXiv ID -->
          <template v-if="showArxiv && story.arxiv_id">
            <span class="meta-divider">·</span>
            <code class="arxiv-id"> arXiv:{{ story.arxiv_id }} </code>
          </template>
        </div>

        <!-- Additional links -->
        <div
          v-if="story.links.length > 1 && !compact"
          class="paper-card-links"
        >
          <a
            v-for="link in story.links.slice(0, 4)"
            :key="link.url"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
            class="paper-card-link-btn"
            :title="link.title"
          >
            <svg
              v-if="link.link_type === 'github'"
              class="w-3.5 h-3.5"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"
              />
            </svg>
            <svg
              v-else-if="link.link_type === 'arxiv'"
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
            <svg
              v-else
              class="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
              />
            </svg>
            <span>{{ getLinkTypeLabel(link.link_type) }}</span>
          </a>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
  /* ═══════════════════════════════════════════════════════════════════════════
   STORY CARD - Premium Paper Display Component
   ═══════════════════════════════════════════════════════════════════════════ */

  /* Rank badge */
  .rank-badge {
    flex-shrink: 0;
    width: 2.25rem;
    height: 2.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-lg);
    font-weight: 700;
    font-size: 0.875rem;
    background: var(--color-surface-secondary);
    color: var(--color-text-tertiary);
    border: 1px solid var(--color-border-subtle);
    transition: all var(--duration-base) var(--ease-out);
    position: relative;
  }

  .rank-badge--top {
    background: linear-gradient(135deg, rgb(216 189 122 / 0.2) 0%, rgb(136 185 171 / 0.1) 100%);
    color: var(--color-section-top);
    border-color: rgb(216 189 122 / 0.36);
    box-shadow: 0 2px 8px rgb(216 189 122 / 0.14);
  }

  .rank-badge--top::before {
    content: '';
    position: absolute;
    inset: -1px;
    border-radius: inherit;
    background: linear-gradient(135deg, rgb(216 189 122 / 0.28) 0%, transparent 50%);
    opacity: 0;
    transition: opacity var(--duration-base) var(--ease-out);
  }

  .group:hover .rank-badge {
    transform: scale(1.08) translateY(-2px);
  }

  .group:hover .rank-badge--top {
    box-shadow: 0 4px 16px rgb(216 189 122 / 0.24);
  }

  .group:hover .rank-badge--top::before {
    opacity: 1;
  }

  /* Compact variant */
  .paper-card--compact {
    padding: 0.875rem 1rem;
  }

  .paper-card--compact .paper-card-meta {
    padding-top: 0.625rem;
    margin-top: 0.5rem;
  }

  /* Title link - Enhanced hover effect */
  .paper-card-link {
    display: inline-flex;
    align-items: flex-start;
    gap: 0.5rem;
    color: var(--color-text-primary);
    text-decoration: none;
    transition: all var(--duration-fast) var(--ease-out);
    border-radius: var(--radius-sm);
    position: relative;
  }

  .paper-card-link::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    width: 0;
    height: 1px;
    background: linear-gradient(
      90deg,
      var(--color-accent-primary),
      var(--color-accent-primary-hover)
    );
    transition: width var(--duration-base) var(--ease-out);
  }

  .paper-card-link:hover {
    color: var(--color-accent-primary);
  }

  .paper-card-link:hover::after {
    width: 100%;
  }

  .paper-card-link:focus-visible {
    outline: none;
    box-shadow:
      0 0 0 2px var(--color-surface-base),
      0 0 0 4px var(--color-border-focus);
  }

  /* External link icon */
  .paper-card-external-icon {
    flex-shrink: 0;
    width: 0.875rem;
    height: 0.875rem;
    margin-top: 0.1875rem;
    opacity: 0;
    transform: translateX(-6px) translateY(4px);
    transition: all var(--duration-base) var(--ease-spring);
    color: var(--color-accent-primary);
  }

  .paper-card-link:hover .paper-card-external-icon {
    opacity: 0.8;
    transform: translateX(0) translateY(0);
  }

  /* Authors - Improved styling */
  .paper-card-authors {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    line-height: 1.5;
    display: flex;
    align-items: center;
  }

  /* Meta divider */
  .meta-divider {
    color: var(--color-border-strong);
    opacity: 0.5;
  }

  /* arXiv ID */
  .arxiv-id {
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    background: var(--color-surface-secondary);
    color: var(--color-text-tertiary);
    padding: 0.25rem 0.625rem;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-border-subtle);
    transition: all var(--duration-fast) var(--ease-out);
  }

  .group:hover .arxiv-id {
    background: var(--color-surface-overlay);
    border-color: var(--color-border-default);
  }

  /* Additional links section */
  .paper-card-links {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    padding-top: 0.875rem;
    border-top: 1px solid var(--color-border-subtle);
    margin-top: 0.375rem;
  }

  .paper-card-link-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.4375rem 0.75rem;
    font-size: 0.6875rem;
    font-weight: 600;
    color: var(--color-text-secondary);
    background: var(--color-surface-secondary);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-md);
    text-decoration: none;
    transition: all var(--duration-fast) var(--ease-out);
    position: relative;
    overflow: hidden;
  }

  .paper-card-link-btn::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, var(--color-accent-primary-glow) 0%, transparent 50%);
    opacity: 0;
    transition: opacity var(--duration-fast) var(--ease-out);
  }

  .paper-card-link-btn:hover {
    background: var(--color-surface-elevated);
    border-color: var(--color-accent-primary);
    color: var(--color-accent-primary);
    transform: translateY(-2px);
    box-shadow: var(--shadow-sm);
  }

  .paper-card-link-btn:hover::before {
    opacity: 0.5;
  }

  .paper-card-link-btn:active {
    transform: translateY(0) scale(0.97);
  }

  .paper-card-link-btn:focus-visible {
    outline: none;
    box-shadow:
      0 0 0 2px var(--color-surface-base),
      0 0 0 4px var(--color-border-focus);
  }

  /* Icon styling for link buttons */
  .paper-card-link-btn svg {
    transition: transform var(--duration-fast) var(--ease-spring);
  }

  .paper-card-link-btn:hover svg {
    transform: scale(1.1);
  }

  /* HuggingFace Metadata Display */
  .hf-metadata {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.625rem;
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
  }

  .hf-metadata-tag {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.625rem;
    background: linear-gradient(135deg, rgb(154 168 198 / 0.14) 0%, rgb(136 185 171 / 0.08) 100%);
    color: var(--color-section-models);
    border-radius: var(--radius-full);
    font-weight: 500;
    border: 1px solid rgb(154 168 198 / 0.24);
    transition: all var(--duration-fast) var(--ease-out);
  }

  .hf-metadata-tag:hover {
    background: linear-gradient(135deg, rgb(154 168 198 / 0.2) 0%, rgb(136 185 171 / 0.12) 100%);
    border-color: rgb(154 168 198 / 0.34);
  }

  .hf-metadata-stat {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    color: var(--color-text-secondary);
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    transition: color var(--duration-fast) var(--ease-out);
  }

  .hf-metadata-stat svg {
    opacity: 0.6;
  }

  .hf-metadata-stat:hover {
    color: var(--color-text-primary);
  }

  .hf-metadata-stat:hover svg {
    opacity: 0.9;
  }

  .hf-metadata-license {
    display: inline-flex;
    align-items: center;
    padding: 0.125rem 0.5rem;
    background: var(--color-surface-secondary);
    color: var(--color-text-tertiary);
    border-radius: var(--radius-sm);
    font-size: 0.625rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0;
    border: 1px solid var(--color-border-subtle);
    transition: all var(--duration-fast) var(--ease-out);
  }

  .hf-metadata-license:hover {
    background: var(--color-surface-overlay);
    border-color: var(--color-border-default);
    color: var(--color-text-secondary);
  }

  /* ═══════════════════════════════════════════════════════════════
   ENTITY / AFFILIATION BADGES
   Displayed near category badges to indicate paper origin
   ═══════════════════════════════════════════════════════════════ */

  .badge-entity {
    text-transform: none;
    letter-spacing: 0;
    font-weight: 500;
    gap: 0.3125rem;
  }

  .badge-entity-icon {
    width: 0.6875rem;
    height: 0.6875rem;
    flex-shrink: 0;
    opacity: 0.85;
  }

  /* Organization badge - cool research-network tone */
  .badge-entity-org {
    background: rgb(20 184 166 / 0.12);
    color: rgb(94 234 212);
    border: 1px solid rgb(20 184 166 / 0.25);
  }

  .badge-entity-org:hover {
    background: rgb(20 184 166 / 0.2);
    border-color: rgb(20 184 166 / 0.4);
  }

  /* Institution badge - restrained lab-accent tone */
  .badge-entity-inst {
    background: rgb(217 119 6 / 0.12);
    color: rgb(252 211 77);
    border: 1px solid rgb(217 119 6 / 0.25);
  }

  .badge-entity-inst:hover {
    background: rgb(217 119 6 / 0.2);
    border-color: rgb(217 119 6 / 0.4);
  }

  /* ═══════════════════════════════════════════════════════════════
   LLM SCORE BADGES
   Color-coded relevance indicator from LLM evaluation
   ═══════════════════════════════════════════════════════════════ */

  .badge-score {
    font-family: var(--font-mono);
    font-size: 0.625rem;
    font-weight: 600;
    gap: 0.25rem;
    letter-spacing: 0;
    transition: all var(--duration-fast) var(--ease-out);
  }

  .badge-score-high {
    background: rgb(34 197 94 / 0.14);
    color: rgb(134 239 172);
    border: 1px solid rgb(34 197 94 / 0.3);
  }

  .badge-score-high:hover {
    background: rgb(34 197 94 / 0.22);
    border-color: rgb(34 197 94 / 0.45);
  }

  .badge-score-mid {
    background: rgb(154 168 198 / 0.12);
    color: var(--color-section-models);
    border: 1px solid rgb(154 168 198 / 0.25);
  }

  .badge-score-mid:hover {
    background: rgb(154 168 198 / 0.2);
    border-color: rgb(154 168 198 / 0.4);
  }

  .badge-score-low {
    background: rgb(156 163 175 / 0.1);
    color: var(--color-text-tertiary);
    border: 1px solid rgb(156 163 175 / 0.2);
  }

  .badge-score-low:hover {
    background: rgb(156 163 175 / 0.15);
    border-color: rgb(156 163 175 / 0.3);
  }

  /* ═══════════════════════════════════════════════════════════════════════════
   LLM EVALUATION BREAKDOWN
   Rationale + six weighted component bars
   ═══════════════════════════════════════════════════════════════════════════ */

  .llm-evaluation {
    padding: 0.75rem 0.875rem;
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-md);
    background: var(--color-surface-secondary);
  }

  .llm-evaluation-rationale {
    font-size: 0.75rem;
    line-height: 1.55;
    color: var(--color-text-secondary);
    margin: 0 0 0.625rem;
  }

  .llm-evaluation-components {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .llm-component {
    display: grid;
    grid-template-columns: 8rem 1fr 2.75rem;
    align-items: center;
    gap: 0.5rem;
  }

  .llm-component-label {
    font-size: 0.6875rem;
    color: var(--color-text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .llm-component-bar {
    height: 0.375rem;
    border-radius: var(--radius-full);
    background: var(--color-surface-overlay);
    overflow: hidden;
  }

  .llm-component-fill {
    height: 100%;
    border-radius: var(--radius-full);
    background: linear-gradient(
      90deg,
      var(--color-accent-primary),
      var(--color-accent-primary-hover)
    );
    transition: width var(--duration-base) var(--ease-out);
  }

  .llm-component-value {
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    color: var(--color-text-secondary);
    text-align: right;
  }
</style>
