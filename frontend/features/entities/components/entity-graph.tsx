"use client";

import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntityGraph } from "@/features/entities/hooks/use-entities";
import { buildGraph } from "@/features/entities/lib/build-graph";
import {
  ENTITY_TYPES,
  type RelationshipType,
  type TraversalDirection,
} from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { Loader2, Maximize2, Minus, Plus, TriangleAlert } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import Sigma from "sigma";
import type { NodeHoverDrawingFunction } from "sigma/rendering";

/** Above this the graph still renders, but a hint nudges the user to filter. */
const SOFT_WARN_NODES = 400;
const LABEL_FONT = "Inter, ui-sans-serif, system-ui, sans-serif";

interface EntityGraphProps {
  focusEntityId: string;
  depth?: number;
  direction?: TraversalDirection;
  /** restrict traversal to these relationship types */
  types?: RelationshipType[];
  /** drop weighted edges below this (keeps unweighted typed edges) */
  minWeight?: number;
  /** compact mode for the identity-page sidebar */
  compact?: boolean;
  className?: string;
}

/** Resolve a CSS custom property to a concrete rgb() string the canvas can use. */
function resolveColor(varName: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const probe = document.createElement("span");
  probe.style.cssText = `color:var(${varName});position:absolute;visibility:hidden`;
  document.body.appendChild(probe);
  const value = getComputedStyle(probe).color;
  probe.remove();
  return value || fallback;
}

/**
 * Themed replacement for sigma's built-in node hover (which paints a hard-coded
 * white chip — unreadable in dark mode). Draws a ring on the node plus a popover-
 * coloured label chip.
 */
function makeHoverRenderer(colors: {
  text: string;
  chip: string;
  border: string;
}): NodeHoverDrawingFunction {
  return (context, data, settings) => {
    const label = typeof data.label === "string" ? data.label : "";
    context.beginPath();
    context.arc(data.x, data.y, data.size + 2, 0, Math.PI * 2);
    context.strokeStyle = data.color;
    context.lineWidth = 2;
    context.stroke();

    if (!label) return;
    context.font = `${settings.labelWeight} ${settings.labelSize}px ${settings.labelFont}`;
    const padX = 6;
    const padY = 4;
    const textWidth = context.measureText(label).width;
    const boxH = settings.labelSize + padY * 2;
    const boxX = data.x + data.size + 4;
    const boxY = data.y - boxH / 2;
    const boxW = textWidth + padX * 2;

    context.beginPath();
    context.fillStyle = colors.chip;
    context.strokeStyle = colors.border;
    context.lineWidth = 1;
    if (context.roundRect) context.roundRect(boxX, boxY, boxW, boxH, 5);
    else context.rect(boxX, boxY, boxW, boxH);
    context.fill();
    context.stroke();

    context.fillStyle = colors.text;
    context.textBaseline = "middle";
    context.fillText(label, boxX + padX, data.y + 1);
  };
}

export function EntityGraph({
  focusEntityId,
  depth = 2,
  direction,
  types,
  minWeight,
  compact,
  className,
}: EntityGraphProps) {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const { data, isPending, isError } = useEntityGraph(focusEntityId, {
    depth,
    direction,
    types,
    minWeight,
  });

  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const hoveredRef = useRef<string | null>(null);

  const built = useMemo(
    () => (data ? buildGraph(data, focusEntityId) : null),
    [data, focusEntityId]
  );

  useEffect(() => {
    if (!containerRef.current || !built || built.nodeCount === 0) return;

    const graph = built.graph;
    const labelColor = resolveColor("--foreground", "#f5f5f7");
    const mutedColor = resolveColor("--muted-foreground", "#8a8a94");
    const edgeColor = resolveColor("--border", "#2c2c31");
    const chipColor = resolveColor("--popover", "#222226");
    // Solid (non-translucent) grey for de-emphasised nodes on hover -- --border is
    // an rgba() whose alpha sigma's node shader ignores, rendering it near-white.
    const dimColor = resolveColor("--secondary", "#303036");

    const renderer = new Sigma(graph, containerRef.current, {
      renderLabels: true,
      renderEdgeLabels: !compact,
      labelFont: LABEL_FONT,
      labelSize: 12,
      labelWeight: "500",
      labelColor: { color: labelColor },
      labelDensity: 0.5,
      labelGridCellSize: 72,
      labelRenderedSizeThreshold: compact ? 0 : 9,
      edgeLabelFont: LABEL_FONT,
      edgeLabelSize: 9,
      edgeLabelColor: { color: mutedColor },
      defaultEdgeColor: edgeColor,
      defaultEdgeType: "arrow",
      defaultDrawNodeHover: makeHoverRenderer({
        text: labelColor,
        chip: chipColor,
        border: edgeColor,
      }),
      enableEdgeEvents: true,
      zIndex: true,
      minCameraRatio: 0.08,
      maxCameraRatio: 10,
      nodeReducer: (node, attrs) => {
        const hovered = hoveredRef.current;
        if (!hovered) return attrs;
        if (node === hovered || graph.areNeighbors(hovered, node)) {
          return { ...attrs, forceLabel: true, zIndex: 1 };
        }
        return { ...attrs, color: dimColor, label: "", zIndex: 0 };
      },
      edgeReducer: (edge, attrs) => {
        const hovered = hoveredRef.current;
        if (!hovered) return { ...attrs, label: "" };
        if (graph.hasExtremity(edge, hovered)) return { ...attrs, forceLabel: true };
        return { ...attrs, hidden: true };
      },
    });

    const rerender = () => renderer.refresh({ skipIndexation: true });
    renderer.on("enterNode", ({ node }) => {
      hoveredRef.current = node;
      rerender();
    });
    renderer.on("leaveNode", () => {
      hoveredRef.current = null;
      rerender();
    });
    renderer.on("clickNode", ({ node }) => router.push(`/entities/${node}`));

    sigmaRef.current = renderer;
    return () => {
      renderer.kill();
      sigmaRef.current = null;
      hoveredRef.current = null;
    };
  }, [built, compact, resolvedTheme, router]);

  if (isPending) {
    return (
      <div className={cn("flex items-center justify-center py-16 text-xs text-muted-foreground", className)}>
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Building graph…
      </div>
    );
  }
  if (isError) {
    return (
      <p className={cn("py-16 text-center text-xs italic text-muted-foreground", className)}>
        Graph unavailable.
      </p>
    );
  }

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border border-border bg-background",
        compact ? "h-72" : "h-[70vh]",
        className
      )}
    >
      <div ref={containerRef} className="absolute inset-0" />

      {built?.nodeCount === 0 && (
        <p className="absolute inset-0 flex items-center justify-center text-xs italic text-muted-foreground">
          No connections to graph.
        </p>
      )}

      {!compact && built && built.nodeCount > 0 && (
        <>
          <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-1.5">
            {ENTITY_TYPES.map((type) => {
              const meta = ENTITY_TYPE_META[type];
              return (
                <span
                  key={type}
                  className="flex items-center gap-1 rounded-md border border-border bg-card/80 px-1.5 py-0.5 text-[10px] text-muted-foreground backdrop-blur-sm"
                >
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: meta.color }} />
                  {meta.label}
                </span>
              );
            })}
          </div>

          <div className="absolute bottom-3 right-3 flex flex-col gap-1">
            <GraphButton label="Zoom in" onClick={() => sigmaRef.current?.getCamera().animatedZoom({ duration: 200 })}>
              <Plus size={13} />
            </GraphButton>
            <GraphButton label="Zoom out" onClick={() => sigmaRef.current?.getCamera().animatedUnzoom({ duration: 200 })}>
              <Minus size={13} />
            </GraphButton>
            <GraphButton label="Fit" onClick={() => sigmaRef.current?.getCamera().animatedReset({ duration: 300 })}>
              <Maximize2 size={12} />
            </GraphButton>
          </div>

          {built.nodeCount >= SOFT_WARN_NODES && (
            <div className="absolute bottom-3 left-3 flex items-center gap-1.5 rounded-md border border-annotation/30 bg-annotation/5 px-2 py-1 text-[10px] text-muted-foreground">
              <TriangleAlert className="h-3 w-3 text-annotation" />
              {built.nodeCount} nodes — narrow the entity type or depth to reduce clutter
            </div>
          )}
        </>
      )}
    </div>
  );
}

function GraphButton({
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
