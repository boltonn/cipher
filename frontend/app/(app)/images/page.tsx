"use client";

import { PageError, PageLoading } from "@/components/page-loading";
import { PageHeader } from "@/components/page-header";
import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { ImageSearchBar } from "@/features/images/components/image-search-bar";
import { ImagesContainerInfinite } from "@/features/images/components/images-container-infinite";
import { ImagesContainerPaginated } from "@/features/images/components/images-container-paginated";
import { useSearchController } from "@/features/images/hooks/use-search-controller";
import { PaginationModeType } from "@/types/common";
import { useQueryClient } from "@tanstack/react-query";
import { ImageIcon, Search, X } from "lucide-react";
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
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    currentPage,
    isSimilarityMode,
    queryLabel,
  } = useSearchController(paginationMode);

  const queryClient = useQueryClient();
  const retry = () => queryClient.invalidateQueries({ queryKey: ["images"] });

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
        value={
          isSimilarityMode || queryLabel
            ? `${totalAssets.toLocaleString()} Results`
            : `${totalAssets.toLocaleString()} images`
        }
        extra={
          isSimilarityMode && (
            <button
              type="button"
              onClick={actions.clearSearch}
              className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-widest text-primary bg-primary/10 border border-primary/20 rounded-full px-3 py-1.5 hover:bg-primary/20 transition-colors"
            >
              <ImageIcon size={12} />
              {queryLabel || "Similar to image"}
              <X size={10} />
            </button>
          )
        }
        actions={
          <PaginationModeToggle
            mode={paginationMode}
            onToggle={() => setPaginationMode((p) => (p === "infinite" ? "normal" : "infinite"))}
            accentClassName="hover:text-primary"
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
        {error && !data && !paginatedData ? (
          <PageError
            title="Couldn’t load images"
            body="The image index didn’t respond. This is usually temporary — try again."
            onRetry={retry}
          />
        ) : isPending && !data && !paginatedData ? (
          <PageLoading icon={Search} label="Searching images…" onRetry={retry} />
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
