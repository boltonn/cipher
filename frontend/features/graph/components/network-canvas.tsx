"use client";

import type {
  EntityType,
  RelationshipType,
} from "@/features/entities/types";
import type { ColorMode, SizeMode } from "@/features/graph/hooks/use-graph-explore";
import type { BuiltNetwork } from "@/features/graph/lib/build-network";
import {
  makeHoverRenderer,
  makeLabelRenderer,
  resolveColor,
} from "@/features/graph/lib/canvas-helpers";
import { pathEdgeKeys } from "@/features/graph/lib/graph-analytics";
import { createLiveLayout } from "@/features/graph/lib/graph-layouts";
import { makeGraphPrograms } from "@/features/graph/lib/graph-programs";
import { useTheme } from "@/providers/theme-provider";
import { downloadAsPNG } from "@sigma/export-image";
import { Maximize2, Minus, Plus } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import Sigma from "sigma";

/**
 * Browser-only sigma renderer for the network viewer -- loaded via
 * `next/dynamic({ ssr: false })` because `sigma@3` reads `WebGL2RenderingContext`
 * at module scope. Layout is fixed by {@link BuiltNetwork}; this paints it and
 * applies visibility / colour / size / highlight via reducers, hosts node
 * dragging + an optional live ForceAtlas2 worker, and exports the canvas to PNG.
 */

const LABEL_FONT = "Inter, ui-sans-serif, system-ui, sans-serif";

export type LabelsMode = "all" | "hover" | "off";

export interface EdgePick {
  id: string;
  relationshipType: RelationshipType;
  directed: boolean;
  weight: number;
  source: string;
  attributes: Record<string, unknown>;
  srcId: string;
  dstId: string;
  srcName: string;
  dstName: string;
}

export interface NetworkCanvasProps {
  built: BuiltNetwork;
  hiddenIds: ReadonlySet<string>;
  /** empty = all types visible */
  visibleTypes: EntityType[];
  /** empty = all relationship types visible */
  visibleRelTypes: RelationshipType[];
  labelsMode: LabelsMode;
  labelDensity: number;
  colorMode: ColorMode;
  sizeMode: SizeMode;
  liveLayout: boolean;
  selectedId: string | null;
  highlightIds: ReadonlySet<string>;
  pathIds: readonly string[];
  pathAnchors: readonly string[];
  /** bump to trigger a PNG download */
  exportNonce: number;
  onSelect: (id: string | null) => void;
  onSelectEdge: (edge: EdgePick | null) => void;
  onNodeContextMenu: (
    payload: { id: string; clientX: number; clientY: number } | null
  ) => void;
  onDragEnd: (id: string, pos: { x: number; y: number }) => void;
  /** double-click a node to pull its neighbours */
  onExpand: (id: string) => void;
}

interface CanvasState {
  hiddenIds: ReadonlySet<string>;
  visibleTypes: EntityType[];
  visibleRelTypes: RelationshipType[];
  labelsMode: LabelsMode;
  colorMode: ColorMode;
  sizeMode: SizeMode;
  selectedId: string | null;
  highlightIds: ReadonlySet<string>;
  pathIds: readonly string[];
  pathAnchors: readonly string[];
  pathSet: ReadonlySet<string>;
  pathEdges: ReadonlySet<string>;
}

export function NetworkCanvas({
  built,
  hiddenIds,
  visibleTypes,
  visibleRelTypes,
  labelsMode,
  labelDensity,
  colorMode,
  sizeMode,
  liveLayout,
  selectedId,
  highlightIds,
  pathIds,
  pathAnchors,
  exportNonce,
  onSelect,
  onSelectEdge,
  onNodeContextMenu,
  onDragEnd,
  onExpand,
}: NetworkCanvasProps) {
  const { resolvedTheme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const [sigmaInstance, setSigmaInstance] = useState<Sigma | null>(null);
  const hoveredRef = useRef<string | null>(null);
  const draggedRef = useRef<string | null>(null);
  const prevSelectedRef = useRef<string | null>(null);

  const stateRef = useRef<CanvasState>({
    hiddenIds,
    visibleTypes,
    visibleRelTypes,
    labelsMode,
    colorMode,
    sizeMode,
    selectedId,
    highlightIds,
    pathIds,
    pathAnchors,
    pathSet: new Set(),
    pathEdges: new Set(),
  });
  useEffect(() => {
    stateRef.current = {
      hiddenIds,
      visibleTypes,
      visibleRelTypes,
      labelsMode,
      colorMode,
      sizeMode,
      selectedId,
      highlightIds,
      pathIds,
      pathAnchors,
      pathSet: new Set(pathIds),
      pathEdges: pathEdgeKeys(pathIds),
    };
    const sigma = sigmaRef.current;
    if (!sigma) return;
    sigma.setSetting("renderLabels", labelsMode !== "off");
    sigma.setSetting("labelDensity", labelDensity);

    // Fly to a newly selected node.
    if (selectedId && selectedId !== prevSelectedRef.current) {
      const dd = sigma.getNodeDisplayData(selectedId);
      if (dd) {
        const cam = sigma.getCamera();
        cam.animate(
          { x: dd.x, y: dd.y, ratio: Math.min(cam.ratio, 0.7) },
          { duration: 400 }
        );
      }
    }
    prevSelectedRef.current = selectedId;

    sigma.refresh({ skipIndexation: true });
  }, [
    hiddenIds,
    visibleTypes,
    visibleRelTypes,
    labelsMode,
    labelDensity,
    colorMode,
    sizeMode,
    selectedId,
    highlightIds,
    pathIds,
    pathAnchors,
  ]);

  const cbRef = useRef({
    onSelect,
    onSelectEdge,
    onNodeContextMenu,
    onDragEnd,
    onExpand,
  });
  useEffect(() => {
    cbRef.current = {
      onSelect,
      onSelectEdge,
      onNodeContextMenu,
      onDragEnd,
      onExpand,
    };
  });

  useEffect(() => {
    if (!containerRef.current || built.nodeCount === 0) return;

    const graph = built.graph;
    const chip = {
      text: resolveColor("--foreground", "#f5f5f7"),
      chip: resolveColor("--popover", "#222226"),
      border: resolveColor("--border", "#2c2c31"),
    };
    const mutedColor = resolveColor("--muted-foreground", "#8a8a94");
    const edgeColor = resolveColor("--border", "#2c2c31");
    const dimColor = resolveColor("--secondary", "#303036");
    const pathColor = resolveColor("--primary", "#7c9cff");
    const { nodeProgramClasses, edgeProgramClasses } = makeGraphPrograms();

    const nodeVisible = (node: string, attrs: Record<string, unknown>) => {
      const s = stateRef.current;
      if (s.hiddenIds.has(node)) return false;
      if (
        s.visibleTypes.length &&
        !s.visibleTypes.includes(attrs.entityType as EntityType)
      )
        return false;
      return true;
    };

    const dim = (attrs: Record<string, unknown>) => ({
      ...attrs,
      type: "circle",
      image: undefined,
      color: dimColor,
      label: "",
      zIndex: 0,
    });

    const renderer = new Sigma(graph, containerRef.current, {
      renderLabels: labelsMode !== "off",
      renderEdgeLabels: true,
      labelFont: LABEL_FONT,
      labelSize: 12,
      labelWeight: "600",
      labelColor: { color: chip.text },
      labelDensity,
      labelGridCellSize: 60,
      labelRenderedSizeThreshold: 6,
      edgeLabelFont: LABEL_FONT,
      edgeLabelSize: 9,
      edgeLabelColor: { color: mutedColor },
      defaultNodeType: "entity",
      defaultEdgeType: "straight",
      defaultEdgeColor: edgeColor,
      minEdgeThickness: 1,
      enableEdgeEvents: true,
      zIndex: true,
      minCameraRatio: 0.05,
      maxCameraRatio: 12,
      nodeProgramClasses,
      edgeProgramClasses,
      defaultDrawNodeLabel: makeLabelRenderer(chip),
      defaultDrawNodeHover: makeHoverRenderer(chip),
      nodeReducer: (node, data) => {
        const s = stateRef.current;
        if (!nodeVisible(node, data)) return { ...data, hidden: true };

        const attrs: Record<string, unknown> = { ...data };
        attrs.size =
          s.sizeMode === "importance"
            ? ((data.sizeByImportance as number) ?? data.size)
            : ((data.sizeByDegree as number) ?? data.size);
        attrs.color =
          s.colorMode === "community"
            ? ((data.communityColor as string) ?? data.color)
            : data.color;

        if (s.pathIds.length) {
          if (s.pathSet.has(node)) {
            return {
              ...attrs,
              forceLabel: true,
              zIndex: 3,
              highlighted: s.pathAnchors.includes(node),
            };
          }
          return dim(attrs);
        }

        const focus = hoveredRef.current ?? s.selectedId;

        if (s.highlightIds.size) {
          if (s.highlightIds.has(node)) {
            return { ...attrs, forceLabel: true, zIndex: 2, highlighted: true };
          }
          if (!focus || (node !== focus && !graph.areNeighbors(focus, node))) {
            return dim(attrs);
          }
        }

        if (focus) {
          if (node === focus || graph.areNeighbors(focus, node)) {
            return { ...attrs, forceLabel: true, zIndex: 1 };
          }
          return dim(attrs);
        }
        if (s.labelsMode === "hover" && !data.isSeed) {
          return { ...attrs, label: "" };
        }
        if (data.isSeed) return { ...attrs, forceLabel: true, zIndex: 1 };
        return attrs;
      },
      edgeReducer: (edge, data) => {
        const s = stateRef.current;
        const [src, dst] = graph.extremities(edge);
        if (
          !nodeVisible(src, graph.getNodeAttributes(src)) ||
          !nodeVisible(dst, graph.getNodeAttributes(dst))
        )
          return { ...data, hidden: true };
        if (
          s.visibleRelTypes.length &&
          !s.visibleRelTypes.includes(data.relationshipType as RelationshipType)
        )
          return { ...data, hidden: true };

        if (s.pathIds.length) {
          if (s.pathEdges.has(`${src} ${dst}`)) {
            return {
              ...data,
              forceLabel: true,
              color: pathColor,
              size: Math.max((data.size as number) ?? 2, 3),
              zIndex: 3,
            };
          }
          return { ...data, hidden: true };
        }

        const focus = hoveredRef.current ?? s.selectedId;
        if (!focus) return { ...data, label: "" };
        if (graph.hasExtremity(edge, focus)) return { ...data, forceLabel: true };
        return { ...data, hidden: true };
      },
    });

    const rerender = () => renderer.refresh({ skipIndexation: true });
    renderer.on("enterNode", ({ node }) => {
      if (draggedRef.current) return;
      hoveredRef.current = node;
      rerender();
    });
    renderer.on("leaveNode", () => {
      if (draggedRef.current) return;
      hoveredRef.current = null;
      rerender();
    });
    renderer.on("clickNode", ({ node }) => cbRef.current.onSelect(node));
    renderer.on("doubleClickNode", (e) => {
      e.preventSigmaDefault();
      cbRef.current.onExpand(e.node);
    });
    renderer.on("clickEdge", ({ edge }) => {
      const a = graph.getEdgeAttributes(edge);
      const [s, d] = graph.extremities(edge);
      cbRef.current.onSelectEdge({
        id: edge,
        relationshipType: a.relationshipType as RelationshipType,
        directed: Boolean(a.directed),
        weight: (a.weight as number) ?? 1,
        source: (a.relSource as string) ?? "",
        attributes: (a.attributes as Record<string, unknown>) ?? {},
        srcId: s,
        dstId: d,
        srcName: (a.srcName as string) ?? s,
        dstName: (a.dstName as string) ?? d,
      });
    });
    renderer.on("rightClickNode", ({ node, event }) => {
      const orig = event.original;
      if (!("clientX" in orig)) return;
      orig.preventDefault();
      cbRef.current.onNodeContextMenu({
        id: node,
        clientX: orig.clientX,
        clientY: orig.clientY,
      });
    });
    renderer.on("clickStage", () => {
      cbRef.current.onSelect(null);
      cbRef.current.onSelectEdge(null);
      cbRef.current.onNodeContextMenu(null);
    });

    // Node dragging (the canonical sigma@3 recipe: freeze the camera bbox and
    // swallow the stage-pan via preventSigmaDefault while a node is held).
    renderer.on("downNode", ({ node }) => {
      draggedRef.current = node;
      graph.setNodeAttribute(node, "highlighted", true);
      graph.setNodeAttribute(node, "fixed", true);
      if (!renderer.getCustomBBox()) renderer.setCustomBBox(renderer.getBBox());
    });
    renderer.on("moveBody", ({ event }) => {
      const node = draggedRef.current;
      if (!node) return;
      const pos = renderer.viewportToGraph(event);
      graph.setNodeAttribute(node, "x", pos.x);
      graph.setNodeAttribute(node, "y", pos.y);
      event.preventSigmaDefault();
      event.original.preventDefault();
      event.original.stopPropagation();
    });
    const drop = () => {
      const node = draggedRef.current;
      draggedRef.current = null;
      if (!node) return;
      graph.removeNodeAttribute(node, "highlighted");
      cbRef.current.onDragEnd(node, {
        x: graph.getNodeAttribute(node, "x") as number,
        y: graph.getNodeAttribute(node, "y") as number,
      });
    };
    renderer.on("upNode", drop);
    renderer.on("upStage", drop);

    sigmaRef.current = renderer;
    setSigmaInstance(renderer);

    // The node-image texture atlas builds async (debounced ~500ms); repaint once
    // it has almost certainly landed so glyphs show without an interaction.
    const atlasPaint = window.setTimeout(() => {
      renderer.refresh({ skipIndexation: true });
    }, 650);

    return () => {
      window.clearTimeout(atlasPaint);
      renderer.kill();
      sigmaRef.current = null;
      setSigmaInstance(null);
      hoveredRef.current = null;
      draggedRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- live settings handled via setSetting
  }, [built, resolvedTheme]);

  // Live ForceAtlas2 worker; pinned (dragged) nodes stay put while it runs.
  useEffect(() => {
    if (!sigmaInstance || !liveLayout || built.nodeCount < 2) return;
    const layout = createLiveLayout(built.graph);
    layout.start();
    return () => {
      layout.stop();
      layout.kill();
    };
  }, [sigmaInstance, liveLayout, built]);

  // PNG export (parent bumps `exportNonce`).
  useEffect(() => {
    if (!exportNonce || !sigmaRef.current) return;
    void downloadAsPNG(sigmaRef.current, {
      fileName: "network.png",
      backgroundColor: resolveColor("--background", "#0b0b0c"),
    });
  }, [exportNonce]);

  return (
    <div
      className="relative h-full w-full overflow-hidden rounded-xl border border-border bg-background"
      onContextMenu={(e) => e.preventDefault()}
    >
      <div ref={containerRef} className="absolute inset-0" />

      {built.nodeCount === 0 && (
        <p className="absolute inset-0 flex items-center justify-center text-xs italic text-muted-foreground">
          Nothing to graph yet.
        </p>
      )}

      <div className="absolute bottom-3 right-3 flex flex-col gap-1">
        <CanvasButton
          label="Zoom in"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedZoom({ duration: 200 })
          }
        >
          <Plus size={13} />
        </CanvasButton>
        <CanvasButton
          label="Zoom out"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedUnzoom({ duration: 200 })
          }
        >
          <Minus size={13} />
        </CanvasButton>
        <CanvasButton
          label="Fit"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedReset({ duration: 300 })
          }
        >
          <Maximize2 size={12} />
        </CanvasButton>
      </div>

      <p className="pointer-events-none absolute bottom-3 left-3 text-[10px] text-muted-foreground/70">
        Drag to reposition · click to inspect · double-click to expand ·
        right-click for actions
      </p>
    </div>
  );
}

function CanvasButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card/80 text-muted-foreground backdrop-blur-sm transition-colors hover:text-foreground"
    >
      {children}
    </button>
  );
}
