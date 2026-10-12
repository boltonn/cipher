import { GRAPH_NODE_TYPE_META } from "@/features/entities/components/entity-type-meta";
import {
  LOW_SIGNAL_RELATIONSHIPS,
  type EntityRelationship,
  type GraphNode,
  type RelationshipType,
} from "@/features/entities/types";
import { annotateAnalytics } from "@/features/graph/lib/graph-analytics";
import {
  applyStaticLayout,
  type LayoutKind,
} from "@/features/graph/lib/graph-layouts";
import {
  guessSelectorType,
  nodeGlyphUrl,
} from "@/features/graph/lib/node-glyphs";
import Graph from "graphology";
import { humanize } from "@/lib/utils";

const NODE_MIN = 5;
const NODE_MAX = 22;
const SEED_SIZE = 20;
const RECIPROCAL_CURVATURE = 0.25;

export interface NetworkInput {
  nodes: GraphNode[];
  edges: EntityRelationship[];
  seedIds: ReadonlySet<string>;
  expandedIds: ReadonlySet<string>;
  layout: LayoutKind;
  /** user-dragged node positions, re-applied on top of the fresh layout */
  pinned: ReadonlyMap<string, { x: number; y: number }>;
}

/** One stored relationship riding on a drawn edge (an edge carries every type between its two nodes). */
export interface EdgeRelationship {
  relationshipType: RelationshipType;
  directed: boolean;
  weight: number;
  source: string;
  attributes: Record<string, unknown>;
  dateStart: number | null;
  dateEnd: number | null;
}

const relationshipLabel = (r: EdgeRelationship) =>
  r.weight > 1
    ? `${humanize(r.relationshipType)} · ${r.weight.toLocaleString()}`
    : humanize(r.relationshipType);

export interface BuiltNetwork {
  graph: Graph;
  nodeCount: number;
  edgeCount: number;
  communityCount: number;
}

/**
 * Merge of every depth-1 response into one laid-out graphology graph. Two nodes
 * share at most one drawn edge per direction; when several relationship types
 * run the same way (emailed + family of) they ride on it as `relationships`,
 * heaviest first, rather than the later ones being dropped. Node size
 * is `sqrt(degree)` (seeds fixed larger); edge width is `sqrt(weight)`. Layout,
 * Louvain communities and PageRank are baked in here; visibility (type filters,
 * hidden nodes, selection focus, colour/size mode, path highlight) is NOT -- the
 * canvas applies that via sigma reducers so the layout stays put when a control
 * toggles.
 */
export function buildNetwork({
  nodes,
  edges,
  seedIds,
  expandedIds,
  layout,
  pinned,
}: NetworkInput): BuiltNetwork {
  const graph = new Graph({ multi: false, type: "directed" });

  nodes.forEach((node, i) => {
    if (graph.hasNode(node.id)) return;
    const meta = GRAPH_NODE_TYPE_META[node.entityType];
    const angle = (2 * Math.PI * i) / Math.max(1, nodes.length);
    const radius = 8 + i * 0.12;
    const selectorType =
      node.entityType === "selector"
        ? guessSelectorType(node.displayName)
        : null;
    graph.addNode(node.id, {
      label: node.displayName,
      entityType: node.entityType,
      type: "entity",
      image: nodeGlyphUrl(node.entityType, selectorType),
      color: meta.color,
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
      size: NODE_MIN,
      isSeed: seedIds.has(node.id),
      isExpanded: expandedIds.has(node.id),
      isVerified: node.isVerified,
    });
  });

  // Edge thickness encodes weight (e.g. emails sent on emailed).
  // Weight 1 (the default -- most typed edges have none) sits at a thin
  // baseline; only genuinely weighted edges scale up, so a heavy edge reads as
  // heavy rather than everything looking the same.
  const BASE = 1.4;
  const MAX_EXTRA = 4;
  const maxWeight = Math.max(1, ...edges.map((e) => e.weight ?? 1));
  const weightSpan = Math.sqrt(Math.max(1, maxWeight - 1));
  const bySrcDst = new Map<string, { src: string; dst: string; rels: EdgeRelationship[] }>();
  edges.forEach((edge) => {
    if (LOW_SIGNAL_RELATIONSHIPS.includes(edge.relationshipType)) return;
    if (!graph.hasNode(edge.srcEntityId) || !graph.hasNode(edge.dstEntityId)) return;
    const key = `${edge.srcEntityId} ${edge.dstEntityId}`;
    const group = bySrcDst.get(key) ?? {
      src: edge.srcEntityId,
      dst: edge.dstEntityId,
      rels: [],
    };
    group.rels.push({
      relationshipType: edge.relationshipType,
      directed: edge.directed,
      weight: edge.weight ?? 1,
      source: edge.source,
      attributes: edge.attributes,
      dateStart: edge.dateObservedStart ? Date.parse(edge.dateObservedStart) : null,
      dateEnd: edge.dateObservedEnd ? Date.parse(edge.dateObservedEnd) : null,
    });
    bySrcDst.set(key, group);
  });
  bySrcDst.forEach(({ src, dst, rels }) => {
    const relationships = rels.toSorted((a, b) => b.weight - a.weight);
    const w = relationships[0].weight;
    // one undated relationship keeps the whole edge outside the time filter
    const dated = relationships.every((r) => r.dateStart != null);
    graph.addEdge(src, dst, {
      label: relationships.map(relationshipLabel).join(" + "),
      relationships,
      relationshipType: relationships[0].relationshipType,
      dateStart: dated ? Math.min(...relationships.map((r) => r.dateStart as number)) : null,
      dateEnd: dated
        ? Math.max(...relationships.map((r) => r.dateEnd ?? (r.dateStart as number)))
        : null,
      srcName: graph.getNodeAttribute(src, "label"),
      dstName: graph.getNodeAttribute(dst, "label"),
      weight: w,
      type: "straight",
      size: w <= 1 ? BASE : BASE + (Math.sqrt(w - 1) / weightSpan) * MAX_EXTRA,
    });
  });

  const analytics = annotateAnalytics(graph);

  graph.forEachNode((id, attrs) => {
    const byDegree = attrs.isSeed
      ? SEED_SIZE
      : Math.min(NODE_MAX, NODE_MIN + Math.sqrt(graph.degree(id)) * 3);
    const rank = (attrs.pagerank as number) ?? 0;
    const byImportance = attrs.isSeed
      ? SEED_SIZE
      : NODE_MIN +
        Math.sqrt(analytics.maxPagerank > 0 ? rank / analytics.maxPagerank : 0) *
          (NODE_MAX - NODE_MIN);
    graph.mergeNodeAttributes(id, {
      size: byDegree,
      sizeByDegree: byDegree,
      sizeByImportance: byImportance,
    });
  });

  // The graph is simple + directed, so the only "parallel" case is a reciprocal
  // A->B / B->A pair. Give both the same curvature: each bows relative to its
  // own direction, so the pair opens into a lens instead of overlapping (opposite
  // signs cancel out and draw both on one arc). Everything else stays straight.
  graph.forEachEdge((edge, _attrs, src, dst) => {
    if (graph.hasDirectedEdge(dst, src)) {
      graph.mergeEdgeAttributes(edge, {
        type: "curved",
        curvature: RECIPROCAL_CURVATURE,
      });
    } else {
      graph.setEdgeAttribute(edge, "type", "straight");
    }
  });

  applyStaticLayout(graph, layout);
  pinned.forEach((pos, id) => {
    if (graph.hasNode(id)) {
      graph.mergeNodeAttributes(id, { x: pos.x, y: pos.y, fixed: true });
    }
  });

  return {
    graph,
    nodeCount: graph.order,
    edgeCount: graph.size,
    communityCount: analytics.communityCount,
  };
}

/** Node ids within one hop of `id` (plus `id` itself). Used by "isolate". */
export function neighbourhood(graph: Graph, id: string): Set<string> {
  const set = new Set<string>([id]);
  if (graph.hasNode(id)) graph.forEachNeighbor(id, (n) => set.add(n));
  return set;
}
