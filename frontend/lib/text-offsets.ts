/**
 * Backend offsets (mention spans, chunk spans) count Unicode code points -- Python string
 * indices. JavaScript strings index UTF-16 code units, where an emoji or other astral
 * character (📞) takes two. Convert at the boundary, or every span after one drifts left.
 */
export interface TextOffsets {
  /** code-point offset (backend) -> UTF-16 index (JS) */
  toUtf16: (codePoint: number) => number;
  /** UTF-16 index (JS) -> code-point offset (backend) */
  toCodePoint: (utf16: number) => number;
}

const SURROGATE = /[\uD800-\uDFFF]/;
const IDENTITY: TextOffsets = { toUtf16: (i) => i, toCodePoint: (i) => i };

export function textOffsets(text: string): TextOffsets {
  if (!SURROGATE.test(text)) return IDENTITY;
  const utf16At: number[] = []; // code point -> UTF-16 index
  const codePointAt = new Int32Array(text.length + 1); // UTF-16 index -> code point
  let unit = 0;
  for (const char of text) {
    codePointAt[unit] = utf16At.length;
    if (char.length === 2) codePointAt[unit + 1] = utf16At.length + 1; // inside a pair: round up
    utf16At.push(unit);
    unit += char.length;
  }
  utf16At.push(unit);
  codePointAt[unit] = utf16At.length - 1;
  return {
    toUtf16: (i) => utf16At[Math.min(Math.max(i, 0), utf16At.length - 1)],
    toCodePoint: (i) => codePointAt[Math.min(Math.max(i, 0), text.length)],
  };
}
