"use client";

import { PageError, PageLoading } from "@/components/page-loading";
import { PageHeader } from "@/components/page-header";
import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { FaceSelectionBar } from "@/features/faces/components/face-selection-bar";
import { FaceUploadSearchBar } from "@/features/faces/components/face-upload-search-bar";
import { FacesContainerInfinite } from "@/features/faces/components/faces-container-infinite";
import { FacesContainerPaginated } from "@/features/faces/components/faces-container-paginated";
import { useGridSelection } from "@/hooks/use-grid-selection";
import { useSearchController } from "@/features/faces/hooks/use-search-controller";
import { PaginationModeType } from "@/types/common";
import { useQueryClient } from "@tanstack/react-query";
import { ScanFace, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";

function FacesPageInner() {
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
    queryLabel,
    isSimilarityMode,
  } = useSearchController(paginationMode);

  const queryClient = useQueryClient();
  const retry = () => queryClient.invalidateQueries({ queryKey: ["faces"] });

  const totalFaces = data?.pages[0]?.total ?? paginatedData?.total ?? 0;

  const selection = useGridSelection();
  const isRejectedView = !!filters.rejectedOnly;
  const [prevRejectedView, setPrevRejectedView] = useState(isRejectedView);
  if (isRejectedView !== prevRejectedView) {
    setPrevRejectedView(isRejectedView);
    selection.clear();
  }
  const loadedIds = useMemo(
    () =>
      paginationMode === "infinite"
        ? (data?.pages.flatMap((page) => page.data.map((face) => face.id)) ??
          [])
        : (paginatedData?.data.map((face) => face.id) ?? []),
    [paginationMode, data, paginatedData]
  );

  useEffect(() => {
    if (hasProcessedParams.current) return;
    const similar = searchParams.get("similar");
    if (similar) {
      actions.handleSimilar(similar);
      window.history.replaceState(null, "", "/faces");
      hasProcessedParams.current = true;
    }
  }, [searchParams, actions]);

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20">
      <PageHeader
        eyebrow="Faces"
        value={`${totalFaces.toLocaleString()} ${isRejectedView ? "rejected" : "faces"}`}
        accentClassName="text-annotation/80"
        sidebarAccentClassName="hover:text-annotation"
        extra={
          isSimilarityMode && (
            <button
              type="button"
              onClick={actions.clearSimilar}
              className="flex items-center gap-1.5 text-xs font-medium text-annotation bg-annotation/10 border border-annotation/20 rounded-full px-3 py-1.5 hover:bg-annotation/20 transition-colors"
            >
              <ScanFace size={12} />
              {queryLabel || "Similar to face"}
              <X size={10} />
            </button>
          )
        }
        actions={
          <PaginationModeToggle
            mode={paginationMode}
            onToggle={() =>
              setPaginationMode((p) =>
                p === "infinite" ? "normal" : "infinite"
              )
            }
            accentClassName="hover:text-annotation"
          />
        }
      />

      {/* Upload search bar, with filters tucked behind its filter icon */}
      <div className="mt-4">
        <FaceUploadSearchBar
          onEmbeddingSelected={actions.handleEmbeddingSelected}
          isSearching={isPending}
          uploadedLabel={queryLabel}
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
            title="Couldn’t load faces"
            body="The face index didn’t respond. This is usually temporary — try again."
            onRetry={retry}
          />
        ) : isPending && !data && !paginatedData ? (
          <PageLoading
            icon={ScanFace}
            label="Loading faces…"
            accent="annotation"
            onRetry={retry}
          />
        ) : paginationMode === "infinite" ? (
          <FacesContainerInfinite
            data={data}
            onSimilar={actions.handleSimilar}
            selection={selection}
            fetchNextPage={fetchNextPage}
            hasNextPage={hasNextPage}
            isFetchingNextPage={isFetchingNextPage}
            isFullWidth
            onToggleFilters={() => setIsFiltersOpen(true)}
          />
        ) : (
          <FacesContainerPaginated
            data={paginatedData}
            onSimilar={actions.handleSimilar}
            selection={selection}
            currentPage={currentPage}
            onPageChange={actions.handlePageChange}
            isLoading={isFetching}
            itemsPerPage={filters.limit || 24}
            isFullWidth
            onToggleFilters={() => setIsFiltersOpen(true)}
          />
        )}
        <FaceSelectionBar
          selection={selection}
          loadedIds={loadedIds}
          isRejectedView={isRejectedView}
        />
      </main>
    </div>
  );
}

export default function FacesPage() {
  return (
    <Suspense>
      <FacesPageInner />
    </Suspense>
  );
}
