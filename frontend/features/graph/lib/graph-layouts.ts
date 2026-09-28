import type Graph from "graphology";
import { circlepack, circular, random } from "graphology-layout";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2Layout from "graphology-layout-forceatlas2/worker";
import noverlap from "graphology-layout-noverlap";

/**
 * The layout choices offered in the toolbar. `force` is ForceAtlas2 (the
 * default); the others are cheap deterministic arrangements. Every static run
 * finishes with a Noverlap anti-collision pass so nodes/labels stop overlapping.
 */
export const LAYOUT_KINDS = [
  "force",
  "circular",
  "circlepack",
  "scatter",
] as const;
export type LayoutKind = (typeof LAYOUT_KINDS)[number];

export const LAYOUT_LABELS: Record<LayoutKind, string> = {
  force: "Force",
  circular: "Circular",
  circlepack: "Cluster pack",
  scatter: "Scatter",
};

function fa2Settings(graph: Graph) {
  return {
    ...forceAtlas2.inferSettings(graph),
    barnesHutOptimize: graph.order > 60,
    adjustSizes: true,
    gravity: 0.6,
    scalingRatio: 14,
  };
}

export function applyStaticLayout(graph: Graph, kind: LayoutKind) {
  if (graph.order === 0) return;

  if (kind === "circular") {
    circular.assign(graph, { scale: Math.max(10, graph.order * 1.4) });
  } else if (kind === "circlepack") {
    circlepack.assign(graph, { hierarchyAttributes: ["community"] });
  } else if (kind === "scatter") {
    random.assign(graph, { scale: Math.max(20, graph.order * 2.2) });
  } else {
    // Deterministic circular seed so `force` settles the same way every run.
    circular.assign(graph, { scale: Math.max(10, graph.order) });
    if (graph.order > 1) {
      forceAtlas2.assign(graph, {
        iterations: Math.min(600, 150 + graph.order * 3),
        settings: fa2Settings(graph),
      });
    }
  }

  if (graph.order > 1) {
    noverlap.assign(graph, {
      maxIterations: 60,
      settings: { margin: 4, ratio: 1, gridSize: 20 },
    });
  }
}

/** A live ForceAtlas2 worker; nodes with `fixed: true` stay pinned while it runs. */
export function createLiveLayout(graph: Graph) {
  return new FA2Layout(graph, { settings: fa2Settings(graph) });
}
