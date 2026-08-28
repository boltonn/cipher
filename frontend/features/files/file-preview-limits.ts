/** Bytes; the default cap on how large a file can be before the viewer shows a
 * "too large" fallback instead of rendering it, so a huge file can't hang or
 * crash the tab. Override per filetype group below where a different budget
 * makes sense. */
export const DEFAULT_MAX_PREVIEW_BYTES = 50 * 1024 * 1024

/** Text and code are loaded fully into memory as a string (code is also
 * synchronously syntax-highlighted), so they need a tighter cap than binary
 * viewers like PDF/DOCX/XLSX that page or virtualize their content. */
export const MAX_PREVIEW_BYTES_BY_GROUP: Record<string, number> = {
  text: 10 * 1024 * 1024,
  code: 10 * 1024 * 1024,
}

export function getMaxPreviewBytes(filetypeGroup: string): number {
  return MAX_PREVIEW_BYTES_BY_GROUP[filetypeGroup] ?? DEFAULT_MAX_PREVIEW_BYTES
}
