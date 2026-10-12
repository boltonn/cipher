"use client";

import { FilterChip } from "@/components/active-filters";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { PageHeader } from "@/components/page-header";
import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { PreviewPane } from "@/features/search/components/preview-pane";
import { ResultsList } from "@/features/search/components/results-list";
import { SearchFiltersBar } from "@/features/search/components/search-filters-bar";
import { SearchScopeSummary } from "@/features/search/components/search-scope-summary";
import { SearchToolbar } from "@/features/search/components/search-toolbar";
import { useSearchController } from "@/features/search/hooks/use-search-controller";
import type { SearchFilters, SearchMode, SearchSelection } from "@/features/search/types";
import type { PaginationModeType } from "@/types/common";
import { FileSearch, Waypoints } from "lucide-react";
import { Suspense, useMemo, useState } from "react";

function SearchPageInner() {
  const [selection, setSelection] = useState<SearchSelection | null>(null);
  const [paginationMode, setPaginationMode] = useState<PaginationModeType>("infinite");
  const [previewExpanded, setPreviewExpanded] = useState(false);

  const {
    groupedResults,
    total,
    totalIsExact,
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
    exactMatch,
    filters,
    setFilters,
    datasetIds,
    graphExpandLabel,
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
    <div className="relative mx-auto flex h-full w-full max-w-400 flex-col px-6 pb-6 pt-5">
      <PageHeader
        eyebrow="Search"
        icon={<FileSearch size={10} className="text-primary/50" />}
        value={
          canSearch && !isPending
            ? totalIsExact
              ? `${total.toLocaleString()} result${total === 1 ? "" : "s"}`
              : "Closest matches"
            : "Documents & emails"
        }
        actions={
          <>
            <DatasetSelect
              datasetIds={datasetIds}
              placeholder="All datasets"
              onChange={(ids) => {
                setSelection(null);
                actions.setDatasetIds(ids);
              }}
            />
            <PaginationModeToggle
            mode={paginationMode}
              onToggle={() => setPaginationMode((p) => (p === "infinite" ? "normal" : "infinite"))}
            />
          </>
        }
      />

      <div className="mt-4 shrink-0 space-y-2">
        <SearchToolbar
          isSearching={isFetching}
          searchMode={searchMode}
          exactMatch={exactMatch}
          onExactMatchChange={actions.setExactMatch}
          query={query}
          onSearch={handleSearch}
          onSearchModeChange={handleSearchModeChange}
        />
        <SearchFiltersBar datasetIds={datasetIds} filters={filters} onFiltersChange={handleFiltersChange} />
        {graphExpandLabel && (
          <FilterChip
            icon={<Waypoints />}
            label={`About ${graphExpandLabel}`}
            onRemove={() => {
              setSelection(null);
              actions.clearGraphExpand();
            }}
          />
        )}
        {canSearch && !isPending && (
          <SearchScopeSummary
            query={query}
            searchMode={searchMode}
            filters={filters}
            about={graphExpandLabel}
            total={totalIsExact ? total : null}
          />
        )}
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
              totalIsExact={totalIsExact}
              limit={limit}
              onPageChange={handlePageChange}
            />
          </aside>
        )}

        <main className="flex-1 overflow-hidden rounded-xl border border-border bg-muted/40 shadow-xl">
          <PreviewPane
            // Remount on mode / entity-filter change so the highlight + mention-review defaults re-seed.
            key={`${searchMode}:${filters.entityIds?.join(",") ?? ""}:${filters.mentionValues?.join(",") ?? ""}`}
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
            focusEntityIds={filters.entityIds}
            focusMentionValues={filters.mentionValues}
          />
        </main>
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchPageInner />
    </Suspense>
  );
}
