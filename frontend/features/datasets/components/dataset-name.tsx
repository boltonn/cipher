"use client";

import { useDataset } from "@/features/datasets/api";
import { cn } from "@/lib/utils";
import { Database } from "lucide-react";

/** Inline "which dataset" label for rows shown across several datasets. */
export function DatasetName({ datasetId, className }: { datasetId: string; className?: string }) {
  const { data: dataset } = useDataset(datasetId);
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px] text-muted-foreground", className)}>
      <Database size={11} className="shrink-0" />
      <span className="truncate">{dataset?.name ?? "…"}</span>
    </span>
  );
}
