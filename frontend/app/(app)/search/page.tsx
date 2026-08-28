"use client";

import { PageHeader } from "@/components/page-header";
import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { PreviewPane } from "@/features/search/components/preview-pane";
import { ResultsList } from "@/features/search/components/results-list";
import { SearchFiltersBar } from "@/features/search/components/search-filters-bar";
import { SearchToolbar } from "@/features/search/components/search-toolbar";
import { useSearchController } from "@/features/search/hooks/use-search-controller";
import type { SearchFilters, SearchMode, SearchSelection } from "@/features/search/types";
import type { PaginationModeType } from "@/types/common";
import { FileSearch } from "lucide-react";
import { useMemo, useState } from "react";

export default function SearchPage() {
  const [selection, setSelection] = useState<SearchSelection | null>(null);
  const [paginationMode, setPaginationMode] = useState<PaginationModeType>("infinite");
  const [previewExpanded, setPreviewExpanded] = useState(false);

  const {
    groupedResults,
    total,
    isPending,
    isFetching,
    hasMore,
    loadMore,
    currentPage,
    limit,
    actions,
    query,
    canSearch,
    searchMode,
    filters,
    setFilters,
  } = useSearchController(paginationMode);

  // The selected file's group carries both the selected chunk itself and
  // every match for that file, in reading order -- lets the preview pane
  // step through them without the results list needing an accordion.
  const selectedGroup = useMemo(
    () => (selection?.fileId ? groupedResults.find((group) => group.fileId === selection.fileId) : undefined),
    [groupedResults, selection]
  );
  const selectedChunk = useMemo(
    () => (selection?.chunkId ? selectedGroup?.chunks.find((chunk) => chunk.id === selection.chunkId) : undefined),
    [selectedGroup, selection]
  );

  // A new page/query/mode/filter set is a new result set -- a kept selection
  // would point at a file/chunk that's no longer loaded (or no longer
  // matches), leaving the preview silently stuck on stale content instead of
  // going back to the "select a result" placeholder.
  const handlePageChange = (page: number) => {
    setSelection(null);
    actions.handlePageChange(page);
  };

  const handleSearch = (newQuery: string, newMode?: SearchMode) => {
    setSelection(null);
    actions.handleSearch(newQuery, newMode);
  };

  const handleSearchModeChange = (newMode: SearchMode) => {
    setSelection(null);
    actions.handleSearchModeChange(newMode);
  };

  const handleFiltersChange = (next: SearchFilters) => {
    setSelection(null);
    setFilters(next);
  };

  return (
    <div className="relative mx-auto flex h-full w-full max-w-400 flex-col px-6 pb-6">
      <PageHeader
        eyebrow="Search"
        icon={<FileSearch size={10} className="text-primary/50" />}
        value={canSearch && !isPending ? `${total.toLocaleString()} Result${total === 1 ? "" : "s"}` : "Documents & Emails"}
        actions={
          <PaginationModeToggle
            mode={paginationMode}
            onToggle={() => setPaginationMode((p) => (p === "infinite" ? "normal" : "infinite"))}
          />
        }
      />

      <div className="mt-4 shrink-0 space-y-2">
        <SearchToolbar
          isSearching={isFetching}
          searchMode={searchMode}
          query={query}
          onSearch={handleSearch}
          onSearchModeChange={handleSearchModeChange}
        />
        <SearchFiltersBar filters={filters} onFiltersChange={handleFiltersChange} />
      </div>

      <div className="relative z-10 mt-3 flex min-h-0 flex-1 gap-4">
        {!(previewExpanded && selection) && (
          <aside className="flex w-96 shrink-0 flex-col overflow-y-auto rounded-xl border border-border bg-muted/40 shadow-xl">
            <ResultsList
              groupedResults={groupedResults}
              selection={selection}
              onSelectChunk={(fileId, chunkId) => setSelection({ fileId, chunkId })}
              searchMode={searchMode}
              query={query}
              canSearch={canSearch}
              isPending={isPending}
              paginationMode={paginationMode}
              hasMore={hasMore}
              isFetching={isFetching}
              onLoadMore={loadMore}
              currentPage={currentPage}
              total={total}
              limit={limit}
              onPageChange={handlePageChange}
            />
          </aside>
        )}

        <main className="flex-1 overflow-hidden rounded-xl border border-border bg-muted/40 shadow-xl">
          <PreviewPane
            // Remount on mode change so the chunk-highlight toggle re-seeds to the new mode's default.
            key={searchMode}
            fileId={selection?.fileId ?? null}
            chunk={selectedChunk}
            query={query}
            searchMode={searchMode}
            // Match navigation is a semantic/hybrid affordance -- BM25 hits are
            // literal keyword matches, not fuzzy ones worth stepping through
            // (see FileResultGroup for the matching list-badge rule).
            matches={searchMode !== "text" ? selectedGroup?.chunks : undefined}
            onSelectChunk={
              searchMode !== "text" && selection ? (chunkId) => setSelection({ fileId: selection.fileId, chunkId }) : undefined
            }
            isExpanded={previewExpanded}
            onToggleExpand={() => setPreviewExpanded((current) => !current)}
          />
        </main>
      </div>
    </div>
  );
}
