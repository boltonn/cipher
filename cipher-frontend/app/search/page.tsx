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
    chunks,
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
    searchMode,
    groupByFile,
    filters,
    setFilters,
  } = useSearchController(paginationMode);

  const selectedChunk = useMemo(
    () => (selection?.chunkId ? chunks.find((chunk) => chunk.id === selection.chunkId) : undefined),
    [chunks, selection]
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
    <div className="relative mx-auto flex h-screen max-w-400 flex-col px-6 pb-6">
      <PageHeader
        eyebrow="Search"
        icon={<FileSearch size={10} className="text-indigo-400/50" />}
        value={query ? `${total.toLocaleString()} Result${total === 1 ? "" : "s"}` : "Documents & Emails"}
        actions={
          <PaginationModeToggle
            mode={paginationMode}
            onToggle={() => setPaginationMode((p) => (p === "infinite" ? "normal" : "infinite"))}
          />
        }
      />

      <div className="mt-2">
        <SearchToolbar
          isSearching={isFetching}
          searchMode={searchMode}
          groupByFile={groupByFile}
          onSearch={handleSearch}
          onSearchModeChange={handleSearchModeChange}
          onToggleGroupByFile={actions.toggleGroupByFile}
        />
      </div>

      <div className="mt-3">
        <SearchFiltersBar filters={filters} onFiltersChange={handleFiltersChange} />
      </div>

      <div className="relative z-10 mt-4 flex min-h-0 flex-1 gap-4">
        {!(previewExpanded && selection) && (
          <aside className="flex w-96 shrink-0 flex-col overflow-y-auto rounded-xl border border-white/10 bg-slate-900/40 shadow-xl">
            <ResultsList
              chunks={chunks}
              groupedResults={groupedResults}
              groupByFile={groupByFile}
              selection={selection}
              onSelectFile={(fileId) => setSelection({ fileId })}
              onSelectChunk={(fileId, chunkId) => setSelection({ fileId, chunkId })}
              searchMode={searchMode}
              query={query}
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

        <main className="flex-1 overflow-hidden rounded-xl border border-white/10 bg-slate-900/40 shadow-xl">
          <PreviewPane
            fileId={selection?.fileId ?? null}
            chunk={selectedChunk}
            query={query}
            isExpanded={previewExpanded}
            onToggleExpand={() => setPreviewExpanded((current) => !current)}
          />
        </main>
      </div>
    </div>
  );
}
