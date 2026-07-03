"use client";

import { Button } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { ImageFilterSidebar } from "@/features/images/components/image-filter-sidebar";
import { ImageSearchBar } from "@/features/images/components/image-search-bar";
import { ImagesContainerInfinite } from "@/features/images/components/images-container-infinite";
import { ImagesContainerPaginated } from "@/features/images/components/images-container-paginated";
import { useSearchController } from "@/features/images/hooks/use-search-controller";
import { cn } from "@/lib/utils";
import { PaginationModeType } from "@/types/common";
import {
  Infinity as InfinityIcon,
  Loader2,
  Search,
  SlidersHorizontal,
  Zap,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

function ImageSearchPageInner() {
  const [paginationMode, setPaginationMode] =
    useState<PaginationModeType>("infinite");
  const [isMinimized, setIsMinimized] = useState(false);

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
    fetchPreviousPage,
    hasNextPage,
    hasPreviousPage,
    isFetchingNextPage,
    isFetchingPreviousPage,
    currentPage,
  } = useSearchController(paginationMode);

  const totalAssets = data?.pages[0]?.total ?? paginatedData?.total ?? 0;

  const hasActiveFilters = !!(
    filters.dateFrom ||
    filters.dateTo ||
    (filters.datasets && filters.datasets.length > 0) ||
    (filters.tags && filters.tags.length > 0)
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "b") {
        e.preventDefault();
        setIsMinimized((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

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
      {/* Utility Header */}
      <div
        className={`sticky top-0 z-30 flex items-center justify-between pt-6 pb-2 ${isMinimized ? "bg-[#050507]/90" : "bg-transparent"} `}
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center p-1 rounded-lg bg-slate-900/50 border border-white/5 gap-1">
            <SidebarTrigger className="h-8 w-8 text-slate-400 hover:text-indigo-400" />

            <div
              className={cn(
                "flex items-center overflow-hidden transition-all duration-500 ease-in-out",
                isMinimized ? "w-24 opacity-100 ml-1" : "w-0 opacity-0 ml-0"
              )}
            >
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsMinimized(false)}
                className="h-8 gap-2 text-[10px] font-bold uppercase tracking-widest text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 px-2"
              >
                <SlidersHorizontal
                  size={14}
                  className={cn(hasActiveFilters && "animate-pulse")}
                />
                Filters
              </Button>
            </div>
          </div>

          <div className="flex flex-col">
            <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">
              Images
            </span>
            <span className="text-xs font-mono text-indigo-400/80">
              {totalAssets.toLocaleString()} Results
            </span>
          </div>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            setPaginationMode((p) => (p === "infinite" ? "normal" : "infinite"))
          }
          className="border-white/5 bg-slate-900/40 text-slate-400 hover:text-indigo-400 uppercase text-[10px] font-bold tracking-widest gap-2 h-9"
        >
          {paginationMode === "infinite" ? (
            <InfinityIcon size={14} />
          ) : (
            <Zap size={14} />
          )}
          {paginationMode} Mode
        </Button>
      </div>

      {/* Sticky Search Bar */}
      <div className="py-4 backdrop-blur-md">
        <ImageSearchBar
          onSearch={actions.handleText}
          onImageUpload={actions.handleUpload}
          isSearching={isPending}
        />
      </div>

      {/* Main Layout Content */}
      <div className="flex flex-col lg:flex-row mt-4 items-start gap-0">
        <aside
          className={cn(
            "shrink-0 transition-all duration-500 ease-in-out self-start",
            "sticky top-24 z-20",
            isMinimized
              ? "w-0 opacity-0 hidden lg:block"
              : "w-80 opacity-100 lg:pr-8"
          )}
        >
          <div className="w-72">
            <ImageFilterSidebar
              params={filters}
              setParams={setFilters}
              isMinimized={isMinimized}
              setIsMinimized={setIsMinimized}
            />
          </div>
        </aside>

        <main className="flex-1 min-w-0">
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
              isFullWidth={isMinimized}
              onToggleFilters={() => setIsMinimized(false)}
            />
          ) : (
            <ImagesContainerPaginated
              data={paginatedData}
              onSimilar={actions.handleSimilar}
              currentPage={currentPage}
              onPageChange={actions.handlePageChange}
              isLoading={isFetching}
              itemsPerPage={filters.limit || 20}
              isFullWidth={isMinimized}
              onToggleFilters={() => setIsMinimized(false)}
            />
          )}
        </main>
      </div>
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
