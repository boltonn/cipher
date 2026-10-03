"use client";

import { EmptyState } from "@/components/empty-state";
import { PageLoading } from "@/components/page-loading";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDatabaseMetrics } from "@/features/database/api";
import { ShareBar } from "@/features/database/components/share-bar";
import type { TableScope } from "@/features/database/types";
import { formatBytes, formatCompactNumber } from "@/lib/utils";
import { Database } from "lucide-react";
import { useRouter } from "next/navigation";

const SCOPE_LABEL: Record<TableScope, string> = {
  dataset: "Dataset",
  file: "Via file",
  shared: "Shared",
};

const SCOPE_HINT: Record<TableScope, string> = {
  dataset: "Rows carry their own dataset.",
  file: "Rows belong to a file, and the file to a dataset.",
  shared: "Content-addressed or global; not attributed to one dataset.",
};

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-border bg-muted/40 p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

/** Postgres size, split by dataset (estimated from row shares) and by table. */
export function DatabaseOverview() {
  const router = useRouter();
  const { data: metrics, isPending, isError } = useDatabaseMetrics();

  if (isPending) return <PageLoading icon={Database} label="Measuring the database…" />;
  if (isError || !metrics) {
    return <EmptyState icon={Database} title="Couldn't read database metrics" />;
  }

  const { databaseSizeBytes, tables, datasets } = metrics;
  const datasetBytes = datasets.reduce((sum, dataset) => sum + dataset.estimatedBytes, 0);
  const sharedBytes = tables
    .filter((table) => table.scope === "shared")
    .reduce((sum, table) => sum + table.totalBytes, 0);

  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat
          label="Database"
          value={formatBytes(databaseSizeBytes)}
          detail={`${tables.length} tables`}
        />
        <Stat
          label="In datasets"
          value={`≈ ${formatBytes(datasetBytes)}`}
          detail={`across ${datasets.length} ${datasets.length === 1 ? "dataset" : "datasets"}`}
        />
        <Stat
          label="Shared"
          value={formatBytes(sharedBytes)}
          detail="images, faces, enrichments and other content-addressed tables"
        />
      </div>

      <section>
        <h2 className="mb-1 text-sm font-medium text-foreground">By dataset</h2>
        <p className="mb-2 text-xs text-muted-foreground">
          Sizes are estimates: each dataset&apos;s share of a table&apos;s rows times that
          table&apos;s size.
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Dataset</TableHead>
              <TableHead className="text-right">Rows</TableHead>
              <TableHead className="text-right">Indexes</TableHead>
              <TableHead className="text-right">Size</TableHead>
              <TableHead className="w-1/4">Share of database</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {datasets.map((dataset) => (
              <TableRow
                key={dataset.datasetId}
                onClick={() => router.push(`/datasets/${dataset.datasetId}`)}
                className="cursor-pointer"
              >
                <TableCell>{dataset.datasetName}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatCompactNumber(dataset.rowCount)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  ≈ {formatBytes(dataset.estimatedIndexBytes)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  ≈ {formatBytes(dataset.estimatedBytes)}
                </TableCell>
                <TableCell>
                  <ShareBar value={dataset.estimatedBytes} total={databaseSizeBytes} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium text-foreground">By table</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Table</TableHead>
              <TableHead>Attributed</TableHead>
              <TableHead className="text-right">Rows (est.)</TableHead>
              <TableHead className="text-right">Indexes</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="w-1/4">Share of database</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tables.map((table) => (
              <TableRow key={table.name}>
                <TableCell className="font-mono text-xs">{table.name}</TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    title={SCOPE_HINT[table.scope]}
                    className="font-normal text-muted-foreground"
                  >
                    {SCOPE_LABEL[table.scope]}
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {table.rowCount === null ? "–" : formatCompactNumber(table.rowCount)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatBytes(table.indexBytes)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatBytes(table.totalBytes)}
                </TableCell>
                <TableCell>
                  <ShareBar value={table.totalBytes} total={databaseSizeBytes} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  );
}
