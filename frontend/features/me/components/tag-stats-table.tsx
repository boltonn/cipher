"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTagStats } from "@/features/tags/hooks/use-tag-stats";
import { formatDistanceToNow, parseISO } from "date-fns";

const TARGET_LABELS = { content: "Files & images", entity: "Entities", event: "Events" } as const;

/** Every tag in use: analyst labels vs model output (amber), and how many of the labels are yours. */
export function TagStatsTable() {
  const { data: stats, isPending } = useTagStats();
  if (isPending) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!stats?.length) return <p className="text-sm text-muted-foreground">No tags yet.</p>;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Tag</TableHead>
          <TableHead>On</TableHead>
          <TableHead className="text-right">Labelled</TableHead>
          <TableHead className="text-right">Rejected</TableHead>
          <TableHead className="text-right text-annotation">Model</TableHead>
          <TableHead className="text-right">By you</TableHead>
          <TableHead className="text-right">Last used</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {stats.map((row) => (
          <TableRow key={`${row.targetType}:${row.tag}`}>
            <TableCell className="font-medium">{row.tag}</TableCell>
            <TableCell className="text-muted-foreground">{TARGET_LABELS[row.targetType]}</TableCell>
            <TableCell className="text-right tabular-nums">{row.labelled.toLocaleString()}</TableCell>
            <TableCell className="text-right tabular-nums">{row.rejected.toLocaleString()}</TableCell>
            <TableCell className="text-right tabular-nums text-annotation">{row.predicted.toLocaleString()}</TableCell>
            <TableCell className="text-right tabular-nums">{row.byYou.toLocaleString()}</TableCell>
            <TableCell className="text-right text-muted-foreground">
              {formatDistanceToNow(parseISO(row.dateLastUsed), { addSuffix: true })}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
