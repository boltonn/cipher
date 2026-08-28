/** Human-readable labels for agent tool calls, shown in the chat's tool header. */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

const TOOL_LABELS: Record<string, string> = {
  search_text: "Keyword search",
  search_semantic: "Semantic search",
  search_hybrid: "Search",
  find_person: "Looking up person",
  list_datasets: "Listing datasets",
  find_entity: "Resolving entity",
  entity_profile: "Entity profile",
  entity_mentions: "Entity mentions",
  related_entities: "Graph traversal",
  read_file: "Reading file",
};

const TOOL_DETAILS: Record<string, (input: Record<string, unknown>) => string | undefined> = {
  search_text: (input) => str(input.query),
  search_semantic: (input) => str(input.query),
  search_hybrid: (input) => str(input.query),
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
