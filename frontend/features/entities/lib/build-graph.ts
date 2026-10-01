import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { GRAPH_NODE_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { LOW_SIGNAL_RELATIONSHIPS, type GraphResponse } from "@/features/entities/types";

const NODE_MIN_SIZE = 5;
const NODE_MAX_SIZE = 16;
const NODE_FOCUS_SIZE = 18;

export interface BuiltGraph {
  graph: Graph;
  nodeCount: number;
  edgeCount: number;
  /** edges dropped as low-signal (`LOW_SIGNAL_RELATIONSHIPS`) */
  hiddenEdges: number;
}

/**
 * Turn a bounded traversal response into a laid-out graphology graph with
 * presentation attributes: colour by entity type, size by degree, and
 * ForceAtlas2 positions. Seeded on a circle so the layout never starts from a
 * degenerate (all-zero) state.
 */
export function buildGraph(data: GraphResponse, focusEntityId: string): BuiltGraph {
  const graph = new Graph({ multi: true, type: "directed" });

  data.nodes.forEach((node, i) => {
    if (graph.hasNode(node.id)) return;
    const meta = GRAPH_NODE_TYPE_META[node.entityType];
    const angle = (2 * Math.PI * i) / Math.max(1, data.nodes.length);
    graph.addNode(node.id, {
      label: node.displayName,
      entityType: node.entityType,
      color: meta.color,
      x: Math.cos(angle),
      y: Math.sin(angle),
      size: NODE_MIN_SIZE,
      isFocus: node.id === focusEntityId,
    });
  });

  let hiddenEdges = 0;
  data.edges.forEach((edge) => {
    if (LOW_SIGNAL_RELATIONSHIPS.includes(edge.relationshipType)) {
      hiddenEdges += 1;
      return;
    }
    if (!graph.hasNode(edge.srcEntityId) || !graph.hasNode(edge.dstEntityId)) return;
    graph.addEdge(edge.srcEntityId, edge.dstEntityId, {
      label: edge.relationshipType.replace(/_/g, " "),
      relationshipType: edge.relationshipType,
      size: 1.4,
    });
  });

  graph.forEachNode((id, attrs) => {
    if (attrs.isFocus) {
      graph.setNodeAttribute(id, "size", NODE_FOCUS_SIZE);
      return;
    }
    const scaled = NODE_MIN_SIZE + Math.sqrt(graph.degree(id)) * 2.5;
    graph.setNodeAttribute(id, "size", Math.min(NODE_MAX_SIZE, scaled));
  });

  if (graph.order > 1) {
    forceAtlas2.assign(graph, {
      iterations: Math.min(600, 150 + graph.order * 3),
      settings: {
        ...forceAtlas2.inferSettings(graph),
        barnesHutOptimize: graph.order > 60,
        adjustSizes: true,
        gravity: 0.8,
        scalingRatio: 12,
      },
    });
  }

  return {
    graph,
    nodeCount: graph.order,
    edgeCount: graph.size,
    hiddenEdges,
  };
}
