"use client";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EVENT_STATUS_LABELS,
  EVENT_TYPE_META,
  categoryMeta,
} from "@/features/events/components/event-type-meta";
import { formatEventStart } from "@/features/events/lib/format";
import type {
  CipherEvent,
  EventSortField,
  SortOrder,
} from "@/features/events/types";
import { cn } from "@/lib/utils";
import { BadgeCheck, ChevronDown, ChevronsUpDown, ChevronUp, Sparkles } from "lucide-react";

interface EventsTableProps {
  events: CipherEvent[];
  sortBy: EventSortField;
  sortOrder: SortOrder;
  onSortChange: (key: EventSortField) => void;
  onSelect: (event: CipherEvent) => void;
  checkedIds: ReadonlySet<string>;
  onCheckedIdsChange: (next: Set<string>) => void;
}

function SortHead({
  label,
  sortKey,
  sortBy,
  sortOrder,
  onSortChange,
}: {
  label: string;
  sortKey: EventSortField;
  sortBy: EventSortField;
  sortOrder: SortOrder;
  onSortChange: (key: EventSortField) => void;
}) {
  const active = sortBy === sortKey;
  const Icon = !active ? ChevronsUpDown : sortOrder === "asc" ? ChevronUp : ChevronDown;
  return (
    <TableHead>
      <button
        type="button"
        onClick={() => onSortChange(sortKey)}
        className={cn(
          "-ml-1 flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:text-foreground",
          active ? "text-foreground" : "text-muted-foreground"
        )}
      >
        {label}
        <Icon size={12} className={active ? "opacity-100" : "opacity-40"} />
      </button>
    </TableHead>
  );
}

export function EventsTable({
  events,
  sortBy,
  sortOrder,
  onSortChange,
  onSelect,
  checkedIds,
  onCheckedIdsChange,
}: EventsTableProps) {
  const checkedOnPage = events.filter((e) => checkedIds.has(e.id)).length;
  const setChecked = (ids: string[], checked: boolean) => {
    const next = new Set(checkedIds);
    for (const id of ids) {
      if (checked) next.add(id);
      else next.delete(id);
    }
    onCheckedIdsChange(next);
  };
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="w-9">
              <Checkbox
                checked={
                  checkedOnPage === 0
                    ? false
                    : checkedOnPage === events.length
                      ? true
                      : "indeterminate"
                }
                onCheckedChange={(checked) =>
                  setChecked(
                    events.map((e) => e.id),
                    checked === true
                  )
                }
                aria-label="Select all on this page"
              />
            </TableHead>
            <SortHead
              label="When"
              sortKey="date_start"
              sortBy={sortBy}
              sortOrder={sortOrder}
              onSortChange={onSortChange}
            />
            <TableHead>
              Event
            </TableHead>
            <TableHead>
              Type
            </TableHead>
            <TableHead>
              Status
            </TableHead>
            <SortHead
              label="Added"
              sortKey="date_created"
              sortBy={sortBy}
              sortOrder={sortOrder}
              onSortChange={onSortChange}
            />
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((e) => {
            const meta = EVENT_TYPE_META[e.eventType];
            const cat = categoryMeta(e.category);
            return (
              <TableRow
                key={e.id}
                className={cn("group cursor-pointer", checkedIds.has(e.id) && "bg-primary/5")}
                onClick={() => onSelect(e)}
              >
                <TableCell onClick={(click) => click.stopPropagation()}>
                  <Checkbox
                    checked={checkedIds.has(e.id)}
                    onCheckedChange={(checked) => setChecked([e.id], checked === true)}
                    aria-label={`Select ${e.title}`}
                  />
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                  {formatEventStart(e)}
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "flex items-center gap-2 font-medium text-foreground group-hover:text-primary",
                      e.status === "cancelled" && "line-through opacity-60"
                    )}
                  >
                    <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", cat.dotClass)} />
                    <span className="truncate">{e.title}</span>
                    {e.isVerified ? (
                      <BadgeCheck size={13} className="shrink-0 text-primary" />
                    ) : e.extractor === "llm" ? (
                      <Sparkles size={12} className="shrink-0 text-annotation" />
                    ) : null}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={cn(
                      "h-6 gap-1.5 px-2 text-[11px] font-bold uppercase tracking-wide",
                      cat.bgClass,
                      cat.textClass,
                      cat.borderClass
                    )}
                  >
                    <meta.Icon size={11} />
                    {meta.label}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {EVENT_STATUS_LABELS[e.status]}
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                  {new Date(e.dateCreated).toLocaleDateString()}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
