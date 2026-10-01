/** Human-readable labels for agent tool calls, shown in the chat's tool header. */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** A non-empty string arg; bare UUIDs read as "entity" -- the sources carry the names. */
function str(value: unknown): string | undefined {
  if (typeof value !== "string" || value.length === 0) return undefined;
  return UUID.test(value) ? "entity" : value;
}

/** How each entity filter reads in a label: "about X", "from X", "to X", "between X and Y". */
const ENTITY_FILTERS = [
  ["entity_ids", "about"],
  ["sent_from", "from"],
  ["sent_to", "to"],
  ["participants", "between"],
] as const;

/** "Nick Bolton" / "entity +2": one identity plus however many extra ids were passed with it. */
function describeIds(value: unknown): string | undefined {
  const ids = (Array.isArray(value) ? value : [value]).map(str).filter(Boolean);
  if (ids.length === 0) return undefined;
  return ids.length === 1 ? ids[0] : `${ids[0]} +${ids.length - 1}`;
}

/** `from entity · to entity +1 · 2020-01-01 → 2020-12-31` for whichever filters a call set. */
function describeFilters(input: Record<string, unknown>): string | undefined {
  const parts = ENTITY_FILTERS.flatMap(([key, word]) => {
    const shown = describeIds(input[key]);
    return shown ? [`${word} ${shown}`] : [];
  });
  const from = str(input.date_from);
  const to = str(input.date_to);
  if (from || to) parts.push(`${from ?? "…"} → ${to ?? "…"}`);
  return parts.length ? parts.join(" · ") : undefined;
}

function describeHops(value: unknown): string | undefined {
  return typeof value === "number" && value > 0 ? `+${value} hop${value > 1 ? "s" : ""}` : undefined;
}

const TOOL_LABELS: Record<string, string> = {
  search_passages: "Search",
  count_emails: "Counting emails",
  find_person: "Looking up person",
  list_datasets: "Listing datasets",
  find_entity: "Resolving entity",
  entity_profile: "Entity profile",
  entity_mentions: "Entity mentions",
  related_entities: "Graph traversal",
  explain_entity_resolution: "Explaining resolution",
  propose_selector_links: "Proposing address links (needs your review)",
  propose_entity_merge: "Proposing a merge (needs your review)",
  read_file: "Reading file",
};

const TOOL_DETAILS: Record<string, (input: Record<string, unknown>) => string | undefined> = {
  search_passages: (input) =>
    [str(input.query), str(input.mode), describeFilters(input), describeHops(input.connected_hops)]
      .filter(Boolean)
      .join(" · ") || undefined,
  count_emails: (input) => [str(input.group_by), describeFilters(input)].filter(Boolean).join(" · ") || undefined,
  find_person: (input) => str(input.name),
  find_entity: (input) => str(input.name) ?? str(input.selector_value),
  entity_profile: (input) => str(input.entity_id),
  entity_mentions: (input) => str(input.entity_id),
  related_entities: (input) =>
    [str(input.entity_id), str(input.relationship_type)].filter(Boolean).join(" · ") || undefined,
  read_file: (input) => str(input.file_id),
};

/** A `Label: detail` string for a tool call, falling back to the raw name. */
export function describeToolCall(toolName: string, input: unknown): string {
  const label = TOOL_LABELS[toolName] ?? toolName.replace(/_/g, " ");
  const detail = isRecord(input) ? TOOL_DETAILS[toolName]?.(input) : undefined;
  return detail ? `${label}: ${detail}` : label;
}
