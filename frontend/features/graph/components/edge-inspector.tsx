"use client";

import { Button } from "@/components/ui/button";
import type { EdgePick } from "@/features/graph/components/network-canvas";
import { INSPECTOR_SHELL } from "@/features/graph/components/node-inspector";
import type { EdgeRelationship } from "@/features/graph/lib/build-network";
import { format } from "date-fns";
import {
  ArrowLeftRight,
  ArrowRight,
  ExternalLink,
  FileSearch,
  X,
} from "lucide-react";
import Link from "next/link";

interface EdgeInspectorProps {
  edge: EdgePick;
  datasetId: string | undefined;
  onClose: () => void;
}

/** Read-only detail for a clicked edge: every relationship running between its
 * two nodes in that direction. All data comes from the graph edge attributes
 * -- no fetch. */
export function EdgeInspector({ edge, datasetId, onClose }: EdgeInspectorProps) {
  const isEventEdge = edge.relationships.some(
    (r) => r.relationshipType === "participant_in"
  );

  return (
    <aside className={INSPECTOR_SHELL}>
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {edge.relationships.length > 1
            ? `${edge.relationships.length} relationships`
            : "Relationship"}
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

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-3">
        {edge.relationships.map((rel) => (
          <RelationshipBlock
            key={rel.relationshipType}
            rel={rel}
            srcName={edge.srcName}
            dstName={edge.dstName}
          />
        ))}

        <div className="mt-auto flex flex-col gap-1.5">
          {!isEventEdge && (
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 border-border bg-muted/40 text-xs"
            >
              <Link
                href={`/search?entityId=${edge.srcId}&entityId=${edge.dstId}${datasetId ? `&datasetId=${datasetId}` : ""}`}
                target="_blank"
              >
                Search text mentioning both
                <FileSearch size={12} />
              </Link>
            </Button>
          )}
          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 border-border bg-muted/40 text-xs"
          >
            <Link href={`/entities/${edge.srcId}`} target="_blank">
              Open source
              <ExternalLink size={12} />
            </Link>
          </Button>
          {!isEventEdge && (
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 border-border bg-muted/40 text-xs"
            >
              <Link href={`/entities/${edge.dstId}`} target="_blank">
                Open target
                <ExternalLink size={12} />
              </Link>
            </Button>
          )}
        </div>
      </div>
    </aside>
  );
}

function RelationshipBlock({
  rel,
  srcName,
  dstName,
}: {
  rel: EdgeRelationship;
  srcName: string;
  dstName: string;
}) {
  const attrEntries = Object.entries(rel.attributes).filter(
    ([, v]) => v != null && v !== ""
  );
  const fmt = (ms: number) => format(ms, "MMM d, yyyy");
  const active =
    rel.dateStart == null
      ? null
      : rel.dateEnd != null && fmt(rel.dateEnd) !== fmt(rel.dateStart)
        ? `${fmt(rel.dateStart)} – ${fmt(rel.dateEnd)}`
        : fmt(rel.dateStart);

  return (
    <div className="space-y-2">
      <span className="inline-flex rounded-md border border-primary/40 bg-primary/10 px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-primary">
        {rel.relationshipType.replace(/_/g, " ")}
      </span>

      <div className="flex items-center gap-2 text-xs text-foreground">
        <span className="flex-1 truncate font-semibold">{srcName}</span>
        {rel.directed ? (
          <ArrowRight size={13} className="shrink-0 text-muted-foreground" />
        ) : (
          <ArrowLeftRight size={13} className="shrink-0 text-muted-foreground" />
        )}
        <span className="flex-1 truncate text-right font-semibold">{dstName}</span>
      </div>

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
        <Stat label="Weight" value={rel.weight.toLocaleString()} />
        <Stat label="Source" value={rel.source || "—"} />
      </div>

      <dl className="space-y-1.5 text-xs">
        {active && (
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">active</dt>
            <dd className="truncate text-right font-medium text-foreground">{active}</dd>
          </div>
        )}
        {attrEntries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className="text-muted-foreground">{k.replace(/_/g, " ")}</dt>
            <dd className="truncate text-right font-medium text-foreground">
              {String(v)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-2 py-2 text-center">
      <div className="truncate text-sm font-semibold text-foreground">{value}</div>
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
    </div>
  );
}
