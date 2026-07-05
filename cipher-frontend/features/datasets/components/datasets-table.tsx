"use client";

import { DataTable } from "@/components/data-table/data-table";
import type {
  DataTableColumn,
  DataTableFilters,
  DataTableSortOrder,
} from "@/components/data-table/types";
import type { DatasetSummary } from "@/features/datasets/types";
import { formatBytes, formatCompactNumber } from "@/lib/utils";
import { useRouter } from "next/navigation";

const formatDate = (dateString: string) =>
  new Date(dateString).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

const columns: DataTableColumn<DatasetSummary>[] = [
  {
    key: "name",
    header: "Name",
    type: "text",
    sortable: true,
    filterable: true,
    width: "2fr",
  },
  { key: "description", header: "Description", type: "text", width: "3fr" },
  {
    key: "fileCount",
    header: "Files",
    type: "number",
    sortable: true,
    align: "right",
    width: "1fr",
    render: (row) => formatCompactNumber(row.fileCount),
  },
  {
    key: "totalSizeBytes",
    header: "Size",
    type: "number",
    sortable: true,
    align: "right",
    width: "1fr",
    render: (row) => formatBytes(row.totalSizeBytes),
  },
  {
    key: "filetypeCount",
    header: "Types",
    type: "number",
    sortable: true,
    align: "right",
    width: "1fr",
    render: (row) => formatCompactNumber(row.filetypeCount),
  },
  {
    key: "dateCreated",
    header: "Created",
    type: "date",
    sortable: true,
    filterable: true,
    width: "1.5fr",
    render: (row) => formatDate(row.dateCreated),
  },
  {
    key: "dateLastUpdated",
    header: "Updated",
    type: "date",
    sortable: true,
    filterable: true,
    width: "1.5fr",
    render: (row) => formatDate(row.dateLastUpdated),
  },
];

interface DatasetsTableProps {
  datasets: DatasetSummary[];
  total: number;
  page: number;
  limit: number;
  isLoading?: boolean;
  sortBy?: string;
  sortOrder?: DataTableSortOrder;
  filters: DataTableFilters;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
  onSortChange: (sortBy: string, sortOrder: DataTableSortOrder) => void;
  onFilterChange: (key: string, value: DataTableFilters[string]) => void;
}

export function DatasetsTable({
  datasets,
  total,
  page,
  limit,
  isLoading,
  sortBy,
  sortOrder,
  filters,
  onPageChange,
  onLimitChange,
  onSortChange,
  onFilterChange,
}: DatasetsTableProps) {
  const router = useRouter();

  return (
    <DataTable
      columns={columns}
      data={datasets}
      getRowId={(row) => row.id}
      total={total}
      page={page}
      limit={limit}
      sortBy={sortBy}
      sortOrder={sortOrder}
      defaultSortBy="name"
      defaultSortOrder="asc"
      filters={filters}
      isLoading={isLoading}
      onPageChange={onPageChange}
      onLimitChange={onLimitChange}
      onSortChange={onSortChange}
      onFilterChange={onFilterChange}
      onRowClick={(row) => router.push(`/datasets/${row.id}`)}
      emptyMessage="No datasets found"
    />
  );
}
