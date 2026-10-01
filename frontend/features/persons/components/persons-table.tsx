"use client";

import { Badge } from "@/components/ui/badge";
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
import { BadgeCheck } from "lucide-react";
import { useRouter } from "next/navigation";

/** Compact row list of people -- the table alternative to the card grid. */
export function PersonsTable({ persons }: { persons: Person[] }) {
  const router = useRouter();

  return (
    <div className="overflow-x-auto rounded-xl border border-border/50">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
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
            return (
              <TableRow
                key={p.id}
                onClick={() => router.push(`/persons/${p.id}`)}
                className="cursor-pointer"
              >
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
                  {p.source.replace(/_/g, " ")}
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
