"use client";

import {
  FileTree,
  FileTreeActions,
  FileTreeFile,
  FileTreeFolder,
  FileTreeIcon,
  FileTreeName,
} from "@/components/ai-elements/file-tree";
import { useDatasetFileBrowser } from "@/features/files/api";
import type { FileBrowserEntryType, FileBrowserItem } from "@/features/files/types";
import { FileArchive, File as FileIcon, Loader2, Mail } from "lucide-react";
import { useRef, useState } from "react";
import { FileRowActions } from "./file-row-actions";

interface FileTreeBrowserProps {
  datasetId: string;
  filetype?: string;
  filetypeGroup?: string;
  onView: (file: FileBrowserItem) => void;
}

const PAGE_SIZE = 100;

/**
 * Hierarchical file tree for a dataset, built on the vendored ai-elements
 * `FileTree` primitives. Each expanded folder fetches its own children on
 * demand via `useDatasetFileBrowser` -- collapsed folders never fetch, so
 * this stays cheap even for datasets with tens of thousands of files. An
 * unpacked archive or an email with attachments opens like a folder: its
 * children sit at its path.
 */
export function FileTreeBrowser({ datasetId, filetype, filetypeGroup, onView }: FileTreeBrowserProps) {
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [selectedPath, setSelectedPath] = useState<string>();
  const pathTypesRef = useRef(new Map<string, FileBrowserEntryType>());

  const handleSelect = (path: string) => {
    setSelectedPath(path);
    if (pathTypesRef.current.get(path) === "directory") {
      setExpandedPaths((prev) => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        return next;
      });
    }
  };

  const reportPathType = (path: string, type: FileBrowserEntryType) => {
    pathTypesRef.current.set(path, type);
  };

  return (
    <FileTree
      expanded={expandedPaths}
      onExpandedChange={setExpandedPaths}
      selectedPath={selectedPath}
      onSelect={handleSelect}
      className="max-h-160 overflow-y-auto"
    >
      <FileTreeLevel
        datasetId={datasetId}
        path="/"
        filetype={filetype}
        filetypeGroup={filetypeGroup}
        expandedPaths={expandedPaths}
        onView={onView}
        reportPathType={reportPathType}
      />
    </FileTree>
  );
}

interface FileTreeLevelProps {
  datasetId: string;
  path: string;
  filetype?: string;
  filetypeGroup?: string;
  expandedPaths: Set<string>;
  onView: (file: FileBrowserItem) => void;
  reportPathType: (path: string, type: FileBrowserEntryType) => void;
}

function FileTreeLevel({
  datasetId,
  path,
  filetype,
  filetypeGroup,
  expandedPaths,
  onView,
  reportPathType,
}: FileTreeLevelProps) {
  // The backend caps `limit` at 100/request, so "load more" pages forward
  // (page 1, 2, 3...) and accumulates rows locally, rather than growing
  // `limit` past what the server will accept.
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<FileBrowserItem[]>([]);
  const [loadedPage, setLoadedPage] = useState(0);

  // Reset accumulation if the filter changes under a level that stays
  // mounted (e.g. user re-applies a different filetype filter while this
  // folder is still expanded). Adjusted during render, not an effect.
  const filterKey = `${filetype ?? ""}:${filetypeGroup ?? ""}`;
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    setPage(1);
    setRows([]);
    setLoadedPage(0);
  }

  const { data, isPending, isFetching } = useDatasetFileBrowser(datasetId, {
    path,
    filetype,
    filetypeGroup,
    limit: PAGE_SIZE,
    page,
    sortBy: "filename",
    sortOrder: "asc",
  });

  if (data && data.page === page && data.page > loadedPage) {
    setRows((prev) => (data.page === 1 ? data.data : [...prev, ...data.data]));
    setLoadedPage(data.page);
  }

  if (isPending && rows.length === 0) {
    return (
      <div className="flex items-center gap-2 px-2 py-1 text-xs text-muted-foreground">
        <Loader2 size={12} className="animate-spin" /> Loading...
      </div>
    );
  }

  rows.forEach((row) => reportPathType(row.path ?? row.filename, row.memberCount ? "directory" : row.type));

  return (
    <>
      {rows.map((row) => {
        const rowPath = row.path ?? row.filename;
        if (row.type === "directory" || row.memberCount) {
          const isParentFile = row.type === "file";
          return (
            <FileTreeFolder
              key={rowPath}
              path={rowPath}
              name={
                isParentFile
                  ? `${row.filename} · ${row.memberCount?.toLocaleString()} ${row.filetypeGroup === "email" ? "attachments" : "members"}`
                  : row.filename
              }
              icon={
                isParentFile ? (
                  row.filetypeGroup === "email" ? (
                    <Mail className="size-4 text-primary" />
                  ) : (
                    <FileArchive className="size-4 text-primary" />
                  )
                ) : undefined
              }
              actions={
                isParentFile ? (
                  <FileTreeActions>
                    <FileRowActions file={row} onView={onView} />
                  </FileTreeActions>
                ) : undefined
              }
            >
              {expandedPaths.has(rowPath) && (
                <FileTreeLevel
                  datasetId={datasetId}
                  path={rowPath}
                  filetype={filetype}
                  filetypeGroup={filetypeGroup}
                  expandedPaths={expandedPaths}
                  onView={onView}
                  reportPathType={reportPathType}
                />
              )}
            </FileTreeFolder>
          );
        }
        return (
          <FileTreeFile key={rowPath} path={rowPath} name={row.filename}>
            <FileTreeIcon>
              <FileIcon className="size-4 text-muted-foreground" />
            </FileTreeIcon>
            <FileTreeName>{row.filename}</FileTreeName>
            <FileTreeActions>
              <FileRowActions file={row} onView={onView} />
            </FileTreeActions>
          </FileTreeFile>
        );
      })}
      {data?.hasMore && (
        <button
          type="button"
          disabled={isFetching}
          onClick={() => setPage((p) => p + 1)}
          className="flex w-full items-center gap-2 px-2 py-1 text-left text-xs italic text-muted-foreground hover:bg-muted/50 rounded disabled:opacity-50"
        >
          {isFetching ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            `Load ${Math.min(PAGE_SIZE, (data.total ?? 0) - rows.length)} more...`
          )}
        </button>
      )}
    </>
  );
}
