"use client";

import { PreviewPane } from "@/features/search/components/preview-pane";
import { ResultsList } from "@/features/search/components/results-list";
import { SearchToolbar } from "@/features/search/components/search-toolbar";
import { useSearchController } from "@/features/search/hooks/use-search-controller";
import type { SearchSelection } from "@/features/search/types";
import { useMemo, useState } from "react";

export default function SearchPage() {
  const [selection, setSelection] = useState<SearchSelection | null>(null);

  const {
    chunks,
    groupedResults,
    isPending,
    isFetching,
    hasMore,
    loadMore,
    actions,
    query,
    searchMode,
    groupByFile,
  } = useSearchController();

  const selectedChunk = useMemo(
    () => (selection?.chunkId ? chunks.find((chunk) => chunk.id === selection.chunkId) : undefined),
    [chunks, selection]
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-card text-slate-200">
      <header className="z-20 flex h-14 shrink-0 items-center gap-4 border-b border-slate-800 bg-[#161b22] px-6 shadow-lg">
        <span className="hidden shrink-0 text-lg font-bold tracking-tight md:block">Search</span>
        <SearchToolbar
          isSearching={isFetching}
          searchMode={searchMode}
          groupByFile={groupByFile}
          onSearch={actions.handleSearch}
          onSearchModeChange={actions.handleSearchModeChange}
          onToggleGroupByFile={actions.toggleGroupByFile}
        />
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="flex w-96 flex-col overflow-y-auto border-r border-slate-800 bg-card">
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
            hasMore={hasMore}
            isFetching={isFetching}
            onLoadMore={loadMore}
          />
        </aside>

        <main className="flex-1 overflow-hidden">
          <PreviewPane fileId={selection?.fileId ?? null} chunk={selectedChunk} query={query} />
        </main>
      </div>
    </div>
  );
}
