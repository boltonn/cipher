"use client";

import { PageError, PageLoading } from "@/components/page-loading";
import { PageHeader } from "@/components/page-header";
import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { Button } from "@/components/ui/button";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { FaceSelectionBar } from "@/features/faces/components/face-selection-bar";
import { FaceUploadSearchBar } from "@/features/faces/components/face-upload-search-bar";
import { FacesContainerInfinite } from "@/features/faces/components/faces-container-infinite";
import { FacesContainerPaginated } from "@/features/faces/components/faces-container-paginated";
import { useGridSelection } from "@/hooks/use-grid-selection";
import {
  MAX_BULK_FACES,
  useSearchController,
} from "@/features/faces/hooks/use-search-controller";
import type { FacePublic } from "@/features/faces/types";
import { PaginationModeType } from "@/types/common";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Loader2, ScanFace, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

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
    fetchAllIds,
    similarId,
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
  // A new query or filter changes the result set, so an old selection would act on faces no longer shown.
  const resultSetKey = JSON.stringify({ similarId, queryLabel, filters });
  const [prevResultSetKey, setPrevResultSetKey] = useState(resultSetKey);
  if (resultSetKey !== prevResultSetKey) {
    setPrevResultSetKey(resultSetKey);
    selection.clear();
  }
  const loadedFaces = useMemo<FacePublic[]>(
    () =>
      paginationMode === "infinite"
        ? (data?.pages.flatMap((page) => page.data) ?? [])
        : (paginatedData?.data ?? []),
    [paginationMode, data, paginatedData]
  );
  const loadedIds = useMemo(
    () => loadedFaces.map((face) => face.id),
    [loadedFaces]
  );

  // Similarity results are bounded by minSimilarity, so "select all" can reach past the loaded pages.
  const selectAllCount = isSimilarityMode
    ? Math.min(totalFaces, MAX_BULK_FACES)
    : loadedIds.length;
  const [isSelectingAll, setIsSelectingAll] = useState(false);
  const handleSelectAll = async () => {
    if (selectAllCount <= loadedIds.length)
      return selection.selectAll(loadedIds);
    setIsSelectingAll(true);
    try {
      selection.selectAll(await fetchAllIds());
      if (totalFaces > MAX_BULK_FACES)
        toast.info(
          `Selected the top ${MAX_BULK_FACES.toLocaleString()} matches -- raise the minimum similarity to narrow the rest`
        );
    } catch {
      toast.error("Couldn't load every match to select");
    } finally {
      setIsSelectingAll(false);
    }
  };

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
          <div className="flex items-center gap-2">
            <DatasetSelect
              datasetIds={filters.datasets ?? []}
              placeholder="All datasets"
              onChange={(datasetIds) =>
                setFilters((prev) => ({
                  ...prev,
                  datasets: datasetIds.length ? datasetIds : undefined,
                }))
              }
            />
            <PaginationModeToggle
              mode={paginationMode}
              onToggle={() =>
                setPaginationMode((p) =>
                  p === "infinite" ? "normal" : "infinite"
                )
              }
              accentClassName="hover:text-annotation"
            />
          </div>
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
          trailing={
            isSimilarityMode &&
            totalFaces > 0 &&
            selection.selectedIds.size === 0 && (
              <Button
                variant="outline"
                onClick={handleSelectAll}
                disabled={isSelectingAll}
                className="h-10 shrink-0 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                {isSelectingAll ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <CheckCheck size={13} />
                )}
                Select all {selectAllCount.toLocaleString()}
              </Button>
            )
          }
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
          faces={loadedFaces}
          selectAllCount={selectAllCount}
          onSelectAll={handleSelectAll}
          isSelectingAll={isSelectingAll}
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
