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
  EventFilters,
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
  /** Clicking a row's type or status narrows the filter bar to that value. */
  onFilter: (patch: Partial<EventFilters>) => void;
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
  onFilter,
  onSelect,
  checkedIds,
  onCheckedIdsChange,
}: EventsTableProps) {
  const sortProps = { sortBy, sortOrder, onSortChange };
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
            <SortHead label="When" sortKey="dateStart" {...sortProps} />
            <SortHead label="Event" sortKey="title" {...sortProps} />
            <SortHead label="Type" sortKey="eventType" {...sortProps} />
            <SortHead label="Status" sortKey="status" {...sortProps} />
            <SortHead label="Added" sortKey="dateCreated" {...sortProps} />
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
                  <button
                    type="button"
                    title={`Show only ${meta.label.toLowerCase()} events`}
                    onClick={(click) => {
                      click.stopPropagation();
                      onFilter({ eventType: e.eventType });
                    }}
                    className="rounded-md transition-opacity hover:opacity-80"
                  >
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
                  </button>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  <button
                    type="button"
                    title={`Show only ${EVENT_STATUS_LABELS[e.status].toLowerCase()} events`}
                    onClick={(click) => {
                      click.stopPropagation();
                      onFilter({ status: e.status });
                    }}
                    className="rounded px-1 -mx-1 py-0.5 hover:bg-muted hover:text-foreground"
                  >
                    {EVENT_STATUS_LABELS[e.status]}
                  </button>
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
