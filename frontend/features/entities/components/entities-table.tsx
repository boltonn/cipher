"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EntityTypeBadge } from "@/features/entities/components/entity-type-badge";
import type { Entity } from "@/features/entities/types";
import { cn } from "@/lib/utils";
import {
  BadgeCheck,
  ChevronDown,
  ChevronsUpDown,
  ChevronUp,
} from "lucide-react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

export type EntitySortKey = "display_name" | "date_updated";
export type EntitySortOrder = "asc" | "desc";

interface EntitiesTableProps {
  entities: Entity[];
  emptyMessage?: string;
  sortBy?: EntitySortKey;
  sortOrder?: EntitySortOrder;
  onSortChange?: (key: EntitySortKey) => void;
}

function SortHead({
  label,
  sortKey,
  sortBy,
  sortOrder,
  onSortChange,
}: {
  label: string;
  sortKey: EntitySortKey;
  sortBy?: EntitySortKey;
  sortOrder?: EntitySortOrder;
  onSortChange?: (key: EntitySortKey) => void;
}) {
  const active = sortBy === sortKey;
  const Icon = !active
    ? ChevronsUpDown
    : sortOrder === "asc"
      ? ChevronUp
      : ChevronDown;
  return (
    <TableHead className="text-[10px] font-black uppercase tracking-widest">
      <button
        type="button"
        onClick={() => onSortChange?.(sortKey)}
        disabled={!onSortChange}
        className={cn(
          "-ml-1 flex items-center gap-1 rounded px-1 py-0.5 transition-colors",
          onSortChange && "hover:text-foreground",
          active ? "text-foreground" : "text-muted-foreground"
        )}
      >
        {label}
        <Icon size={12} className={active ? "opacity-100" : "opacity-40"} />
      </button>
    </TableHead>
  );
}

export function EntitiesTable({
  entities,
  emptyMessage = "No entities match these filters.",
  sortBy,
  sortOrder,
  onSortChange,
}: EntitiesTableProps) {
  if (entities.length === 0) {
    return (
      <p className="py-16 text-center text-xs italic text-muted-foreground">
        {emptyMessage}
      </p>
    );
  }

  const sortProps = { sortBy, sortOrder, onSortChange };

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <SortHead label="Name" sortKey="display_name" {...sortProps} />
            <TableHead className="text-[10px] font-black uppercase tracking-widest">
              Type
            </TableHead>
            <TableHead className="text-[10px] font-black uppercase tracking-widest">
              Tags
            </TableHead>
            <SortHead label="Updated" sortKey="date_updated" {...sortProps} />
          </TableRow>
        </TableHeader>
        <TableBody>
          {entities.map((e) => (
            <TableRow key={e.id} className="group cursor-pointer">
              <TableCell>
                <Link
                  href={`/entities/${e.id}`}
                  className="flex items-center gap-2 font-medium text-foreground group-hover:text-primary"
                >
                  {e.displayName}
                  {e.isVerified && (
                    <BadgeCheck size={13} className="text-primary" />
                  )}
                </Link>
              </TableCell>
              <TableCell>
                <EntityTypeBadge
                  type={e.entityType}
                  suggested={!e.isVerified && e.source === "extraction"}
                />
              </TableCell>
              <TableCell className="max-w-40 truncate">
                <div className="flex flex-wrap gap-1">
                  {e.tags.slice(0, 3).map((t) => (
                    <Badge
                      key={t}
                      variant="outline"
                      className="h-5 border-border bg-muted/40 px-1.5 text-[10px] text-muted-foreground"
                    >
                      #{t}
                    </Badge>
                  ))}
                </div>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {formatDistanceToNow(new Date(e.dateUpdated), {
                  addSuffix: true,
                })}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
