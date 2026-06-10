/**
 * Composable for decoding LaTeX escape sequences
 * Commonly found in arXiv paper data
 */

// Convert digits/letters to Unicode superscript
const superscriptMap: Record<string, string> = {
  '0': '⁰',
  '1': '¹',
  '2': '²',
  '3': '³',
  '4': '⁴',
  '5': '⁵',
  '6': '⁶',
  '7': '⁷',
  '8': '⁸',
  '9': '⁹',
  '+': '⁺',
  '-': '⁻',
  '=': '⁼',
  '(': '⁽',
  ')': '⁾',
  n: 'ⁿ',
  i: 'ⁱ',
}

// Convert digits/letters to Unicode subscript
const subscriptMap: Record<string, string> = {
  '0': '₀',
  '1': '₁',
  '2': '₂',
  '3': '₃',
  '4': '₄',
  '5': '₅',
  '6': '₆',
  '7': '₇',
  '8': '₈',
  '9': '₉',
  '+': '₊',
  '-': '₋',
  '=': '₌',
  '(': '₍',
  ')': '₎',
  a: 'ₐ',
  e: 'ₑ',
  o: 'ₒ',
  x: 'ₓ',
}

/**
 * Convert string to Unicode superscript
 */
export function toSuperscript(str: string): string {
  return str
    .split('')
    .map((c) => superscriptMap[c] || c)
    .join('')
}

/**
 * Convert string to Unicode subscript
 */
export function toSubscript(str: string): string {
  return str
    .split('')
    .map((c) => subscriptMap[c] || c)
    .join('')
}

/**
 * Decode LaTeX escape sequences commonly found in arXiv data
 */
export function decodeLatex(text: string): string {
  if (!text) return text

  // First handle math mode superscripts and subscripts
  const result = text
    // Superscripts in math mode: $^{...}$ or $^X$
    .replace(/\$\^{([^}]+)}\$/g, (_, content) => toSuperscript(content))
    .replace(/\$\^([0-9a-zA-Z])\$/g, (_, char) => toSuperscript(char))
    // Subscripts in math mode: $_{...}$ or $_X$
    .replace(/\$_{([^}]+)}\$/g, (_, content) => toSubscript(content))
    .replace(/\$_([0-9a-zA-Z])\$/g, (_, char) => toSubscript(char))
    // Remove remaining empty math delimiters
    .replace(/\$\$/g, '')

  return (
    result
      // Accented characters
      .replace(/\\'e/g, 'é')
      .replace(/\\'a/g, 'á')
      .replace(/\\'i/g, 'í')
      .replace(/\\'o/g, 'ó')
      .replace(/\\'u/g, 'ú')
      .replace(/\\"e/g, 'ë')
      .replace(/\\"a/g, 'ä')
      .replace(/\\"i/g, 'ï')
      .replace(/\\"o/g, 'ö')
      .replace(/\\"u/g, 'ü')
      .replace(/\\`e/g, 'è')
      .replace(/\\`a/g, 'à')
      .replace(/\\`i/g, 'ì')
      .replace(/\\`o/g, 'ò')
      .replace(/\\`u/g, 'ù')
      .replace(/\\~n/g, 'ñ')
      .replace(/\\c\{c\}/g, 'ç')
      .replace(/\\c c/g, 'ç')
      .replace(/\\\^e/g, 'ê')
      .replace(/\\\^a/g, 'â')
      .replace(/\\\^i/g, 'î')
      .replace(/\\\^o/g, 'ô')
      .replace(/\\\^u/g, 'û')
      // Common LaTeX symbols
      .replace(/\\&/g, '&')
      .replace(/\\\$/g, '$')
      .replace(/\\%/g, '%')
      .replace(/\\_/g, '_')
      .replace(/\\#/g, '#')
      .replace(/\\{/g, '{')
      .replace(/\\}/g, '}')
      // Handle remaining backslash escapes
      .replace(/\\\\/g, '')
  )
}

/**
 * Strip HTML tags from text
 */
export function stripHtml(html: string): string {
  return html
    .replace(/<[^>]*>/g, '')
    .replace(/&[a-zA-Z0-9#]+;/g, ' ')
    .trim()
}

/**
 * Clean arXiv metadata prefix from summary
 */
export function cleanArxivPrefix(text: string): string {
  return text
    .replace(
      /^arXiv:\d+\.\d+(?:v\d+)?\s+Announce Type:\s*[\w-]+\s*Abstract:\s*/i,
      '',
    )
    .trim()
}

/**
 * Clean LaTeX emphasis and formatting commands from text
 */
export function cleanLatexEmphasis(text: string): string {
  return (
    text
      // Handle {\em text} -> text
      .replace(/\{\\em\s+([^}]+)\}/g, '$1')
      // Handle \emph{text} -> text
      .replace(/\\emph\{([^}]+)\}/g, '$1')
      // Handle {\it text} -> text
      .replace(/\{\\it\s+([^}]+)\}/g, '$1')
      // Handle {\bf text} -> text
      .replace(/\{\\bf\s+([^}]+)\}/g, '$1')
      // Handle \textit{text} -> text
      .replace(/\\textit\{([^}]+)\}/g, '$1')
      // Handle \textbf{text} -> text
      .replace(/\\textbf\{([^}]+)\}/g, '$1')
  )
}

/**
 * Check if text looks like image alt text (not a real summary)
 */
export function looksLikeImageAlt(text: string): boolean {
  const altPatterns = [
    /^illustration\s+of\s+/i,
    /^image\s+of\s+/i,
    /^photo\s+of\s+/i,
    /^screenshot\s+of\s+/i,
    /^diagram\s+(of|showing)\s+/i,
    /^figure\s+\d+/i,
    /^a\s+(photo|image|illustration)\s+/i,
  ]
  return altPatterns.some((pattern) => pattern.test(text.trim()))
}

/**
 * Composable that returns all LaTeX decoder functions
 */
export function useLatexDecoder() {
  return {
    decodeLatex,
    toSuperscript,
    toSubscript,
    stripHtml,
    cleanArxivPrefix,
    cleanLatexEmphasis,
    looksLikeImageAlt,
  }
}
