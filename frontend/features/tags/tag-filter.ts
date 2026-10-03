import type { TagFilterState, TagFilterValue } from "./types";

const FIELDS: Record<TagFilterState, keyof TagFilterValue> = {
  positive: "tags",
  negative: "negativeTags",
  predicted: "predictedTags",
};

/** Every filtered tag with its state, in the order positive, negative, predicted. */
export function tagFilterEntries(
  value: TagFilterValue
): { tag: string; state: TagFilterState }[] {
  return (Object.keys(FIELDS) as TagFilterState[]).flatMap((state) =>
    (value[FIELDS[state]] ?? []).map((tag) => ({ tag, state }))
  );
}

export function tagFilterState(
  value: TagFilterValue,
  tag: string
): TagFilterState | undefined {
  return tagFilterEntries(value).find((entry) => entry.tag === tag)?.state;
}

/** Put `tag` in `state`'s list (and out of the others); `undefined` drops it. Empty lists become undefined. */
export function withTagFilterState(
  value: TagFilterValue,
  tag: string,
  state: TagFilterState | undefined
): TagFilterValue {
  const next: TagFilterValue = {};
  for (const [fieldState, field] of Object.entries(FIELDS) as [
    TagFilterState,
    keyof TagFilterValue,
  ][]) {
    const tags = (value[field] ?? []).filter((t) => t !== tag);
    if (fieldState === state) tags.push(tag);
    next[field] = tags.length ? tags : undefined;
  }
  return next;
}

/** Click order: off -> positive -> negative -> (predicted) -> off. */
export function nextTagFilterState(
  state: TagFilterState | undefined,
  allowPredicted: boolean
): TagFilterState | undefined {
  if (state === undefined) return "positive";
  if (state === "positive") return "negative";
  if (state === "negative" && allowPredicted) return "predicted";
  return undefined;
}

export function hasTagFilters(value: TagFilterValue): boolean {
  return tagFilterEntries(value).length > 0;
}
