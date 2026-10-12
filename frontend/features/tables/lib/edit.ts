import type { EdgeBinding, TableMapping } from "@/features/tables/types";

/**
 * Pure edits on a mapping. Whatever the user touches becomes `decisionSource: "user"`,
 * which the server keeps as-is while re-evaluating everything else around it.
 */

/** Set a column's type and role. The role decides which entity it joins (`sender`, ...); empty = the row's main party. */
export function setColumn(mapping: TableMapping, index: number, fieldType: string, role: string): TableMapping {
  const value = role.trim().toLowerCase().replace(/\s+/g, "_") || null;
  return {
    ...mapping,
    columns: mapping.columns.map((c) =>
      c.index === index ? { ...c, fieldType, role: value, decisionSource: "user", confidence: 1 } : c
    ),
  };
}

function updateEdge(mapping: TableMapping, at: number, patch: Partial<EdgeBinding>): TableMapping {
  return {
    ...mapping,
    edges: mapping.edges.map((e, i) => (i === at ? { ...e, ...patch, decisionSource: "user" } : e)),
  };
}

export function setEdge(mapping: TableMapping, at: number, verb: string, isEnabled: boolean): TableMapping {
  return updateEdge(mapping, at, { relationshipType: verb, isEnabled });
}

export function addEdge(mapping: TableMapping, srcSlot: string, verb: string, dstSlot: string): TableMapping {
  const edge: EdgeBinding = {
    srcSlot,
    dstSlot,
    relationshipType: verb,
    isProposedVerb: false,
    isEnabled: true,
    dateColumn: null,
    attributeColumns: [],
    decisionSource: "user",
  };
  return { ...mapping, edges: [...mapping.edges, edge] };
}
