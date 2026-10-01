import type { SearchChunk, SearchMode } from "./types";

/**
 * Words to mark in a chunk: server-reported matches (keyword hits, or the filtered
 * entities' mention text) plus the raw query -- except in semantic mode, where the
 * query has no literal words to mark.
 */
export function matchTerms(
  chunk: Pick<SearchChunk, "highlights"> | undefined,
  query: string | null,
  searchMode: SearchMode
): string[] {
  const trimmed = searchMode === "semantic" ? "" : query?.trim();
  return [...new Set([...(chunk?.highlights ?? []), ...(trimmed ? [trimmed] : [])])];
}

/**
 * Window `text` around the first mention span (chunk-relative `anchor`) or else
 * the first occurrence of any term, so the match is actually visible inside a
 * line-clamped result row -- big chunks otherwise clip it right out of view.
 */
export function snippetRange(
  text: string,
  terms: string[],
  anchor?: number,
  radius = 150
): { start: number; end: number } {
  let matchIndex = anchor ?? -1;
  if (matchIndex === -1) {
    const lower = text.toLowerCase();
    for (const term of terms) {
      const index = lower.indexOf(term.toLowerCase());
      if (index !== -1 && (matchIndex === -1 || index < matchIndex)) matchIndex = index;
    }
  }
  if (matchIndex <= radius) return { start: 0, end: text.length };
  return { start: matchIndex - radius, end: Math.min(text.length, matchIndex + radius) };
}
