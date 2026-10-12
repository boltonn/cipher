"use client";

import { Button } from "@/components/ui/button";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import {
  useFieldTypes,
  useRelationshipVerbs,
  useUpdateTableMapping,
  useVerifyTableMapping,
} from "@/features/tables/api";
import { ColumnMappingPopover } from "@/features/tables/components/column-mapping-popover";
import { RelationshipPopover, verbLabel } from "@/features/tables/components/relationship-popover";
import { addEdge, setColumn, setEdge } from "@/features/tables/lib/edit";
import { chipClass, fieldIcon } from "@/features/tables/lib/field-meta";
import type { EntitySlot, TableMappingDetail, TableMappingFileStatus } from "@/features/tables/types";
import { cn } from "@/lib/utils";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowRight, BadgeCheck, Files, Loader2, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

const COLUMN_WIDTH_PX = 192;
const ROW_HEIGHT_PX = 34;

const FILE_STATUS: Record<TableMappingFileStatus, string> = {
  waiting: "waiting for verify",
  queued: "queued for emit-tables",
  emitted: "emitted",
  failed: "failed",
};

/** Contiguous runs of columns that belong to the same slot -- drawn as one band over their headers. */
function slotBands(columnCount: number, slots: EntitySlot[]) {
  const owner = new Map<number, EntitySlot>();
  for (const slot of slots) for (const index of slot.columns) owner.set(index, slot);
  const bands: { start: number; span: number; slot: EntitySlot | null }[] = [];
  for (let i = 0; i < columnCount; i++) {
    const slot = owner.get(i) ?? null;
    const last = bands[bands.length - 1];
    if (last && last.slot === slot) last.span += 1;
    else bands.push({ start: i, span: 1, slot });
  }
  return bands;
}

function FilesUsingLayout({ detail, sha256 }: { detail: TableMappingDetail; sha256: string }) {
  return (
    <HoverCard openDelay={150}>
      <HoverCardTrigger asChild>
        <span className="flex cursor-default items-center gap-1.5 text-xs text-muted-foreground">
          <Files size={13} />
          {detail.files.length === 1 ? "Only this file" : `${detail.files.length} files share this layout`}
        </span>
      </HoverCardTrigger>
      <HoverCardContent align="end" className="w-80 p-3">
        <p className="text-xs text-muted-foreground">One mapping covers every file with these headers.</p>
        <ul className="mt-2 space-y-1 text-xs">
          {detail.files.map((f) => (
            <li key={`${f.fileId}-${f.sheet ?? ""}`} className="flex items-center gap-2">
              {f.sha256 === sha256 ? (
                <span className="truncate font-medium">{f.filename} (this table)</span>
              ) : (
                <Link href={`/tables/${f.sha256}`} className="truncate hover:underline">
                  {f.filename}
                </Link>
              )}
              <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{FILE_STATUS[f.status]}</span>
            </li>
          ))}
        </ul>
      </HoverCardContent>
    </HoverCard>
  );
}

function SheetMapping({ sha256, detail }: { sha256: string; detail: TableMappingDetail }) {
  const fieldTypes = useFieldTypes();
  const verbs = useRelationshipVerbs();
  const update = useUpdateTableMapping(sha256, detail.id);
  const verify = useVerifyTableMapping(sha256, detail.id);
  const scrollRef = useRef<HTMLDivElement>(null);
  const busy = update.isPending || verify.isPending;

  const { mapping, sample } = detail;
  const fields = new Map((fieldTypes.data ?? []).map((f) => [f.id, f]));
  const width = COLUMN_WIDTH_PX * mapping.columns.length;
  const gridTemplateColumns = `repeat(${mapping.columns.length}, ${COLUMN_WIDTH_PX}px)`;
  const bands = slotBands(mapping.columns.length, mapping.slots);
  const proposals = mapping.columns.filter((c) => c.decisionSource === "model" && c.fieldType !== "other").length;

  const rows = useVirtualizer({
    count: sample.rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT_PX,
    overscan: 8,
  });

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex min-h-12 flex-wrap items-center gap-2 border-b bg-background px-3 py-2">
        {mapping.edges.map((edge, at) => (
          <RelationshipPopover
            key={`${edge.srcSlot}-${edge.dstSlot}-${at}`}
            slots={mapping.slots}
            verbs={verbs.data ?? []}
            edge={edge}
            busy={busy}
            onApply={({ verb, isEnabled }) => update.mutate(setEdge(mapping, at, verb, isEnabled))}
          >
            <button
              type="button"
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs transition-colors hover:bg-accent",
                edge.decisionSource === "model" && !detail.isVerified
                  ? "border-dashed border-annotation/50 bg-annotation/10 text-annotation"
                  : "border-border bg-muted/40 text-foreground",
                (!edge.isEnabled || edge.isProposedVerb) && "opacity-50 line-through"
              )}
            >
              {edge.decisionSource === "model" && !detail.isVerified && <Sparkles size={11} />}
              <span className="font-medium">{edge.srcSlot}</span>
              <ArrowRight size={11} className="opacity-60" />
              {verbLabel(edge.relationshipType)}
              <ArrowRight size={11} className="opacity-60" />
              <span className="font-medium">{edge.dstSlot}</span>
            </button>
          </RelationshipPopover>
        ))}
        {mapping.slots.length >= 2 && (
          <RelationshipPopover
            slots={mapping.slots}
            verbs={verbs.data ?? []}
            busy={busy}
            onApply={({ srcSlot, verb, dstSlot }) => update.mutate(addEdge(mapping, srcSlot, verb, dstSlot))}
          >
            <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs text-muted-foreground">
              <Plus size={12} /> Relationship
            </Button>
          </RelationshipPopover>
        )}
        {mapping.edges.length === 0 && mapping.slots.length < 2 && (
          <span className="text-xs text-muted-foreground">Each row becomes one entity — no relationships between rows.</span>
        )}

        <div className="ml-auto flex items-center gap-3">
          {update.isPending && <Loader2 size={13} className="animate-spin text-muted-foreground" />}
          <FilesUsingLayout detail={detail} sha256={sha256} />
          {detail.isVerified ? (
            <span className="flex items-center gap-1.5 text-xs text-primary">
              <BadgeCheck size={14} /> Verified
            </span>
          ) : (
            <Button size="sm" className="h-8 gap-1.5 text-xs" disabled={busy} onClick={() => verify.mutate()}>
              <BadgeCheck size={13} /> Verify mapping
            </Button>
          )}
        </div>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
        <div style={{ width }}>
          <div className="sticky top-0 z-10 border-b bg-muted">
            <div className="grid h-7 border-b" style={{ gridTemplateColumns }}>
              {bands.map(({ start, span, slot }) => {
                const meta = slot ? ENTITY_TYPE_META[slot.entityType] : null;
                return (
                  <div
                    key={start}
                    className={cn(
                      "flex items-center gap-1.5 truncate border-r px-2 text-[11px] font-medium last:border-r-0",
                      meta && cn(meta.bgClass, meta.textClass)
                    )}
                    style={{ gridColumn: `span ${span}` }}
                  >
                    {meta && (
                      <>
                        <meta.Icon size={11} className="shrink-0" />
                        <span className="truncate">{slot?.name}</span>
                        <span className="truncate font-normal opacity-70">{meta.label.toLowerCase()}</span>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
            <TooltipProvider>
              <div className="grid" style={{ gridTemplateColumns }}>
                {mapping.columns.map((column) => {
                  const field = fields.get(column.fieldType);
                  const Icon = fieldIcon(field);
                  const fit = column.hitRate;
                  return (
                    <div key={column.index} className="relative flex flex-col gap-1 border-r px-2 pt-1.5 pb-2 last:border-r-0">
                      <span className="truncate text-xs font-semibold" title={column.header}>
                        {column.header}
                      </span>
                      <ColumnMappingPopover
                        column={column}
                        fieldTypes={fieldTypes.data ?? []}
                        busy={busy}
                        onApply={(fieldType, role) => update.mutate(setColumn(mapping, column.index, fieldType, role))}
                      >
                        <button
                          type="button"
                          className={cn(
                            "inline-flex w-fit max-w-full items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium transition-shadow hover:shadow-sm",
                            chipClass(column, field, detail.isVerified)
                          )}
                        >
                          <Icon size={11} className="shrink-0 opacity-80" />
                          <span className="truncate">{field?.label ?? column.fieldType}</span>
                        </button>
                      </ColumnMappingPopover>
                      {fit != null && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div className="absolute inset-x-0 bottom-0 h-0.5 bg-border/60">
                              <div
                                className={cn("h-full", fit < 0.8 ? "bg-destructive/70" : "bg-primary/60")}
                                style={{ width: `${Math.round(fit * 100)}%` }}
                              />
                            </div>
                          </TooltipTrigger>
                          <TooltipContent side="bottom">{Math.round(fit * 100)}% of sampled cells fit</TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  );
                })}
              </div>
            </TooltipProvider>
          </div>

          <div style={{ height: rows.getTotalSize(), position: "relative" }}>
            {rows.getVirtualItems().map((virtualRow) => {
              const row = sample.rows[virtualRow.index];
              return (
                <div
                  key={virtualRow.key}
                  className="absolute top-0 left-0 grid w-full border-b"
                  style={{ gridTemplateColumns, height: virtualRow.size, transform: `translateY(${virtualRow.start}px)` }}
                >
                  {mapping.columns.map((column) => (
                    <div
                      key={column.index}
                      className={cn(
                        "truncate border-r px-2 py-1.5 text-[13px] last:border-r-0",
                        column.fieldType === "other" && "text-muted-foreground"
                      )}
                      title={row[column.index]}
                    >
                      {row[column.index] ?? ""}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3 border-t bg-background px-3 py-1.5 text-[11px] text-muted-foreground">
        <span>
          {sample.rows.length.toLocaleString()} sampled rows
          {mapping.rowsEstimate ? ` of ~${mapping.rowsEstimate.toLocaleString()}` : ""}
        </span>
        {proposals > 0 && !detail.isVerified && (
          <span className="flex items-center gap-1 text-annotation">
            <Sparkles size={11} /> {proposals} column {proposals === 1 ? "type is a proposal" : "types are proposals"} — click a
            chip to change it
          </span>
        )}
      </div>
    </div>
  );
}

/** A table shown as itself, with its mapping onto the ontology drawn on the headers. */
export function TableMappingView({ sha256, mappings }: { sha256: string; mappings: TableMappingDetail[] }) {
  const [active, setActive] = useState(0);
  const detail = mappings[Math.min(active, mappings.length - 1)];
  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden bg-background">
      {mappings.length > 1 && (
        <div className="border-b px-3 py-2">
          <Tabs value={String(active)} onValueChange={(v) => setActive(Number(v))}>
            <TabsList>
              {mappings.map((m, i) => (
                <TabsTrigger key={m.id} value={String(i)} className="text-xs">
                  {m.mapping.sheet ?? `Sheet ${i + 1}`}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      )}
      <SheetMapping key={detail.id} sha256={sha256} detail={detail} />
    </div>
  );
}
