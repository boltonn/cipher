"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Button } from "@/components/ui/button";
import { FileSummary } from "@/features/files/components/file-summary";
import { useTable } from "@/features/tables/api";
import { TableMappingView } from "@/features/tables/components/table-mapping-view";
import { FileText, Table2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use } from "react";

/**
 * One table, keyed by content hash like images: its rows, with how its columns map onto
 * people, places, selectors and relationships drawn on the headers. `?datasetId=` picks
 * the dataset's mapping when the same file was ingested into several.
 */
export default function TablePage({ params }: { params: Promise<{ sha256: string }> }) {
  const { sha256 } = use(params);
  const datasetId = useSearchParams().get("datasetId") ?? undefined;
  const { data: table, isPending, isError, refetch } = useTable(sha256, datasetId);

  if (isPending) return <PageLoading icon={Table2} label="Loading table…" onRetry={() => refetch()} />;
  if (isError || !table) {
    return (
      <PageError
        className="mt-24"
        title="Couldn’t load this table"
        body="Its record didn’t come back. This is usually temporary — try again, or head back."
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="mx-auto flex h-full w-full min-w-0 max-w-400 flex-col px-6 pb-6 pt-5">
      <PageHeader
        eyebrow="Table"
        icon={<Table2 size={10} className="text-primary/50" />}
        value={table.filename}
        actions={
          <Button asChild variant="outline" size="sm" className="h-8 gap-2 text-xs">
            <Link href={`/files/${table.fileId}`}>
              <FileText size={13} /> Extracted text
            </Link>
          </Button>
        }
      />
      <FileSummary fileId={table.fileId} className="mt-4" />
      <div className="mt-4 min-h-0 min-w-0 flex-1 overflow-hidden rounded-xl border border-border bg-muted/40 shadow-xl">
        {table.mappings.length > 0 ? (
          <TableMappingView sha256={sha256} mappings={table.mappings} />
        ) : (
          <EmptyState
            className="mt-24"
            icon={Table2}
            title="Not mapped yet"
            body="Run `cipher map-tables` on this dataset to read the table and propose how its columns map onto entities and relationships."
          />
        )}
      </div>
    </div>
  );
}
