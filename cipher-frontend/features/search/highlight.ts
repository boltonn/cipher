import type { SearchChunk } from "./types";

/** ES-reported word/phrase matches when present; the raw query as fallback (pure kNN results carry no ES highlights). */
export function matchTerms(chunk: Pick<SearchChunk, "highlights"> | undefined, query: string | null): string[] {
  if (chunk?.highlights.length) return chunk.highlights;
  const trimmed = query?.trim();
  return trimmed ? [trimmed] : [];
}

/**
 * Window `text` around the first occurrence of any term so the match is
 * actually visible inside a line-clamped result row -- big chunks otherwise
 * clip the matched phrase right out of view.
 */
export function snippetAround(text: string, terms: string[], radius = 150): string {
  const lower = text.toLowerCase();
  let matchIndex = -1;
  for (const term of terms) {
    const index = lower.indexOf(term.toLowerCase());
    if (index !== -1 && (matchIndex === -1 || index < matchIndex)) matchIndex = index;
  }
  if (matchIndex <= radius) return text;
  const start = matchIndex - radius;
  const end = Math.min(text.length, matchIndex + radius);
  return `…${text.slice(start, end)}${end < text.length ? "…" : ""}`;
}
