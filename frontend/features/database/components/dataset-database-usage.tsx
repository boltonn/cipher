"use client";

import { useDatasetDatabaseUsage } from "@/features/database/api";
import { ShareBar } from "@/features/database/components/share-bar";
import { formatBytes, formatCompactNumber } from "@/lib/utils";
import { HardDrive } from "lucide-react";

/** Admin-only panel: this dataset's rows and estimated size (and index size) in each table. */
export function DatasetDatabaseUsagePanel({ datasetId }: { datasetId: string }) {
  const { data: usage, isPending } = useDatasetDatabaseUsage(datasetId);

  return (
    <div className="mt-6 rounded-2xl border border-admin/25 bg-muted/40 p-4">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-muted-foreground">
        <span className="flex items-center gap-2">
          <HardDrive size={14} className="text-admin" />
          <h2 className="text-[11px] font-semibold uppercase tracking-wide">
            Database usage
          </h2>
        </span>
        {usage && (
          <span className="text-xs">
            ≈ {formatBytes(usage.estimatedBytes)} · {formatCompactNumber(usage.rowCount)} rows ·
            indexes ≈ {formatBytes(usage.estimatedIndexBytes)}
          </span>
        )}
      </div>
      {isPending ? (
        <p className="text-xs text-muted-foreground">Measuring…</p>
      ) : !usage || usage.tables.length === 0 ? (
        <p className="text-xs text-muted-foreground">No rows in the database yet.</p>
      ) : (
        <ul className="grid gap-x-8 gap-y-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {usage.tables.map((table) => (
            <li key={table.tableName} className="space-y-1">
              <div className="flex items-baseline justify-between gap-3 text-xs">
                <span className="truncate font-mono text-foreground">{table.tableName}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {formatCompactNumber(table.rowCount)} rows · ≈ {formatBytes(table.estimatedBytes)}
                </span>
              </div>
              <ShareBar value={table.estimatedBytes} total={usage.estimatedBytes} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
