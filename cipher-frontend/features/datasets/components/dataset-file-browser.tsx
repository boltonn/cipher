"use client";

import { DataTable } from "@/components/data-table/data-table";
import type { DataTableColumn, DataTableSortOrder } from "@/components/data-table/types";
import { useDatasetFileBrowser } from "@/features/files/api";
import type { FileBrowserItem } from "@/features/files/types";
import { formatBytes } from "@/lib/utils";
import { ChevronRight, File as FileIcon, Folder, Home } from "lucide-react";
import { useState } from "react";

interface DatasetFileBrowserProps {
  datasetId: string;
}

type SortField = "filename" | "dateCreated" | "dateLastUpdated";

/**
 * Folder-scoped file browser for a dataset. Rows are fetched a page at a
 * time from `/datasets/{id}/browse` (server-capped at 100/page), so this
 * stays responsive even for a dataset with tens of thousands of files --
 * navigating into a folder is just a new paginated query for that path.
 */
export function DatasetFileBrowser({ datasetId }: DatasetFileBrowserProps) {
  // Start at the filesystem root ("/") so folders are browsable like a real
  // file explorer; omitting `path` entirely switches the backend into a
  // flat, folder-less dataset-wide listing instead.
  const [path, setPath] = useState("/");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [sortBy, setSortBy] = useState<SortField>("filename");
  const [sortOrder, setSortOrder] = useState<DataTableSortOrder>("asc");

  const { data, isLoading } = useDatasetFileBrowser(datasetId, {
    path,
    page,
    limit,
    sortBy,
    sortOrder,
  });

  const navigateTo = (newPath: string) => {
    setPath(newPath);
    setPage(1);
  };

  const handleRowClick = (row: FileBrowserItem) => {
    if (row.type === "directory" && row.path) navigateTo(row.path);
  };

  const crumbs = path === "/" ? [] : path.split("/").filter(Boolean);

  const columns: DataTableColumn<FileBrowserItem>[] = [
    {
      key: "filename",
      header: "Name",
      type: "text",
      sortable: true,
      render: (row) => (
        <span className="flex items-center gap-2 min-w-0">
          {row.type === "directory" ? (
            <Folder size={14} className="text-indigo-400 shrink-0" />
          ) : (
            <FileIcon size={14} className="text-slate-500 shrink-0" />
          )}
          <span className="truncate">{row.filename}</span>
        </span>
      ),
    },
    {
      key: "filetype",
      header: "Type",
      type: "text",
      width: "100px",
      render: (row) => (row.type === "directory" ? "—" : row.filetype.toUpperCase()),
    },
    {
      key: "size",
      header: "Size",
      type: "number",
      align: "right",
      width: "120px",
      render: (row) => (row.type === "directory" ? "—" : formatBytes(row.size)),
    },
    {
      key: "dateCreated",
      header: "Loaded",
      type: "date",
      sortable: true,
      width: "140px",
      render: (row) => (row.dateCreated ? new Date(row.dateCreated).toLocaleDateString() : "—"),
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1 text-xs">
        <button
          type="button"
          onClick={() => navigateTo("/")}
          className={path === "/" ? "text-slate-300 font-medium" : "text-slate-500 hover:text-indigo-400"}
          aria-label="Dataset root"
        >
          <Home size={12} />
        </button>
        {crumbs.map((segment, i) => {
          const segmentPath = "/" + crumbs.slice(0, i + 1).join("/");
          const isLast = i === crumbs.length - 1;
          return (
            <span key={segmentPath} className="flex items-center gap-1">
              <ChevronRight size={12} className="text-slate-700" />
              <button
                type="button"
                onClick={() => navigateTo(segmentPath)}
                disabled={isLast}
                className={isLast ? "text-slate-300 font-medium" : "text-slate-500 hover:text-indigo-400"}
              >
                {segment}
              </button>
            </span>
          );
        })}
      </div>

      <DataTable
        columns={columns}
        data={data?.data ?? []}
        getRowId={(row) => `${row.type}:${row.path ?? row.filename}`}
        total={data?.total ?? 0}
        page={page}
        limit={limit}
        sortBy={sortBy}
        sortOrder={sortOrder}
        filters={{}}
        isLoading={isLoading}
        onPageChange={setPage}
        onLimitChange={(newLimit) => {
          setLimit(newLimit);
          setPage(1);
        }}
        onSortChange={(field, order) => {
          setSortBy(field as SortField);
          setSortOrder(order);
        }}
        onFilterChange={() => {}}
        onRowClick={handleRowClick}
        emptyMessage="No files in this folder"
      />
    </div>
  );
}
