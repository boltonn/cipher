"use client";

import { DataTable } from "@/components/data-table/data-table";
import type {
  DataTableColumn,
  DataTableSortOrder,
} from "@/components/data-table/types";
import { useDatasetFileBrowser } from "@/features/files/api";
import { FileRowActions } from "@/features/files/components/file-row-actions";
import { FileTreeBrowser } from "@/features/files/components/file-tree-browser";
import { FileViewerDialog } from "@/features/files/components/file-viewer-dialog";
import type { FileBrowserItem } from "@/features/files/types";
import { cn, formatBytes } from "@/lib/utils";
import { File as FileIcon, Folder, FolderTree, Table2 } from "lucide-react";
import { useState } from "react";

interface DatasetFileBrowserProps {
  datasetId: string;
  /** Cross-filter from the dataset page's "By Filetype" breakdown. */
  filetype?: string;
  /** Cross-filter from the dataset page's "By Filetype Group" breakdown. */
  filetypeGroup?: string;
}

type SortField = "filename" | "dateCreated" | "dateLastUpdated";
type ViewMode = "tree" | "table";

/**
 * Dataset file browser with two view modes. Rows are fetched a page at a
 * time from `/datasets/{id}/browse` (server-capped at 100/page), so this
 * stays responsive even for a dataset with tens of thousands of files:
 * - Tree: folder-scoped, breadcrumb navigation (the classic file-explorer feel).
 * - Table: flat listing across the whole dataset, ignoring folder structure --
 *   the natural mode when filtering by filetype, since "all PDFs" is a
 *   cross-folder query by nature.
 */
export function DatasetFileBrowser({
  datasetId,
  filetype,
  filetypeGroup,
}: DatasetFileBrowserProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("tree");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [sortBy, setSortBy] = useState<SortField>("filename");
  const [sortOrder, setSortOrder] = useState<DataTableSortOrder>("asc");
  const [selectedFile, setSelectedFile] = useState<FileBrowserItem | null>(
    null
  );

  // Selecting a filetype is inherently a cross-folder query -- nudge into
  // table view when a filter newly becomes active, without locking the user
  // out of switching back to tree view manually. Adjusted during render
  // (rather than an effect) by tracking the previous filter key.
  const filterKey = `${filetype ?? ""}:${filetypeGroup ?? ""}`;
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    if (filetype || filetypeGroup) {
      setViewMode("table");
      setPage(1);
    }
  }

  // Table mode is the only mode driven by this flat query -- Tree mode fetches
  // its own per-folder data internally, so the query is disabled there.
  const { data, isLoading } = useDatasetFileBrowser(
    viewMode === "table" ? datasetId : undefined,
    {
      path: undefined,
      page,
      limit,
      sortBy,
      sortOrder,
      filetype,
      filetypeGroup,
    }
  );

  const fileRows = data?.data ?? [];
  const selectedIndex = selectedFile
    ? fileRows.findIndex((row) => row.id === selectedFile.id)
    : -1;

  // When the dialog's next/prev reaches the edge of the current page, cross
  // into the next/previous page instead of just disabling the arrow. Since
  // the new page's rows arrive asynchronously, remember which edge to select
  // once `data.page` catches up to the page we just requested (adjusted
  // during render, not an effect).
  const [pendingSelect, setPendingSelect] = useState<"first" | "last" | null>(null);
  if (pendingSelect && data?.page === page && fileRows.length > 0) {
    setSelectedFile(pendingSelect === "first" ? fileRows[0] : fileRows[fileRows.length - 1]);
    setPendingSelect(null);
  }

  const handleNext = () => {
    if (selectedIndex >= 0 && selectedIndex < fileRows.length - 1) {
      setSelectedFile(fileRows[selectedIndex + 1]);
    } else if (data?.hasMore) {
      setPendingSelect("first");
      setPage(page + 1);
    }
  };

  const handlePrev = () => {
    if (selectedIndex > 0) {
      setSelectedFile(fileRows[selectedIndex - 1]);
    } else if (page > 1) {
      setPendingSelect("last");
      setPage(page - 1);
    }
  };

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
      render: (row) =>
        row.type === "directory" ? "—" : row.filetype.toUpperCase(),
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
      render: (row) =>
        row.dateCreated ? new Date(row.dateCreated).toLocaleDateString() : "—",
    },
    {
      key: "actions",
      header: "",
      type: "text",
      width: "110px",
      render: (row) => <FileRowActions file={row} onView={setSelectedFile} />,
    },
  ];

  const switchViewMode = (mode: ViewMode) => {
    setViewMode(mode);
    setPage(1);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-slate-500">
          {viewMode === "tree" ? "Folder hierarchy" : "All files in dataset"}
        </span>

        <div className="flex items-center gap-0.5 rounded-lg border border-white/5 bg-slate-900/40 p-0.5">
          <button
            type="button"
            onClick={() => switchViewMode("tree")}
            aria-label="Tree view"
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-widest transition-colors",
              viewMode === "tree"
                ? "bg-indigo-600 text-white"
                : "text-slate-500 hover:text-indigo-400"
            )}
          >
            <FolderTree size={12} /> Tree
          </button>
          <button
            type="button"
            onClick={() => switchViewMode("table")}
            aria-label="Table view"
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-widest transition-colors",
              viewMode === "table"
                ? "bg-indigo-600 text-white"
                : "text-slate-500 hover:text-indigo-400"
            )}
          >
            <Table2 size={12} /> Table
          </button>
        </div>
      </div>

      {viewMode === "tree" ? (
        <FileTreeBrowser
          datasetId={datasetId}
          filetype={filetype}
          filetypeGroup={filetypeGroup}
          onView={setSelectedFile}
        />
      ) : (
        <DataTable
          columns={columns}
          data={fileRows}
          getRowId={(row) => row.id ?? row.path ?? row.filename}
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
          emptyMessage="No files match this filter"
        />
      )}

      <FileViewerDialog
        file={selectedFile}
        isOpen={!!selectedFile}
        onOpenChange={(open) => !open && setSelectedFile(null)}
        onNext={handleNext}
        onPrev={handlePrev}
        hasNext={selectedIndex >= 0 && (selectedIndex < fileRows.length - 1 || !!data?.hasMore)}
        hasPrev={selectedIndex >= 0 && (selectedIndex > 0 || page > 1)}
      />
    </div>
  );
}
