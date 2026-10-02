"use client";

import { GRAPH_NODE_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { GRAPH_NODE_TYPES, type GraphNodeType } from "@/features/entities/types";
import type { ColorMode } from "@/features/graph/hooks/use-graph-explore";
import { cn } from "@/lib/utils";
import type Graph from "graphology";

const MAX_COMMUNITIES = 8;

interface GraphLegendProps {
  graph: Graph;
  /** nodes hidden manually or by the time window; left out of the counts */
  hiddenIds: ReadonlySet<string>;
  timeHiddenIds: ReadonlySet<string>;
  colorMode: ColorMode;
  /** empty = all types visible */
  visibleTypes: GraphNodeType[];
  onToggleType: (type: GraphNodeType) => void;
}

/** Colour key for the canvas. In type mode each row also toggles that node type's filter. */
export function GraphLegend({
  graph,
  hiddenIds,
  timeHiddenIds,
  colorMode,
  visibleTypes,
  onToggleType,
}: GraphLegendProps) {
  const hidden = (node: string) => hiddenIds.has(node) || timeHiddenIds.has(node);

  if (colorMode === "type") {
    const counts = new Map<GraphNodeType, number>();
    graph.forEachNode((node, attrs) => {
      if (hidden(node)) return;
      const type = attrs.entityType as GraphNodeType;
      counts.set(type, (counts.get(type) ?? 0) + 1);
    });
    return (
      <LegendShell>
        {GRAPH_NODE_TYPES.filter((t) => counts.has(t)).map((type) => {
          const meta = GRAPH_NODE_TYPE_META[type];
          const active = !visibleTypes.length || visibleTypes.includes(type);
          return (
            <button
              key={type}
              type="button"
              onClick={() => onToggleType(type)}
              aria-pressed={visibleTypes.includes(type)}
              title={`Show only ${meta.label.toLowerCase()} nodes (click again to clear)`}
              className={cn(
                "flex w-full items-center gap-2 rounded px-1 py-0.5 text-left transition-opacity hover:bg-muted",
                !active && "opacity-40"
              )}
            >
              <Dot color={meta.color} />
              <span className="flex-1">{meta.label}</span>
              <span className="font-mono text-muted-foreground">{counts.get(type)}</span>
            </button>
          );
        })}
      </LegendShell>
    );
  }

  // Community mode: name each cluster after its best-connected member.
  const communities = new Map<
    number,
    { color: string; count: number; lead: string; leadDegree: number }
  >();
  graph.forEachNode((node, attrs) => {
    if (
      hidden(node) ||
      (visibleTypes.length &&
        !visibleTypes.includes(attrs.entityType as GraphNodeType))
    )
      return;
    const id = (attrs.community as number) ?? 0;
    const degree = graph.degree(node);
    const entry = communities.get(id) ?? {
      color: attrs.communityColor as string,
      count: 0,
      lead: "",
      leadDegree: -1,
    };
    entry.count += 1;
    if (degree > entry.leadDegree) {
      entry.lead = String(attrs.label ?? node);
      entry.leadDegree = degree;
    }
    communities.set(id, entry);
  });
  const ranked = [...communities.values()].toSorted((a, b) => b.count - a.count);

  return (
    <LegendShell>
      {ranked.slice(0, MAX_COMMUNITIES).map((c) => (
        <div key={c.lead} className="flex items-center gap-2 px-1 py-0.5">
          <Dot color={c.color} />
          <span className="flex-1 truncate">{c.lead}</span>
          <span className="font-mono text-muted-foreground">{c.count}</span>
        </div>
      ))}
      {ranked.length > MAX_COMMUNITIES && (
        <p className="px-1 text-muted-foreground">
          +{ranked.length - MAX_COMMUNITIES} smaller
        </p>
      )}
    </LegendShell>
  );
}

function LegendShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="absolute bottom-9 left-3 z-10 w-44 rounded-lg border border-border bg-card/90 p-1.5 text-[11px] text-foreground shadow-lg backdrop-blur-sm">
      {children}
    </div>
  );
}

function Dot({ color }: { color: string }) {
  return (
    <span
      className="h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ backgroundColor: color }}
    />
  );
}
