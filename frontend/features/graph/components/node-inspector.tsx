"use client";

import { EntityTypeBadge } from "@/features/entities/components/entity-type-badge";
import { GRAPH_NODE_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntity, useEntityProfile } from "@/features/entities/hooks/use-entities";
import type {
  GraphNodeType,
  RelationshipType,
  SelectorType,
} from "@/features/entities/types";
import { HOP_LIMIT } from "@/features/graph/hooks/use-graph-explore";
import type { EdgeRelationship } from "@/features/graph/lib/build-network";
import { Button } from "@/components/ui/button";
import type Graph from "graphology";
import {
  BadgeCheck,
  EyeOff,
  ExternalLink,
  FileSearch,
  Focus,
  Loader2,
  Maximize2,
  Minimize2,
  PinOff,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

/** Shared shell: the inspectors float over the canvas' right edge so opening one never resizes the graph. */
export const INSPECTOR_SHELL =
  "absolute bottom-3 right-3 top-3 z-10 flex w-72 flex-col rounded-xl border border-border bg-card/95 shadow-xl backdrop-blur-sm";

const CONNECTIONS_PREVIEW = 6;

interface NodeInspectorProps {
  entityId: string;
  datasetId: string | undefined;
  graph: Graph | undefined;
  isSeed: boolean;
  isExpanded: boolean;
  /** this node's fetch hit the per-node edge limit */
  isTruncated: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
  onAddSeed: (id: string) => void;
  onRemoveSeed: (id: string) => void;
  onExpand: (id: string) => void;
  onCollapse: (id: string) => void;
  onHide: (id: string) => void;
  onIsolate: (id: string) => void;
}

export function NodeInspector({
  entityId,
  datasetId,
  graph,
  isSeed,
  isExpanded,
  isTruncated,
  onClose,
  onSelect,
  onAddSeed,
  onRemoveSeed,
  onExpand,
  onCollapse,
  onHide,
  onIsolate,
}: NodeInspectorProps) {
  const { data: entity, isPending } = useEntity(entityId);
  const { data: profile } = useEntityProfile(entityId);

  const selectorType =
    (profile?.detail?.selectorType as SelectorType | undefined) ?? null;

  // A selector is found by its value, not by entity mentions, so "files" and
  // "selectors" mean nothing for it -- show how often the value appears instead.
  const stats = (
    entity?.entityType === "selector"
      ? [
          {
            label: "Mentions",
            value:
              profile &&
              Object.values(profile.mentionCounts).reduce((a, b) => a + (b ?? 0), 0),
          },
          { label: "Related", value: profile?.relatedTotal },
        ]
      : [
          { label: "Files", value: profile?.fileCount },
          { label: "Related", value: profile?.relatedTotal },
          { label: "Selectors", value: profile?.selectorTotal },
        ]
  ).filter((s) => s.value != null);

  const href =
    entity?.personId != null ? `/persons/${entity.personId}` : `/entities/${entityId}`;

  return (
    <aside className={INSPECTOR_SHELL}>
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Node
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-muted-foreground hover:text-foreground"
        >
          <X size={13} />
        </button>
      </div>

      {isPending || !entity ? (
        <div className="flex flex-1 items-center justify-center py-10 text-muted-foreground">
          <Loader2 size={16} className="animate-spin" />
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-3">
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <h2 className="flex-1 text-sm font-bold leading-snug text-foreground">
                {entity.displayName}
              </h2>
              {entity.isVerified && (
                <BadgeCheck size={14} className="mt-0.5 shrink-0 text-primary" />
              )}
            </div>
            <EntityTypeBadge type={entity.entityType} detail={selectorType} />
            {isSeed && (
              <span className="ml-1.5 inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-primary">
                <Sparkles size={10} /> Seed
              </span>
            )}
          </div>

          {stats.length > 0 && (
            <div className="flex gap-px overflow-hidden rounded-lg border border-border bg-border">
              {stats.map((s) => (
                <div key={s.label} className="flex-1 bg-card px-2 py-2 text-center">
                  <div className="text-sm font-semibold text-foreground">
                    {s.value?.toLocaleString()}
                  </div>
                  <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                    {s.label}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            {isExpanded ? (
              <InspectorAction icon={Minimize2} onClick={() => onCollapse(entityId)}>
                Collapse neighbours
              </InspectorAction>
            ) : (
              <InspectorAction icon={Maximize2} onClick={() => onExpand(entityId)}>
                Expand neighbours
              </InspectorAction>
            )}
            {isSeed ? (
              <InspectorAction icon={PinOff} onClick={() => onRemoveSeed(entityId)}>
                Remove seed
              </InspectorAction>
            ) : (
              <InspectorAction icon={Sparkles} onClick={() => onAddSeed(entityId)}>
                Pin as seed
              </InspectorAction>
            )}
            <InspectorAction icon={Focus} onClick={() => onIsolate(entityId)}>
              Isolate
            </InspectorAction>
            <InspectorAction icon={EyeOff} onClick={() => onHide(entityId)}>
              Hide from view
            </InspectorAction>
          </div>

          {isTruncated && (
            <p className="rounded-md border border-border bg-muted/40 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
              Showing the {HOP_LIMIT} strongest of{" "}
              {profile?.relatedTotal?.toLocaleString() ?? "many"} connections. Narrow
              with relationship types or min edge weight in Filters.
            </p>
          )}

          {graph?.hasNode(entityId) && (
            <Connections graph={graph} entityId={entityId} onSelect={onSelect} />
          )}

          <div className="mt-auto flex flex-col gap-1.5">
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 border-border bg-muted/40 text-xs"
            >
              <Link
                href={`/search?entityId=${entityId}${datasetId ? `&datasetId=${datasetId}` : ""}`}
                target="_blank"
              >
                Search text
                <FileSearch size={12} />
              </Link>
            </Button>
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 border-border bg-muted/40 text-xs"
            >
              <Link href={href} target="_blank">
                Open {entity.personId != null ? "person" : "entity"}
                <ExternalLink size={12} />
              </Link>
            </Button>
          </div>
        </div>
      )}
    </aside>
  );
}

interface Connection {
  id: string;
  label: string;
  entityType: GraphNodeType;
  weight: number;
  outgoing: boolean;
}

/** The node's on-canvas neighbours grouped by relationship type, heaviest first; click one to jump to it. */
function Connections({
  graph,
  entityId,
  onSelect,
}: {
  graph: Graph;
  entityId: string;
  onSelect: (id: string) => void;
}) {
  const [openGroup, setOpenGroup] = useState<RelationshipType | null>(null);

  const groups = new Map<RelationshipType, Connection[]>();
  graph.forEachEdge(entityId, (_edge, attrs, src, dst) => {
    const other = src === entityId ? dst : src;
    for (const rel of attrs.relationships as EdgeRelationship[]) {
      groups.set(rel.relationshipType, [
        ...(groups.get(rel.relationshipType) ?? []),
        {
          id: other,
          label: String(graph.getNodeAttribute(other, "label") ?? other),
          entityType: graph.getNodeAttribute(other, "entityType") as GraphNodeType,
          weight: rel.weight,
          outgoing: src === entityId,
        },
      ]);
    }
  });
  if (groups.size === 0) return null;

  return (
    <div className="space-y-3">
      {[...groups.entries()].map(([type, all]) => {
        const sorted = all.toSorted((a, b) => b.weight - a.weight);
        const open = openGroup === type;
        const shown = open ? sorted : sorted.slice(0, CONNECTIONS_PREVIEW);
        return (
          <div key={type} className="space-y-1">
            <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              <span>{type.replace(/_/g, " ")}</span>
              <span className="font-mono font-normal">{all.length}</span>
            </div>
            {shown.map((c) => (
              <button
                key={`${c.id}-${c.outgoing}`}
                type="button"
                onClick={() => onSelect(c.id)}
                className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs text-foreground transition-colors hover:bg-muted"
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: GRAPH_NODE_TYPE_META[c.entityType].color }}
                />
                <span className="flex-1 truncate">{c.label}</span>
                {c.weight > 1 && (
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {c.outgoing ? "→" : "←"} {c.weight.toLocaleString()}
                  </span>
                )}
              </button>
            ))}
            {sorted.length > CONNECTIONS_PREVIEW && (
              <button
                type="button"
                onClick={() => setOpenGroup(open ? null : type)}
                className="px-1.5 text-[11px] text-primary hover:underline"
              >
                {open ? "Show fewer" : `Show all ${sorted.length}`}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function InspectorAction({
  icon: Icon,
  onClick,
  children,
}: {
  icon: typeof Focus;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 rounded-md border border-border/60 bg-background/40 px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
    >
      <Icon size={13} className="shrink-0" />
      {children}
    </button>
  );
}
