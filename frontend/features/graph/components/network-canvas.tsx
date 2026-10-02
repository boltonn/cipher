"use client";

import type {
  GraphNodeType,
  RelationshipType,
} from "@/features/entities/types";
import type { ColorMode, SizeMode } from "@/features/graph/hooks/use-graph-explore";
import type {
  BuiltNetwork,
  EdgeRelationship,
} from "@/features/graph/lib/build-network";
import {
  blendColor,
  makeHoverRenderer,
  makeLabelRenderer,
  resolveColor,
} from "@/features/graph/lib/canvas-helpers";
import { pathEdgeKeys } from "@/features/graph/lib/graph-analytics";
import { createLiveLayout } from "@/features/graph/lib/graph-layouts";
import { makeGraphPrograms } from "@/features/graph/lib/graph-programs";
import { edgeInWindow, type TimeWindow } from "@/features/graph/lib/time-window";
import { useTheme } from "@/providers/theme-provider";
import { downloadAsPNG } from "@sigma/export-image";
import { Minus, Plus, Scan } from "lucide-react";
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

/** Pointer travel (px) before a held node counts as a drag rather than a click. */
const DRAG_THRESHOLD = 4;
/** A focused hub with more neighbours than this lets label density decide instead of labelling all of them. */
const FORCE_LABEL_NEIGHBOURS = 40;
/** Fit never zooms in past this, so one visible node doesn't fill the canvas. */
const MIN_FIT_RATIO = 0.35;
/** Fit margins (px). Labels sit to the right of their node; the legend and hint sit along the bottom. */
const FIT_PADDING = { left: 70, right: 230, top: 60, bottom: 140 };
/** Width the page's inspector overlays on the right edge of the canvas. */
const INSPECTOR_WIDTH = 300;
/** Sigma's edge picking is exact-pixel on ~1px lines; probe a small ring around the pointer instead. */
const EDGE_PICK_OFFSETS = [0, 2, 4].flatMap((r) =>
  r === 0
    ? [[0, 0]]
    : [-1, 0, 1].flatMap((dx) => [-1, 0, 1].map((dy) => [dx * r, dy * r])).filter(([dx, dy]) => dx || dy)
);

export type LabelsMode = "all" | "hover" | "off";

export interface EdgePick {
  id: string;
  /** every relationship between the two nodes in this direction, heaviest first */
  relationships: EdgeRelationship[];
  srcId: string;
  dstId: string;
  srcName: string;
  dstName: string;
}

export interface NetworkCanvasProps {
  built: BuiltNetwork;
  hiddenIds: ReadonlySet<string>;
  /** nodes left with no in-window edge; hidden without refitting the camera */
  timeHiddenIds: ReadonlySet<string>;
  timeWindow: TimeWindow | null;
  /** ctrl/cmd/shift-click selection for bulk actions */
  multiIds: ReadonlySet<string>;
  /** empty = all types visible */
  visibleTypes: GraphNodeType[];
  /** empty = all relationship types visible */
  visibleRelTypes: RelationshipType[];
  labelsMode: LabelsMode;
  labelDensity: number;
  colorMode: ColorMode;
  sizeMode: SizeMode;
  liveLayout: boolean;
  selectedId: string | null;
  selectedEdgeId: string | null;
  highlightIds: ReadonlySet<string>;
  pathIds: readonly string[];
  pathAnchors: readonly string[];
  /** bump to trigger a PNG download */
  exportNonce: number;
  onSelect: (id: string | null) => void;
  onToggleMulti: (id: string) => void;
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
  timeHiddenIds: ReadonlySet<string>;
  timeWindow: TimeWindow | null;
  multiIds: ReadonlySet<string>;
  visibleTypes: GraphNodeType[];
  visibleRelTypes: RelationshipType[];
  labelsMode: LabelsMode;
  colorMode: ColorMode;
  sizeMode: SizeMode;
  selectedId: string | null;
  selectedEdgeId: string | null;
  highlightIds: ReadonlySet<string>;
  pathIds: readonly string[];
  pathAnchors: readonly string[];
  pathSet: ReadonlySet<string>;
  pathEdges: ReadonlySet<string>;
}

function isNodeVisible(s: CanvasState, node: string, attrs: Record<string, unknown>) {
  if (s.hiddenIds.has(node) || s.timeHiddenIds.has(node)) return false;
  return !s.visibleTypes.length || s.visibleTypes.includes(attrs.entityType as GraphNodeType);
}

/** Frame the visible nodes. Positions come from graph attributes, not sigma's
 * display cache -- that holds raw graph coords between an attribute write and
 * the next render, which sends the camera off-canvas. */
function fitVisible(sigma: Sigma, s: CanvasState, animate = true) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  sigma.getGraph().forEachNode((node, attrs) => {
    if (!isNodeVisible(s, node, attrs)) return;
    const p = sigma.graphToViewport({ x: attrs.x as number, y: attrs.y as number });
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  });
  if (minX === Infinity) return null;
  const { width, height } = sigma.getDimensions();
  const camera = sigma.getCamera();
  const scale = Math.min(
    (width - FIT_PADDING.left - FIT_PADDING.right) / Math.max(maxX - minX, 1),
    (height - FIT_PADDING.top - FIT_PADDING.bottom) / Math.max(maxY - minY, 1),
    camera.ratio / MIN_FIT_RATIO
  );
  // offset the camera so the nodes land up-left of centre, clear of the wider margins
  const target = {
    ...sigma.viewportToFramedGraph({
      x: (minX + maxX) / 2 + (FIT_PADDING.right - FIT_PADDING.left) / 2 / scale,
      y: (minY + maxY) / 2 + (FIT_PADDING.bottom - FIT_PADDING.top) / 2 / scale,
    }),
    ratio: camera.ratio / scale,
  };
  if (animate) camera.animate(target, { duration: 300 });
  else camera.setState(target);
  return target;
}

/** Pan to a node only when it is off-canvas or under the inspector overlay. */
function revealNode(sigma: Sigma, node: string) {
  const graph = sigma.getGraph();
  if (!graph.hasNode(node)) return;
  const { x, y } = graph.getNodeAttributes(node) as { x: number; y: number };
  const p = sigma.graphToViewport({ x, y });
  const { width, height } = sigma.getDimensions();
  const margin = 40;
  if (
    p.x >= margin &&
    p.x <= width - INSPECTOR_WIDTH - margin &&
    p.y >= margin &&
    p.y <= height - margin
  )
    return;
  sigma.getCamera().animate(sigma.viewportToFramedGraph(p), { duration: 300 });
}

export function NetworkCanvas({
  built,
  hiddenIds,
  timeHiddenIds,
  timeWindow,
  multiIds,
  visibleTypes,
  visibleRelTypes,
  labelsMode,
  labelDensity,
  colorMode,
  sizeMode,
  liveLayout,
  selectedId,
  selectedEdgeId,
  highlightIds,
  pathIds,
  pathAnchors,
  exportNonce,
  onSelect,
  onToggleMulti,
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
  const hoveredEdgeRef = useRef<string | null>(null);
  const dragRef = useRef<{ node: string; x: number; y: number; moved: boolean } | null>(null);
  const justDraggedRef = useRef(false);
  const clickedOnCanvasRef = useRef(false);
  // Where the last fit left the camera: if it is still there on a resize, the
  // user hasn't panned or zoomed, so the view is refitted to the new size.
  const lastFitRef = useRef<{ x: number; y: number; ratio: number } | null>(null);
  const fit = (sigma: Sigma, animate = true) => {
    lastFitRef.current = fitVisible(sigma, stateRef.current, animate) ?? lastFitRef.current;
  };

  const stateRef = useRef<CanvasState>({
    hiddenIds,
    timeHiddenIds,
    timeWindow,
    multiIds,
    visibleTypes,
    visibleRelTypes,
    labelsMode,
    colorMode,
    sizeMode,
    selectedId,
    selectedEdgeId,
    highlightIds,
    pathIds,
    pathAnchors,
    pathSet: new Set(),
    pathEdges: new Set(),
  });
  useEffect(() => {
    const prev = stateRef.current;
    stateRef.current = {
      hiddenIds,
      timeHiddenIds,
      timeWindow,
      multiIds,
      visibleTypes,
      visibleRelTypes,
      labelsMode,
      colorMode,
      sizeMode,
      selectedId,
      selectedEdgeId,
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

    sigma.refresh({ skipIndexation: true });

    if (prev.hiddenIds !== hiddenIds || prev.visibleTypes !== visibleTypes) {
      fit(sigma);
    } else if (selectedId && selectedId !== prev.selectedId) {
      // A canvas click may be the first half of a double-click (expand): hold the
      // pan until that window has passed so the node stays under the pointer.
      const delay = clickedOnCanvasRef.current ? 350 : 0;
      clickedOnCanvasRef.current = false;
      window.setTimeout(() => {
        if (sigmaRef.current === sigma) revealNode(sigma, selectedId);
      }, delay);
    }
  }, [
    hiddenIds,
    timeHiddenIds,
    timeWindow,
    multiIds,
    visibleTypes,
    visibleRelTypes,
    labelsMode,
    labelDensity,
    colorMode,
    sizeMode,
    selectedId,
    selectedEdgeId,
    highlightIds,
    pathIds,
    pathAnchors,
  ]);

  const cbRef = useRef({
    onSelect,
    onToggleMulti,
    onSelectEdge,
    onNodeContextMenu,
    onDragEnd,
    onExpand,
  });
  useEffect(() => {
    cbRef.current = {
      onSelect,
      onToggleMulti,
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
    const background = resolveColor("--background", "#0b0b0c");
    const edgeColor = blendColor(mutedColor, background, 0.65);
    const dimColor = blendColor(mutedColor, background, 0.22);
    // flattened to rgb(): sigma can't parse the oklch() the token resolves to and paints black
    const pathColor = blendColor(resolveColor("--primary", "#7c9cff"), background, 1);
    const { nodeProgramClasses, edgeProgramClasses } = makeGraphPrograms();

    const nodeVisible = (node: string, attrs: Record<string, unknown>) =>
      isNodeVisible(stateRef.current, node, attrs);

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
      labelGridCellSize: 130,
      labelRenderedSizeThreshold: 4,
      stagePadding: 70,
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
        if (s.pathAnchors.includes(node) || s.multiIds.has(node)) {
          return {
            ...attrs,
            forceLabel: true,
            zIndex: 3,
            highlighted: true,
            ringColor: pathColor,
          };
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

        if (focus && graph.hasNode(focus)) {
          if (node === focus) return { ...attrs, forceLabel: true, zIndex: 2 };
          if (graph.areNeighbors(focus, node)) {
            const crowded = graph.degree(focus) > FORCE_LABEL_NEIGHBOURS;
            return {
              ...attrs,
              forceLabel: !crowded || Boolean(data.isSeed),
              zIndex: 1,
              highlighted: Boolean(data.isSeed),
            };
          }
          return dim(attrs);
        }
        if (s.labelsMode === "hover" && !data.isSeed) {
          return { ...attrs, label: "" };
        }
        // `highlighted` paints the seed on sigma's hover layer, above every label
        // chip, so a hub's neighbours can't bury it
        if (data.isSeed) {
          return { ...attrs, forceLabel: true, zIndex: 1, highlighted: true };
        }
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
          !(data.relationships as EdgeRelationship[]).some((r) =>
            s.visibleRelTypes.includes(r.relationshipType)
          )
        )
          return { ...data, hidden: true };
        if (s.timeWindow && !edgeInWindow(data, s.timeWindow))
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

        if (edge === s.selectedEdgeId || edge === hoveredEdgeRef.current) {
          return {
            ...data,
            forceLabel: true,
            color: pathColor,
            size: Math.max((data.size as number) ?? 2, 3),
            zIndex: 2,
          };
        }

        const focus = hoveredRef.current ?? s.selectedId;
        if (!focus || !graph.hasNode(focus)) return { ...data, label: "" };
        if (graph.hasExtremity(edge, focus)) {
          const crowded = graph.degree(focus) > FORCE_LABEL_NEIGHBOURS;
          return { ...data, forceLabel: !crowded, label: crowded ? "" : data.label };
        }
        // dimmed, not hidden: the rest of the graph stays visible and clickable
        return { ...data, color: dimColor, label: "", zIndex: 0 };
      },
    });
    fit(renderer, false);
    // after the fitted camera has rendered, so the reveal measures real positions
    const revealTimer = window.setTimeout(() => {
      const { selectedId } = stateRef.current;
      if (selectedId) revealNode(renderer, selectedId);
    }, 60);

    const container = containerRef.current;
    const rerender = () => renderer.refresh({ skipIndexation: true });
    const setCursor = () => {
      container.style.cursor = hoveredRef.current || hoveredEdgeRef.current ? "pointer" : "";
    };
    const pick = renderer as unknown as {
      getEdgeAtPoint: (x: number, y: number) => string | null;
    };
    const edgeNear = (x: number, y: number) => {
      for (const [dx, dy] of EDGE_PICK_OFFSETS) {
        const edge = pick.getEdgeAtPoint(x + dx, y + dy);
        if (edge) return edge;
      }
      return null;
    };
    const selectEdge = (edge: string) => {
      const a = graph.getEdgeAttributes(edge);
      const [s, d] = graph.extremities(edge);
      cbRef.current.onSelectEdge({
        id: edge,
        relationships: a.relationships as EdgeRelationship[],
        srcId: s,
        dstId: d,
        srcName: (a.srcName as string) ?? s,
        dstName: (a.dstName as string) ?? d,
      });
    };

    renderer.on("enterNode", ({ node }) => {
      if (dragRef.current) return;
      hoveredRef.current = node;
      hoveredEdgeRef.current = null;
      setCursor();
      rerender();
    });
    renderer.on("leaveNode", () => {
      if (dragRef.current) return;
      hoveredRef.current = null;
      setCursor();
      rerender();
    });
    renderer.on("clickNode", ({ node, event }) => {
      if (justDraggedRef.current) {
        justDraggedRef.current = false;
        return;
      }
      const orig = event.original;
      if ("ctrlKey" in orig && (orig.ctrlKey || orig.metaKey || orig.shiftKey)) {
        cbRef.current.onToggleMulti(node);
        return;
      }
      clickedOnCanvasRef.current = true;
      cbRef.current.onSelect(node);
    });
    renderer.on("doubleClickNode", (e) => {
      e.preventSigmaDefault();
      cbRef.current.onExpand(e.node);
    });
    renderer.on("clickEdge", ({ edge }) => selectEdge(edge));
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
    renderer.on("clickStage", ({ event }) => {
      cbRef.current.onNodeContextMenu(null);
      const edge = edgeNear(event.x, event.y);
      if (edge) {
        selectEdge(edge);
        return;
      }
      cbRef.current.onSelect(null);
      cbRef.current.onSelectEdge(null);
    });

    // Node dragging (the canonical sigma@3 recipe: freeze the camera bbox and
    // swallow the stage-pan via preventSigmaDefault while a node is held). A
    // press only becomes a drag past DRAG_THRESHOLD, so a plain click neither
    // pins the node nor gets a selection after a real drag.
    renderer.on("downNode", ({ node, event }) => {
      justDraggedRef.current = false;
      const orig = event.original;
      if ("button" in orig && orig.button !== 0) return;
      dragRef.current = { node, x: event.x, y: event.y, moved: false };
    });
    // Edge hover: throttled, and always resolved against the latest pointer
    // position so a fast move can't leave a stale edge lit.
    let hoverTimer = 0;
    let pointer = { x: 0, y: 0 };
    renderer.on("moveBody", ({ event }) => {
      const drag = dragRef.current;
      if (!drag) {
        pointer = { x: event.x, y: event.y };
        if (hoverTimer) return;
        hoverTimer = window.setTimeout(() => {
          hoverTimer = 0;
          const edge = hoveredRef.current ? null : edgeNear(pointer.x, pointer.y);
          if (edge === hoveredEdgeRef.current) return;
          hoveredEdgeRef.current = edge;
          setCursor();
          rerender();
        }, 30);
        return;
      }
      // A move with no button held means the release was missed -- end the drag
      // instead of leaving the node glued to the pointer.
      if ("buttons" in event.original && event.original.buttons === 0) {
        drop();
        return;
      }
      event.preventSigmaDefault();
      event.original.preventDefault();
      event.original.stopPropagation();
      if (!drag.moved) {
        if (Math.hypot(event.x - drag.x, event.y - drag.y) < DRAG_THRESHOLD) return;
        drag.moved = true;
        graph.setNodeAttribute(drag.node, "highlighted", true);
        graph.setNodeAttribute(drag.node, "fixed", true);
        if (!renderer.getCustomBBox()) renderer.setCustomBBox(renderer.getBBox());
      }
      const pos = renderer.viewportToGraph(event);
      graph.setNodeAttribute(drag.node, "x", pos.x);
      graph.setNodeAttribute(drag.node, "y", pos.y);
    });
    const drop = () => {
      const drag = dragRef.current;
      dragRef.current = null;
      if (!drag?.moved || !graph.hasNode(drag.node)) return;
      justDraggedRef.current = true;
      graph.removeNodeAttribute(drag.node, "highlighted");
      cbRef.current.onDragEnd(drag.node, {
        x: graph.getNodeAttribute(drag.node, "x") as number,
        y: graph.getNodeAttribute(drag.node, "y") as number,
      });
    };
    renderer.on("upNode", drop);
    renderer.on("upStage", drop);
    // A release outside the canvas (or one a popup swallowed) must still end the drag.
    window.addEventListener("mouseup", drop);
    const clearHover = () => {
      if (dragRef.current || (!hoveredRef.current && !hoveredEdgeRef.current)) return;
      hoveredRef.current = null;
      hoveredEdgeRef.current = null;
      setCursor();
      rerender();
    };
    container.addEventListener("mouseleave", clearHover);
    // Sigma only listens for window resizes; the canvas also resizes when the
    // timeline or a banner appears. Refit unless the user has moved the camera.
    const resizeObserver = new ResizeObserver(() => {
      const camera = renderer.getCamera().getState();
      const last = lastFitRef.current;
      const untouched =
        last != null &&
        Math.abs(camera.x - last.x) < 1e-6 &&
        Math.abs(camera.y - last.y) < 1e-6 &&
        Math.abs(camera.ratio - last.ratio) < 1e-6;
      renderer.refresh();
      if (untouched) fit(renderer, false);
    });
    resizeObserver.observe(container);

    sigmaRef.current = renderer;
    setSigmaInstance(renderer);

    // The node-image texture atlas builds async (debounced, see graph-programs);
    // repaint once it has almost certainly landed so glyphs show without an interaction.
    const atlasPaint = window.setTimeout(() => {
      renderer.refresh({ skipIndexation: true });
    }, 200);

    return () => {
      window.clearTimeout(atlasPaint);
      window.clearTimeout(revealTimer);
      window.clearTimeout(hoverTimer);
      window.removeEventListener("mouseup", drop);
      container.removeEventListener("mouseleave", clearHover);
      resizeObserver.disconnect();
      renderer.kill();
      sigmaRef.current = null;
      setSigmaInstance(null);
      hoveredRef.current = null;
      hoveredEdgeRef.current = null;
      dragRef.current = null;
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

      <div className="absolute left-3 top-3 flex flex-col gap-1">
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
          label="Fit to visible nodes"
          onClick={() => {
            if (sigmaRef.current) fit(sigmaRef.current);
          }}
        >
          <Scan size={13} />
        </CanvasButton>
      </div>

      <p className="pointer-events-none absolute bottom-3 left-3 text-[11px] text-muted-foreground/70">
        Drag to reposition · click to inspect · ctrl-click to multi-select ·
        double-click to expand · right-click for actions
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
      title={label}
      onClick={onClick}
      className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card/80 text-muted-foreground backdrop-blur-sm transition-colors hover:text-foreground"
    >
      {children}
    </button>
  );
}
