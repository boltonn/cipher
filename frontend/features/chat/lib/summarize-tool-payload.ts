/** Trims agent tool JSON before it's shown in the chat trace: drops embedding
 * vectors and clamps very long text so a raw `entity_profile` / `read_file`
 * payload doesn't dump kilobytes of numbers or prose inline. */

const DROP_KEYS = new Set(["embedding", "nameEmbedding", "nameEmbedding", "vector"]);
const MAX_STRING = 600;

// Keyed by object/array reference so re-renders that walk the same finished
// payload (the message list re-renders on every stream tick) don't redo the walk.
const cache = new WeakMap<object, unknown>();

export function summarizeToolPayload(value: unknown): unknown {
  if (typeof value === "string") {
    return value.length > MAX_STRING ? `${value.slice(0, MAX_STRING)}… (${value.length} chars)` : value;
  }
  if (value === null || typeof value !== "object") return value;

  const cached = cache.get(value);
  if (cached !== undefined) return cached;

  let result: unknown;
  if (Array.isArray(value)) {
    result =
      value.length > 20
        ? [...value.slice(0, 20).map(summarizeToolPayload), `… ${value.length - 20} more`]
        : value.map(summarizeToolPayload);
  } else {
    result = Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, val]) =>
        DROP_KEYS.has(key) && Array.isArray(val)
          ? [key, `[${val.length}-dim vector]`]
          : [key, summarizeToolPayload(val)]
      )
    );
  }
  cache.set(value, result);
  return result;
}
