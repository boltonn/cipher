"use client";

import { Pagination } from "@/components/pagination";
import type { PaginationModeType } from "@/types/common";
import { Loader2 } from "lucide-react";
import type { GroupedFileResult, SearchMode, SearchSelection } from "../types";
import { FileResultGroup } from "./file-result-group";

interface ResultsListProps {
  groupedResults: GroupedFileResult[];
  selection: SearchSelection | null;
  onSelectChunk: (fileId: string, chunkId: string) => void;
  searchMode: SearchMode;
  query: string | null;
  /** False when semantic/hybrid mode has no typed query yet -- there's no match_all fallback for kNN. */
  canSearch: boolean;
  isPending: boolean;
  paginationMode: PaginationModeType;
  hasMore: boolean;
  isFetching: boolean;
  onLoadMore: () => void;
  currentPage: number;
  total: number;
  limit: number;
  onPageChange: (page: number) => void;
}

export function ResultsList({
  groupedResults,
  selection,
  onSelectChunk,
  searchMode,
  query,
  canSearch,
  isPending,
  paginationMode,
  hasMore,
  isFetching,
  onLoadMore,
  currentPage,
  total,
  limit,
  onPageChange,
}: ResultsListProps) {
  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Searching...
      </div>
    );
  }

  if (!canSearch) {
    return <p className="p-6 text-center text-xs italic text-muted-foreground">Type a query to search.</p>;
  }

  if (groupedResults.length === 0) {
    return <p className="p-6 text-center text-xs italic text-muted-foreground">No matches found.</p>;
  }

  return (
    <div>
      {groupedResults.map((group) => (
        <FileResultGroup
          key={group.fileId}
          group={group}
          isSelected={selection?.fileId === group.fileId}
          onSelect={(chunkId) => onSelectChunk(group.fileId, chunkId)}
          searchMode={searchMode}
          query={query}
        />
      ))}

      {paginationMode === "normal" ? (
        <Pagination
          currentPage={currentPage}
          totalItems={total}
          itemsPerPage={limit}
          onPageChange={onPageChange}
          isLoading={isFetching}
          className="flex-wrap gap-1 px-2 py-4"
        />
      ) : (
        hasMore && (
          <button
            type="button"
            disabled={isFetching}
            onClick={onLoadMore}
            className="flex w-full items-center justify-center gap-2 border-t border-border/50 py-3 text-xs italic text-muted-foreground transition-colors hover:bg-white/[0.03] hover:text-primary disabled:opacity-50"
          >
            {isFetching ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              `Load more (${groupedResults.length.toLocaleString()} of ${total.toLocaleString()})`
            )}
          </button>
        )
      )}
    </div>
  );
}
