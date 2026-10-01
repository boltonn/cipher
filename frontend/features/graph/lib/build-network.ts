import { GRAPH_NODE_TYPE_META } from "@/features/entities/components/entity-type-meta";
import {
  LOW_SIGNAL_RELATIONSHIPS,
  type EntityRelationship,
  type GraphNode,
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

export interface BuiltNetwork {
  graph: Graph;
  nodeCount: number;
  edgeCount: number;
  communityCount: number;
}

/**
 * Merge of every depth-1 response into one laid-out graphology graph. Node size
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
  const MAX_EXTRA = 7;
  const maxWeight = Math.max(1, ...edges.map((e) => e.weight ?? 1));
  const weightSpan = Math.sqrt(Math.max(1, maxWeight - 1));
  edges.forEach((edge) => {
    if (LOW_SIGNAL_RELATIONSHIPS.includes(edge.relationshipType)) return;
    if (!graph.hasNode(edge.srcEntityId) || !graph.hasNode(edge.dstEntityId)) return;
    if (graph.hasEdge(edge.srcEntityId, edge.dstEntityId)) return;
    const w = edge.weight ?? 1;
    const label =
      w > 1
        ? `${edge.relationshipType.replace(/_/g, " ")} · ${w.toLocaleString()}`
        : edge.relationshipType.replace(/_/g, " ");
    graph.addEdge(edge.srcEntityId, edge.dstEntityId, {
      label,
      relationshipType: edge.relationshipType,
      directed: edge.directed,
      relSource: edge.source,
      attributes: edge.attributes,
      srcName: graph.getNodeAttribute(edge.srcEntityId, "label"),
      dstName: graph.getNodeAttribute(edge.dstEntityId, "label"),
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
  // A->B / B->A pair. Bow each side the opposite way (sign keyed on id order) so
  // their arrowheads stop overlapping; everything else stays a straight line.
  graph.forEachEdge((edge, _attrs, src, dst) => {
    if (graph.hasDirectedEdge(dst, src)) {
      graph.mergeEdgeAttributes(edge, {
        type: "curved",
        curvature: src < dst ? RECIPROCAL_CURVATURE : -RECIPROCAL_CURVATURE,
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
