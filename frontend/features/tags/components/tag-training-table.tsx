"use client";

import { EmptyState } from "@/components/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTagTrainingReadiness } from "@/features/tags/hooks/use-tag-stats";
import { cn } from "@/lib/utils";
import { Tags } from "lucide-react";

/** Analyst positives / negatives per image tag against what a classifier head needs. */
export function TagTrainingTable() {
  const { data: rows, isPending } = useTagTrainingReadiness();
  if (isPending) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!rows?.length) {
    return <EmptyState icon={Tags} title="No labelled image tags yet" body="Label images with a tag to start." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Tag</TableHead>
          <TableHead className="text-right">Positives</TableHead>
          <TableHead className="text-right">Negatives</TableHead>
          <TableHead className="w-64">Toward a head</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.tag}>
            <TableCell className="font-medium">{row.tag}</TableCell>
            <TableCell className="text-right tabular-nums">{row.positives.toLocaleString()}</TableCell>
            <TableCell className="text-right tabular-nums">{row.negatives.toLocaleString()}</TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn("h-full rounded-full", row.isReady ? "bg-primary" : "bg-muted-foreground/40")}
                    style={{ width: `${Math.min(100, (row.positives / row.minPositives) * 100)}%` }}
                  />
                </div>
                <span className={cn("w-28 text-xs", row.isReady ? "text-primary" : "text-muted-foreground")}>
                  {row.isReady ? "Ready to train" : `${row.minPositives - row.positives} more positives`}
                </span>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
