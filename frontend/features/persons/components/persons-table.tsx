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
import { PersonAvatar } from "@/features/persons/components/person-avatar";
import type { Person } from "@/features/persons/types";
import type { GridSelection } from "@/hooks/use-grid-selection";
import { cn, humanize } from "@/lib/utils";
import { BadgeCheck } from "lucide-react";
import { useRouter } from "next/navigation";

/** Compact row list of people -- the table alternative to the card grid. */
export function PersonsTable({
  persons,
  selection,
}: {
  persons: Person[];
  selection?: GridSelection;
}) {
  const router = useRouter();
  const ids = persons.map((p) => p.id);
  const selectedCount = selection
    ? ids.filter((id) => selection.selectedIds.has(id)).length
    : 0;

  return (
    <div className="overflow-x-auto rounded-xl border border-border/50">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {selection && (
              <TableHead className="w-8">
                <Checkbox
                  aria-label="Select all people on this page"
                  checked={
                    selectedCount === 0
                      ? false
                      : selectedCount === ids.length
                        ? true
                        : "indeterminate"
                  }
                  onCheckedChange={(checked) =>
                    checked ? selection.selectAll(ids) : selection.clear()
                  }
                />
              </TableHead>
            )}
            <TableHead className="w-10" />
            <TableHead>Name</TableHead>
            <TableHead>a.k.a.</TableHead>
            <TableHead>Born</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Tags</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {persons.map((p) => {
            const aka =
              p.aliases.length > 0
                ? `${p.aliases[0]}${p.aliases.length > 1 ? ` +${p.aliases.length - 1}` : ""}`
                : "—";
            const isSelected = !!selection?.selectedIds.has(p.id);
            return (
              <TableRow
                key={p.id}
                onClick={(e) => {
                  if (selection && (selection.selectedIds.size > 0 || e.shiftKey))
                    selection.toggle(p.id, ids, e.shiftKey);
                  else router.push(`/persons/${p.id}`);
                }}
                data-state={isSelected ? "selected" : undefined}
                className={cn("cursor-pointer", isSelected && "bg-primary/5")}
              >
                {selection && (
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      aria-label={isSelected ? "Deselect person" : "Select person"}
                      checked={isSelected}
                      onClick={(e) => {
                        e.preventDefault();
                        selection.toggle(p.id, ids, e.shiftKey);
                      }}
                    />
                  </TableCell>
                )}
                <TableCell>
                  <PersonAvatar person={p} size="sm" />
                </TableCell>
                <TableCell className="font-medium text-foreground">
                  <span className="flex items-center gap-1.5">
                    {p.name || "Unnamed"}
                    {p.isVerified && (
                      <BadgeCheck size={13} className="shrink-0 text-primary" />
                    )}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground">{aka}</TableCell>
                <TableCell className="text-muted-foreground">
                  {p.dateOfBirth
                    ? new Date(p.dateOfBirth).toLocaleDateString()
                    : "—"}
                </TableCell>
                <TableCell className="capitalize text-muted-foreground">
                  {humanize(p.source)}
                </TableCell>
                <TableCell>
                  {p.tags.length > 0 ? (
                    <span className="flex flex-wrap gap-1">
                      {p.tags.slice(0, 3).map((t) => (
                        <Badge
                          key={t}
                          variant="outline"
                          className="h-5 border-border bg-muted/40 px-1.5 py-0 text-[11px] text-muted-foreground"
                        >
                          #{t}
                        </Badge>
                      ))}
                      {p.tags.length > 3 && (
                        <span className="text-[11px] text-muted-foreground">
                          +{p.tags.length - 3}
                        </span>
                      )}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
