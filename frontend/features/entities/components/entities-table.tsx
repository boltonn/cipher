"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EntityTypeBadge } from "@/features/entities/components/entity-type-badge";
import { InvalidateEntityDialog } from "@/features/entities/components/invalidate-entity-dialog";
import type {
  EntityListItem,
  EntitySortKey,
} from "@/features/entities/types";
import { cn } from "@/lib/utils";
import {
  BadgeCheck,
  Ban,
  ChevronDown,
  ChevronsUpDown,
  ChevronUp,
  GitMerge,
  Network,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { formatDistanceToNow } from "date-fns";
import { useState } from "react";

export type EntitySortOrder = "asc" | "desc";

interface EntitiesTableProps {
  entities: EntityListItem[];
  emptyMessage?: string;
  sortBy?: EntitySortKey;
  sortOrder?: EntitySortOrder;
  onSortChange?: (key: EntitySortKey) => void;
  /** open the Resolve tab narrowed to name groups that may be this entity */
  onOpenResolve?: (entity: EntityListItem) => void;
}

function SortHead({
  label,
  sortKey,
  sortBy,
  sortOrder,
  onSortChange,
  className,
}: {
  label: string;
  sortKey: EntitySortKey;
  sortBy?: EntitySortKey;
  sortOrder?: EntitySortOrder;
  onSortChange?: (key: EntitySortKey) => void;
  className?: string;
}) {
  const active = sortBy === sortKey;
  const Icon = !active
    ? ChevronsUpDown
    : sortOrder === "asc"
      ? ChevronUp
      : ChevronDown;
  return (
    <TableHead className={className}>
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
  onOpenResolve,
}: EntitiesTableProps) {
  const router = useRouter();
  const [invalidating, setInvalidating] = useState<EntityListItem | null>(
    null
  );

  if (entities.length === 0) {
    return (
      <p className="py-16 text-center text-xs italic text-muted-foreground">
        {emptyMessage}
      </p>
    );
  }

  const sortProps = { sortBy, sortOrder, onSortChange };
  const maxMentions = Math.max(1, ...entities.map((e) => e.mentionCount));

  return (
    <TooltipProvider delayDuration={150}>
      <div className="overflow-hidden rounded-xl border border-border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <SortHead label="Name" sortKey="displayName" {...sortProps} />
              <TableHead>Type</TableHead>
              <SortHead
                label="Mentions"
                sortKey="mentionCount"
                className="w-44"
                {...sortProps}
              />
              <TableHead className="text-right">
                Relationships
              </TableHead>
              <TableHead>Open work</TableHead>
              <SortHead label="Updated" sortKey="dateUpdated" {...sortProps} />
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {entities.map((e) => {
              const orphan = e.mentionCount === 0;
              return (
                <TableRow
                  key={e.id}
                  className={cn("group cursor-pointer", orphan && "opacity-60")}
                  onClick={() => router.push(`/entities/${e.id}`)}
                >
                  <TableCell className="max-w-72">
                    <Link
                      href={`/entities/${e.id}`}
                      // Real link for keyboard nav, middle-click and "open in new
                      // tab"; the row onClick handles the common case.
                      onClick={(ev) => ev.stopPropagation()}
                      className="flex items-center gap-2 font-medium text-foreground group-hover:text-primary"
                    >
                      <span className="truncate">{e.displayName}</span>
                      {e.isVerified && (
                        <BadgeCheck size={13} className="shrink-0 text-primary" />
                      )}
                    </Link>
                    {e.tags.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {e.tags.slice(0, 3).map((t) => (
                          <Badge
                            key={t}
                            variant="outline"
                            className="h-4 border-border bg-muted/40 px-1 text-[11px] text-muted-foreground"
                          >
                            #{t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <EntityTypeBadge
                      type={e.entityType}
                      detail={e.selectorType}
                      subtype={e.selectorSubtype}
                      suggested={!e.isVerified && e.source === "extraction"}
                    />
                  </TableCell>
                  <TableCell>
                    {orphan ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="text-[11px] italic text-muted-foreground">
                            no mentions
                          </span>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-60 text-xs">
                          Nothing in this dataset points at this entity — often a
                          leftover from an earlier extraction run.
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <div className="space-y-1">
                        <p className="text-xs tabular-nums text-foreground">
                          {e.mentionCount.toLocaleString()}
                          <span className="text-muted-foreground">
                            {" "}
                            in {e.fileCount.toLocaleString()} file
                            {e.fileCount === 1 ? "" : "s"}
                          </span>
                        </p>
                        <div className="h-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-primary/60"
                            style={{
                              width: `${Math.max(2, (e.mentionCount / maxMentions) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 text-xs tabular-nums",
                        e.relationshipCount
                          ? "text-foreground"
                          : "text-muted-foreground/60"
                      )}
                    >
                      <Network size={11} className="text-muted-foreground" />
                      {e.relationshipCount.toLocaleString()}
                    </span>
                  </TableCell>
                  <TableCell>
                    {e.pendingMatchCount > 0 ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(ev) => {
                          ev.stopPropagation();
                          onOpenResolve?.(e);
                        }}
                        className="h-6 gap-1 border-annotation/40 bg-annotation/10 px-2 text-[11px] text-annotation hover:bg-annotation/20 hover:text-annotation"
                      >
                        <GitMerge size={11} />
                        {e.pendingMatchCount} to resolve
                      </Button>
                    ) : (
                      <span className="text-[11px] text-muted-foreground/50">
                        —
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(e.dateUpdated), {
                      addSuffix: true,
                    })}
                  </TableCell>
                  <TableCell>
                    {!e.personId && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label={`Mark ${e.displayName} invalid`}
                            onClick={(ev) => {
                              ev.stopPropagation();
                              setInvalidating(e);
                            }}
                            className="h-7 w-7 text-muted-foreground/50 opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
                          >
                            <Ban size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent className="text-xs">
                          Mark invalid…
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {invalidating && (
        <InvalidateEntityDialog
          entity={invalidating}
          open
          onOpenChange={(open) => !open && setInvalidating(null)}
        />
      )}
    </TooltipProvider>
  );
}
