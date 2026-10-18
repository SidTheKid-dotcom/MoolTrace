/** Evidence sentences come from page and PMC text. Drop reference markers and stray whitespace; never add words. */
export function cleanSnippet(sentence: string | null | undefined): string {
  return (sentence || "")
    .replace(/\[(?:\d+(?:[–,-]\s*\d+)*)\]/g, "")
    .replace(/\(\s*(?:refs?\.?\s*)?\d+(?:[–,-]\s*\d+)*\s*\)/gi, "")
    .replace(/\s+([.,;:])/g, "$1")
    .replace(/\s+/g, " ")
    .trim()
}
