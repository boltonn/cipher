"use client";

import { useEntityGraph } from "@/features/entities/hooks/use-entities";
import { buildGraph } from "@/features/entities/lib/build-graph";
import type {
  RelationshipType,
  TraversalDirection,
} from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo } from "react";

// `sigma@3` reads `WebGL2RenderingContext` at module scope, so the canvas
// (and its `import "sigma"`) must never be evaluated on the server. Everything
// above the fold here -- the data fetch, pending/error/empty states -- is
// SSR-safe; only this chunk is browser-only.
const EntityGraphCanvas = dynamic(
  () => import("./entity-graph-canvas").then((m) => m.EntityGraphCanvas),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center py-16 text-xs text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Building graph…
      </div>
    ),
  }
);

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

export function EntityGraph({
  focusEntityId,
  depth = 2,
  direction,
  types,
  minWeight,
  compact,
  className,
}: EntityGraphProps) {
  const { data, isPending, isError } = useEntityGraph(focusEntityId, {
    depth,
    direction,
    types,
    minWeight,
  });

  const built = useMemo(
    () => (data ? buildGraph(data, focusEntityId) : null),
    [data, focusEntityId]
  );

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

  if (!built || built.nodeCount === 0) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-lg border border-border bg-background text-xs italic text-muted-foreground",
          compact ? "h-72" : "h-[70vh]",
          className
        )}
      >
        No connections to graph.
      </div>
    );
  }

  return <EntityGraphCanvas built={built} compact={compact} className={className} />;
}
