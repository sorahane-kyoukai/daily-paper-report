/**
 * Composable for number formatting utilities
 */

/**
 * Format large numbers with K/M suffix
 */
export function formatNumber(num: number): string {
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(1)}M`
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(1)}K`
  }
  return num.toString()
}

/**
 * Format pipeline tag for display (e.g., "text-generation" -> "Text Generation")
 */
export function formatPipelineTag(tag: string): string {
  return tag
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Format source ID to readable name
 */
export function formatSourceId(sourceId: string): string {
  return sourceId
    .replace(/^hf-/, '')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/**
 * Composable that returns all number formatting functions
 */
export function useNumberFormat() {
  return {
    formatNumber,
    formatPipelineTag,
    formatSourceId,
  }
}
