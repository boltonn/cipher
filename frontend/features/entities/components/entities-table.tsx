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
import { BadgeCheck } from "lucide-react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

interface EntitiesTableProps {
  entities: Entity[];
  emptyMessage?: string;
}

export function EntitiesTable({ entities, emptyMessage = "No entities match these filters." }: EntitiesTableProps) {
  if (entities.length === 0) {
    return <p className="py-16 text-center text-xs italic text-muted-foreground">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="text-[10px] font-black uppercase tracking-widest">Name</TableHead>
            <TableHead className="text-[10px] font-black uppercase tracking-widest">Type</TableHead>
            <TableHead className="text-[10px] font-black uppercase tracking-widest">Aliases</TableHead>
            <TableHead className="text-[10px] font-black uppercase tracking-widest">Tags</TableHead>
            <TableHead className="text-[10px] font-black uppercase tracking-widest">Updated</TableHead>
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
                  {e.isVerified && <BadgeCheck size={13} className="text-primary" />}
                </Link>
              </TableCell>
              <TableCell>
                <EntityTypeBadge type={e.entityType} suggested={!e.isVerified && e.source === "extraction"} />
              </TableCell>
              <TableCell className="max-w-48 truncate text-xs text-muted-foreground">
                {e.aliases.length ? e.aliases.join(", ") : "—"}
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
                {formatDistanceToNow(new Date(e.dateUpdated), { addSuffix: true })}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
