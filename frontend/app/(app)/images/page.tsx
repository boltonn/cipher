"use client";

import { PageError, PageLoading } from "@/components/page-loading";
import { PageHeader } from "@/components/page-header";
import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { ImageSelectionBar } from "@/features/images/components/image-selection-bar";
import { ImageSearchBar } from "@/features/images/components/image-search-bar";
import { ImagesContainerInfinite } from "@/features/images/components/images-container-infinite";
import { ImagesContainerPaginated } from "@/features/images/components/images-container-paginated";
import { useSearchController } from "@/features/images/hooks/use-search-controller";
import { useGridSelection } from "@/hooks/use-grid-selection";
import { PaginationModeType } from "@/types/common";
import { useQueryClient } from "@tanstack/react-query";
import { ImageIcon, Search, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";

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

  // A selection only makes sense for the grid it was made in: drop it when the
  // filters or the search change, so a bulk action never hits images out of view.
  const selection = useGridSelection();
  const [selectionScope, setSelectionScope] = useState({ filters, queryLabel });
  if (
    selectionScope.filters !== filters ||
    selectionScope.queryLabel !== queryLabel
  ) {
    setSelectionScope({ filters, queryLabel });
    selection.clear();
  }
  const loadedImages = useMemo(
    () =>
      paginationMode === "infinite"
        ? (data?.pages.flatMap((page) => page.data) ?? [])
        : (paginatedData?.data ?? []),
    [paginationMode, data, paginatedData]
  );
  const loadedIds = useMemo(
    () => [...new Set(loadedImages.map((image) => image.id))],
    [loadedImages]
  );
  const knownTags = useMemo(
    () =>
      [
        ...new Set([
          ...(filters.tags ?? []),
          ...loadedImages.flatMap((image) => image.tags),
        ]),
      ].sort(),
    [filters.tags, loadedImages]
  );

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
            ? `${totalAssets.toLocaleString()} results`
            : `${totalAssets.toLocaleString()} images`
        }
        extra={
          isSimilarityMode && (
            <button
              type="button"
              onClick={actions.clearSearch}
              className="flex items-center gap-1.5 text-xs font-medium text-primary bg-primary/10 border border-primary/20 rounded-full px-3 py-1.5 hover:bg-primary/20 transition-colors"
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
            selection={selection}
            reviewTags={filters.tags}
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
            selection={selection}
            reviewTags={filters.tags}
            currentPage={currentPage}
            onPageChange={actions.handlePageChange}
            isLoading={isFetching}
            itemsPerPage={filters.limit || 20}
            isFullWidth
            onToggleFilters={() => setIsFiltersOpen(true)}
          />
        )}
        <ImageSelectionBar
          selection={selection}
          loadedIds={loadedIds}
          reviewTag={filters.tags?.length === 1 ? filters.tags[0] : undefined}
          reviewTagState={filters.tagState}
          knownTags={knownTags}
        />
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
