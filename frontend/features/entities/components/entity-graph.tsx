"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntityGraph } from "@/features/entities/hooks/use-entities";
import { LOW_SIGNAL_RELATIONSHIPS, type EntityType, type RelationshipType } from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { Loader2, TriangleAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

const MAX_GRAPH_NODES = 120;

interface EntityGraphProps {
  focusEntityId: string;
  depth?: number;
  /** compact mode for the identity page sidebar */
  compact?: boolean;
  className?: string;
}

type EntityNodeData = {
  label: string;
  entityType: EntityType;
  isFocus: boolean;
};

function EntityNode({ data }: NodeProps<Node<EntityNodeData>>) {
  const meta = ENTITY_TYPE_META[data.entityType];
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs shadow-sm backdrop-blur-sm",
        meta.bgClass,
        meta.borderClass,
        meta.textClass,
        data.isFocus && "ring-2 ring-primary ring-offset-2 ring-offset-background"
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0" />
      <meta.Icon size={12} className="shrink-0" />
      <span className="max-w-40 truncate font-medium">{data.label}</span>
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0" />
    </div>
  );
}

const nodeTypes = { entity: EntityNode };

type SimNode = SimulationNodeDatum & { id: string };

function layout(
  rawNodes: { id: string; data: EntityNodeData }[],
  rawEdges: { source: string; target: string }[]
): Record<string, { x: number; y: number }> {
  const simNodes: SimNode[] = rawNodes.map((n) => ({ id: n.id }));
  const simLinks: SimulationLinkDatum<SimNode>[] = rawEdges.map((e) => ({
    source: e.source,
    target: e.target,
  }));
  forceSimulation<SimNode>(simNodes)
    .force(
      "link",
      forceLink<SimNode, SimulationLinkDatum<SimNode>>(simLinks)
        .id((d) => d.id)
        .distance(110)
        .strength(0.6)
    )
    .force("charge", forceManyBody().strength(-320))
    .force("collide", forceCollide(52))
    .force("center", forceCenter(0, 0))
    .stop()
    .tick(320);

  const pos: Record<string, { x: number; y: number }> = {};
  for (const n of simNodes) {
    pos[n.id] = { x: n.x ?? 0, y: n.y ?? 0 };
  }
  return pos;
}

export function EntityGraph({ focusEntityId, depth = 2, compact, className }: EntityGraphProps) {
  const router = useRouter();
  const { data, isPending, isError } = useEntityGraph(focusEntityId, { depth });

  const { nodes, edges, tooMany } = useMemo(() => {
    if (!data) return { nodes: [] as Node[], edges: [] as Edge[], tooMany: false };
    if (data.nodes.length > MAX_GRAPH_NODES) {
      return { nodes: [], edges: [], tooMany: true };
    }

    const rawNodes = data.nodes.map((n) => ({
      id: n.id,
      data: { label: n.displayName, entityType: n.entityType, isFocus: n.id === focusEntityId },
    }));
    const rawEdges = data.edges
      .filter((e) => !LOW_SIGNAL_RELATIONSHIPS.includes(e.relationshipType))
      .map((e) => ({ source: e.srcEntityId, target: e.dstEntityId, label: e.relationshipType }));

    const pos = layout(rawNodes, rawEdges);

    const flowNodes: Node<EntityNodeData>[] = rawNodes.map((n) => ({
      id: n.id,
      type: "entity",
      position: pos[n.id] ?? { x: 0, y: 0 },
      data: n.data,
    }));
    const flowEdges: Edge[] = rawEdges.map((e, i) => ({
      id: `e${i}`,
      source: e.source,
      target: e.target,
      label: (e.label as RelationshipType).replace(/_/g, " "),
      labelStyle: { fontSize: 9, fill: "var(--muted-foreground)" },
      style: { stroke: "var(--border)", strokeWidth: 1.5 },
    }));
    return { nodes: flowNodes, edges: flowEdges, tooMany: false };
  }, [data, focusEntityId]);

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
  if (tooMany) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border border-annotation/30 bg-annotation/5 py-16 text-center",
          className
        )}
      >
        <TriangleAlert className="h-5 w-5 text-annotation" />
        <p className="text-xs font-medium text-foreground">
          {data?.nodes.length} nodes — too dense to render
        </p>
        <p className="max-w-xs text-[11px] text-muted-foreground">
          Reduce the traversal depth or narrow the entity type, then try again.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-background",
        compact ? "h-72" : "h-[70vh]",
        className
      )}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => router.push(`/entities/${node.id}`)}
        fitView
        minZoom={0.2}
        onlyRenderVisibleElements
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="var(--border)" />
        {!compact && <Controls showInteractive={false} className="!bg-card !border-border" />}
      </ReactFlow>
    </div>
  );
}
