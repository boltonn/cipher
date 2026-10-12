"use client";

import { PageHeader } from "@/components/page-header";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { EntityGraph } from "@/features/entities/components/entity-graph";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntity } from "@/features/entities/hooks/use-entities";
import {
  LOW_SIGNAL_RELATIONSHIPS,
  RELATIONSHIP_TYPES,
  type RelationshipType,
  type TraversalDirection,
} from "@/features/entities/types";
import { cn, humanize } from "@/lib/utils";
import { ArrowLeft, ArrowRight } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";

const SELECTABLE_TYPES = RELATIONSHIP_TYPES.filter(
  (t) => !LOW_SIGNAL_RELATIONSHIPS.includes(t)
);

const DIRECTIONS: { value: TraversalDirection; label: string }[] = [
  { value: "both", label: "Both" },
  { value: "out", label: "Outgoing" },
  { value: "in", label: "Incoming" },
];

export default function EntityGraphPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: entity } = useEntity(id);

  const [depth, setDepth] = useState(2);
  const [direction, setDirection] = useState<TraversalDirection>("both");
  const [types, setTypes] = useState<RelationshipType[]>([]);
  const [minWeight, setMinWeight] = useState(0);

  const toggleType = (t: RelationshipType) =>
    setTypes((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]
    );

  return (
    <div className="mx-auto max-w-400 px-6 pb-10 pt-5">
      <PageHeader>
        <div className="flex min-w-0 items-center gap-1.5 text-xs">
          <Link
            href="/entities"
            className="font-mono text-muted-foreground hover:text-primary"
          >
            Entities
          </Link>
          <span className="text-muted-foreground/50">/</span>
          <Link
            href={`/entities/${id}`}
            className="max-w-48 truncate font-mono text-muted-foreground hover:text-primary"
          >
            {entity ? entity.displayName : "…"}
          </Link>
          <span className="text-muted-foreground/50">/</span>
          <span className="font-mono text-primary/80">Graph</span>
        </div>
      </PageHeader>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          href={`/entities/${id}`}
          className="inline-flex w-fit items-center gap-1.5 text-[11px] font-semibold text-primary hover:underline"
        >
          <ArrowLeft size={12} /> Back to entity
        </Link>
        <Link
          href={`/graph?seed=${id}`}
          className="inline-flex w-fit items-center gap-1.5 text-[11px] font-semibold text-muted-foreground hover:text-primary"
        >
          Open in graph viewer <ArrowRight size={12} />
        </Link>
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-3 rounded-lg border border-border bg-muted/30 p-4">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
            Depth
          </span>
          <Select value={String(depth)} onValueChange={(v) => setDepth(Number(v))}>
            <SelectTrigger className="h-8 w-24 bg-background text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[1, 2, 3].map((d) => (
                <SelectItem key={d} value={String(d)} className="text-xs">
                  {d} hop{d > 1 ? "s" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
            Direction
          </span>
          <div className="flex overflow-hidden rounded-md border border-border">
            {DIRECTIONS.map((d) => (
              <button
                key={d.value}
                type="button"
                onClick={() => setDirection(d.value)}
                className={cn(
                  "px-2.5 py-1.5 text-xs font-medium transition-colors",
                  direction === d.value
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <label className="flex min-w-48 flex-1 flex-col gap-1">
          <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
            Min edge weight: {minWeight === 0 ? "off" : `≥ ${minWeight}`}
          </span>
          <Slider
            value={[minWeight]}
            onValueChange={([v]) => setMinWeight(v)}
            min={0}
            max={100}
            step={1}
            className="mt-2"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {SELECTABLE_TYPES.map((t) => {
          const active = types.includes(t);
          return (
            <button
              key={t}
              type="button"
              onClick={() => toggleType(t)}
              className={cn(
                "rounded-md border px-2 py-1 text-[11px] font-medium transition-colors",
                active
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border bg-muted/30 text-muted-foreground hover:text-foreground"
              )}
            >
              {humanize(t)}
            </button>
          );
        })}
        {types.length > 0 && (
          <button
            type="button"
            onClick={() => setTypes([])}
            className="px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Clear
          </button>
        )}
      </div>

      <div className="mt-4">
        <EntityGraph
          focusEntityId={id}
          depth={depth}
          direction={direction}
          types={types.length ? types : undefined}
          minWeight={minWeight || undefined}
          className="h-[72vh]"
        />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {(["person", "organization", "location", "selector"] as const).map((t) => {
          const meta = ENTITY_TYPE_META[t];
          return (
            <span
              key={t}
              className="flex items-center gap-1 rounded-md border border-border bg-card/80 px-1.5 py-0.5 text-[11px] text-muted-foreground"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: meta.color }}
              />
              {meta.label}
            </span>
          );
        })}
      </div>

    </div>
  );
}
