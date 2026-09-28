"use client";

import { Button } from "@/components/ui/button";
import type { EdgePick } from "@/features/graph/components/network-canvas";
import { ArrowLeftRight, ArrowRight, ExternalLink, X } from "lucide-react";
import Link from "next/link";

interface EdgeInspectorProps {
  edge: EdgePick;
  onClose: () => void;
}

/** Read-only relationship detail for a clicked edge. All data comes from the
 * graph edge attributes -- no fetch. */
export function EdgeInspector({ edge, onClose }: EdgeInspectorProps) {
  const attrEntries = Object.entries(edge.attributes).filter(
    ([, v]) => v != null && v !== ""
  );

  return (
    <aside className="flex w-72 shrink-0 flex-col rounded-xl border border-border bg-muted/40 shadow-xl">
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-2">
        <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">
          Relationship
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
        <div className="space-y-2">
          <span className="inline-flex rounded-md border border-primary/40 bg-primary/10 px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-primary">
            {edge.relationshipType.replace(/_/g, " ")}
          </span>

          <div className="flex items-center gap-2 text-xs text-foreground">
            <span className="flex-1 truncate font-semibold">{edge.srcName}</span>
            {edge.directed ? (
              <ArrowRight size={13} className="shrink-0 text-muted-foreground" />
            ) : (
              <ArrowLeftRight
                size={13}
                className="shrink-0 text-muted-foreground"
              />
            )}
            <span className="flex-1 truncate text-right font-semibold">
              {edge.dstName}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
          <Stat label="Weight" value={edge.weight.toLocaleString()} />
          <Stat label="Source" value={edge.source || "—"} />
        </div>

        {attrEntries.length > 0 && (
          <dl className="space-y-1.5 text-xs">
            {attrEntries.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{k.replace(/_/g, " ")}</dt>
                <dd className="truncate text-right font-medium text-foreground">
                  {String(v)}
                </dd>
              </div>
            ))}
          </dl>
        )}

        <div className="mt-auto flex flex-col gap-1.5">
          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 border-border bg-muted/40 text-xs"
          >
            <Link href={`/entities/${edge.srcId}`}>
              Open source
              <ExternalLink size={12} />
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 border-border bg-muted/40 text-xs"
          >
            <Link href={`/entities/${edge.dstId}`}>
              Open target
              <ExternalLink size={12} />
            </Link>
          </Button>
        </div>
      </div>
    </aside>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-2 py-2 text-center">
      <div className="truncate text-sm font-semibold text-foreground">{value}</div>
      <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
    </div>
  );
}
