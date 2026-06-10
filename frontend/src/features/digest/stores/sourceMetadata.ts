/**
 * Source metadata for display names and categories
 */

export type SourceCategory = 'arxiv' | 'huggingface' | 'blog' | 'other'

export interface SourceInfo {
  name: string
  category: SourceCategory
}

/**
 * Source display names mapping
 */
export const SOURCE_DISPLAY_NAMES: Record<string, SourceInfo> = {
  'arxiv-cs-ai': { name: 'arXiv cs.AI', category: 'arxiv' },
  'arxiv-cs-cl': { name: 'arXiv cs.CL', category: 'arxiv' },
  'arxiv-cs-cv': { name: 'arXiv cs.CV', category: 'arxiv' },
  'arxiv-cs-lg': { name: 'arXiv cs.LG', category: 'arxiv' },
  'arxiv-stat-ml': { name: 'arXiv stat.ML', category: 'arxiv' },
  'hf-daily-papers': { name: 'HF Daily Papers', category: 'huggingface' },
  'hf-qwen': { name: 'Qwen', category: 'huggingface' },
  'hf-openai': { name: 'OpenAI', category: 'huggingface' },
  'hf-meta-llama': { name: 'Meta Llama', category: 'huggingface' },
  'hf-google': { name: 'Google', category: 'huggingface' },
  'hf-microsoft': { name: 'Microsoft', category: 'huggingface' },
  'hf-mistralai': { name: 'Mistral AI', category: 'huggingface' },
  'hf-deepseek-ai': { name: 'DeepSeek', category: 'huggingface' },
  'hf-stabilityai': { name: 'Stability AI', category: 'huggingface' },
  'hf-cohere': { name: 'Cohere', category: 'huggingface' },
  'hf-01-ai': { name: '01.AI (Yi)', category: 'huggingface' },
  'google-ai-blog': { name: 'Google AI', category: 'blog' },
  'openai-blog': { name: 'OpenAI', category: 'blog' },
  'anthropic-research-publications': { name: 'Anthropic Research', category: 'blog' },
  'deepmind-blog': { name: 'DeepMind', category: 'blog' },
  'meta-ai-blog': { name: 'Meta AI', category: 'blog' },
  'aws-ml-blog': { name: 'AWS ML', category: 'blog' },
  'microsoft-research-blog': { name: 'Microsoft Research', category: 'blog' },
  'nvidia-ai-blog': { name: 'NVIDIA AI', category: 'blog' },
  'sebastian-raschka-blog': { name: 'Sebastian Raschka', category: 'blog' },
  'papers-with-code': { name: 'Papers With Code', category: 'other' },
}

/**
 * Category display names for arXiv categories
 */
export const CATEGORY_DISPLAY_NAMES: Record<string, string> = {
  'cs.AI': 'Artificial Intelligence',
  'cs.CL': 'Computation & Language',
  'cs.CV': 'Computer Vision',
  'cs.LG': 'Machine Learning',
  'stat.ML': 'Statistical ML',
  'cs.NE': 'Neural & Evolutionary',
  'cs.RO': 'Robotics',
  'cs.SE': 'Software Engineering',
}

/**
 * Get source display name and category info
 */
export function getSourceInfo(sourceId: string): SourceInfo {
  const info = SOURCE_DISPLAY_NAMES[sourceId]
  if (info) return info
  // Fallback: format source ID
  const name = sourceId
    .replace(/^(hf|arxiv)-/, '')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
  return { name, category: 'other' }
}

/**
 * Get category display name
 */
export function getCategoryDisplayName(category: string): string {
  return CATEGORY_DISPLAY_NAMES[category] || category
}
