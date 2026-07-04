"use client";

import { PaginationModeToggle } from "@/components/pagination-mode-toggle";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { FaceUploadSearchBar } from "@/features/faces/components/face-upload-search-bar";
import { FacesContainerInfinite } from "@/features/faces/components/faces-container-infinite";
import { FacesContainerPaginated } from "@/features/faces/components/faces-container-paginated";
import { useSearchController } from "@/features/faces/hooks/use-search-controller";
import { PaginationModeType } from "@/types/common";
import { Loader2, ScanFace, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

function FacesPageInner() {
  const [paginationMode, setPaginationMode] = useState<PaginationModeType>("infinite");
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
    queryLabel,
    isSimilarityMode,
  } = useSearchController(paginationMode);

  const totalFaces = data?.pages[0]?.total ?? paginatedData?.total ?? 0;

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
      {/* Utility Header */}
      <div className="sticky top-0 z-30 flex items-center justify-between pt-6 pb-2 bg-[#050507]/90">
        <div className="flex items-center gap-4">
          <SidebarTrigger className="h-9 w-9 text-slate-400 hover:text-annotation" />

          <div className="flex flex-col">
            <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">
              Faces
            </span>
            <span className="text-xs font-mono text-annotation/80">
              {totalFaces.toLocaleString()} Results
            </span>
          </div>

          {isSimilarityMode && (
            <button
              type="button"
              onClick={actions.clearSimilar}
              className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-widest text-annotation bg-annotation/10 border border-annotation/20 rounded-full px-3 py-1.5 hover:bg-annotation/20 transition-colors"
            >
              <ScanFace size={12} />
              {queryLabel || "Similar to face"}
              <X size={10} />
            </button>
          )}
        </div>

        <PaginationModeToggle
          mode={paginationMode}
          onToggle={() => setPaginationMode((p) => (p === "infinite" ? "normal" : "infinite"))}
          accentClassName="hover:text-annotation"
        />
      </div>

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
        {isPending && !data && !paginatedData ? (
          <div className="flex flex-col items-center justify-center py-48 text-slate-500">
            <div className="relative flex items-center justify-center mb-6">
              <Loader2 className="h-12 w-12 animate-spin text-annotation/20" />
              <ScanFace className="h-5 w-5 absolute text-annotation animate-pulse" />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-[0.5em] text-annotation/50 italic">
              Loading faces...
            </p>
          </div>
        ) : paginationMode === "infinite" ? (
          <FacesContainerInfinite
            data={data}
            onSimilar={actions.handleSimilar}
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
            currentPage={currentPage}
            onPageChange={actions.handlePageChange}
            isLoading={isFetching}
            itemsPerPage={filters.limit || 24}
            isFullWidth
            onToggleFilters={() => setIsFiltersOpen(true)}
          />
        )}
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
