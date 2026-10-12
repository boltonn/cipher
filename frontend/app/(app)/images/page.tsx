"use client";

import { PageError, PageLoading } from "@/components/page-loading";
import { PageHeader } from "@/components/page-header";
import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { ImageAnnotateBar } from "@/features/images/components/image-annotate-bar";
import { ImageSelectionBar } from "@/features/images/components/image-selection-bar";
import { ImageSearchBar } from "@/features/images/components/image-search-bar";
import { ImagesContainerInfinite } from "@/features/images/components/images-container-infinite";
import { ImagesContainerPaginated } from "@/features/images/components/images-container-paginated";
import { useImageAnnotation } from "@/features/images/hooks/use-image-annotation";
import { useSearchController } from "@/features/images/hooks/use-search-controller";
import { tagFilterEntries } from "@/features/tags/tag-filter";
import { Button } from "@/components/ui/button";
import { useGridSelection } from "@/hooks/use-grid-selection";
import { PaginationModeType } from "@/types/common";
import { useQueryClient } from "@tanstack/react-query";
import { ImageIcon, PenLine, Search, X } from "lucide-react";
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
    textQuery,
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
  const tagFilters = useMemo(() => tagFilterEntries(filters), [filters]);
  const reviewTags = useMemo(() => tagFilters.map((entry) => entry.tag), [tagFilters]);
  const singleTagFilter = tagFilters.length === 1 ? tagFilters[0] : undefined;

  // Annotate mode: card clicks stage positive / negative labels for one tag, saved in one go.
  const annotation = useImageAnnotation();
  const [isAnnotating, setIsAnnotating] = useState(false);
  const startAnnotating = () => {
    const suggested = singleTagFilter?.tag ?? textQuery?.trim();
    if (!annotation.tag && suggested) annotation.setTag(suggested);
    selection.clear();
    setIsAnnotating(true);
  };

  const knownTags = useMemo(
    () =>
      [
        ...new Set([
          ...reviewTags,
          ...loadedImages.flatMap((image) => image.tags),
        ]),
      ].sort(),
    [reviewTags, loadedImages]
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
          <div className="flex items-center gap-2">
            <DatasetSelect
              datasetIds={filters.datasets ?? []}
              placeholder="All datasets"
              onChange={(datasetIds) =>
                setFilters((prev) => ({ ...prev, datasets: datasetIds.length ? datasetIds : undefined }))
              }
            />
            <Button
              size="sm"
              variant={isAnnotating ? "default" : "outline"}
              className="h-8 gap-1.5 text-xs"
              onClick={isAnnotating ? undefined : startAnnotating}
              aria-pressed={isAnnotating}
            >
              <PenLine size={13} />
              {isAnnotating ? "Annotating" : "Annotate"}
            </Button>
            <PaginationModeToggle
              mode={paginationMode}
              onToggle={() => setPaginationMode((p) => (p === "infinite" ? "normal" : "infinite"))}
              accentClassName="hover:text-primary"
            />
          </div>
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
            selection={isAnnotating ? undefined : selection}
            annotation={isAnnotating && annotation.tag ? annotation : undefined}
            reviewTags={reviewTags}
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
            selection={isAnnotating ? undefined : selection}
            annotation={isAnnotating && annotation.tag ? annotation : undefined}
            reviewTags={reviewTags}
            currentPage={currentPage}
            onPageChange={actions.handlePageChange}
            isLoading={isFetching}
            itemsPerPage={filters.limit || 20}
            isFullWidth
            onToggleFilters={() => setIsFiltersOpen(true)}
          />
        )}
        {isAnnotating ? (
          <ImageAnnotateBar
            annotation={annotation}
            loadedImages={loadedImages}
            onExit={() => setIsAnnotating(false)}
          />
        ) : (
          <ImageSelectionBar
            selection={selection}
            loadedIds={loadedIds}
            reviewTag={singleTagFilter?.tag}
            reviewTagState={singleTagFilter?.state}
            knownTags={knownTags}
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
