"use client";

import { PageHeader } from "@/components/page-header";
import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { ImageSearchBar } from "@/features/images/components/image-search-bar";
import { ImagesContainerInfinite } from "@/features/images/components/images-container-infinite";
import { ImagesContainerPaginated } from "@/features/images/components/images-container-paginated";
import { useSearchController } from "@/features/images/hooks/use-search-controller";
import { PaginationModeType } from "@/types/common";
import { Loader2, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

function ImageSearchPageInner() {
  const [paginationMode, setPaginationMode] =
    useState<PaginationModeType>("infinite");
  const [isFiltersOpen, setIsFiltersOpen] = useState(false);

  const searchParams = useSearchParams();
  const hasProcessedParams = useRef(false);

  const {
    data,
    paginatedData,
    filters,
    setFilters,
    actions,
    isPending,
    isFetching,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    currentPage,
    isSimilarityMode,
  } = useSearchController(paginationMode);

  const totalAssets = data?.pages[0]?.total ?? paginatedData?.total ?? 0;

  useEffect(() => {
    if (hasProcessedParams.current) return;
    const id = searchParams.get("id");
    if (id) {
      actions.handleSimilar(id);
      window.history.replaceState(null, "", "/images");
      hasProcessedParams.current = true;
    }
  }, [searchParams, actions]);

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20">
      <PageHeader
        eyebrow="Images"
        value={`${totalAssets.toLocaleString()} Results`}
        actions={
          <PaginationModeToggle
            mode={paginationMode}
            onToggle={() => setPaginationMode((p) => (p === "infinite" ? "normal" : "infinite"))}
            accentClassName="hover:text-indigo-400"
          />
        }
      />

      {/* Search bar, with filters tucked below its filter icon */}
      <div className="mt-4">
        <ImageSearchBar
          onSearch={actions.handleText}
          onImageUpload={actions.handleUpload}
          isSearching={isPending}
          filters={filters}
          setFilters={setFilters}
          isSimilarityMode={isSimilarityMode}
          isFiltersOpen={isFiltersOpen}
          onToggleFilters={() => setIsFiltersOpen((v) => !v)}
        />
      </div>

      {/* Results */}
      <main className="mt-6">
        {isPending && !data && !paginatedData ? (
          <div className="flex flex-col items-center justify-center py-48 text-slate-500">
            <div className="relative flex items-center justify-center mb-6">
              <Loader2 className="h-12 w-12 animate-spin text-indigo-500/20" />
              <Search className="h-5 w-5 absolute text-indigo-500 animate-pulse" />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-[0.5em] text-indigo-400/50 italic">
              Searching images...
            </p>
          </div>
        ) : paginationMode === "infinite" ? (
          <ImagesContainerInfinite
            data={data}
            onSimilar={actions.handleSimilar}
            fetchNextPage={fetchNextPage}
            hasNextPage={hasNextPage}
            isFetchingNextPage={isFetchingNextPage}
            isFullWidth
            onToggleFilters={() => setIsFiltersOpen(true)}
          />
        ) : (
          <ImagesContainerPaginated
            data={paginatedData}
            onSimilar={actions.handleSimilar}
            currentPage={currentPage}
            onPageChange={actions.handlePageChange}
            isLoading={isFetching}
            itemsPerPage={filters.limit || 20}
            isFullWidth
            onToggleFilters={() => setIsFiltersOpen(true)}
          />
        )}
      </main>
    </div>
  );
}

export default function ImageSearchPage() {
  return (
    <Suspense>
      <ImageSearchPageInner />
    </Suspense>
  );
}
