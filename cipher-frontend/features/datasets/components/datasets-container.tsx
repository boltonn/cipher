"use client";
import { useDatasets } from "@/features/datasets/api";
import { DatasetsTable } from "@/features/datasets/components/datasets-table";
import type {
  DatasetRequest,
  DatasetSortFieldType,
} from "@/features/datasets/types";
import { useEffect, useRef } from "react";

type DatasetsContainerProps = {
  filters: DatasetRequest;
  onSort: (field: DatasetSortFieldType) => void;
};

export function DatasetsContainer({ filters, onSort }: DatasetsContainerProps) {
  const observerTarget = useRef<HTMLDivElement>(null);

  // Using standard useDatasets (not suspense)
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useDatasets(filters);

  const allDatasets = data?.pages.flatMap((page) => page.data) ?? [];
  const totalResults = data?.pages[0]?.total ?? 0;

  useEffect(() => {
    const element = observerTarget.current;
    if (!element || !hasNextPage || isFetchingNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Guard: Only fetch if visible AND not already busy
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(element);
    return () => observer.disconnect();
    // Dependency on allDatasets.length ensures the observer refreshes when the list grows
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, allDatasets.length]);

  if (isLoading) {
    return (
      <div className="text-slate-500 font-mono text-xs py-10">
        Searching Datasets...
      </div>
    );
  }

  return (
    <DatasetsTable
      datasets={allDatasets}
      totalResults={totalResults}
      isLoadingMore={isFetchingNextPage}
      hasMore={hasNextPage}
      observerRef={observerTarget}
      sortBy={filters.sortBy}
      sortOrder={filters.sortOrder}
      onSort={onSort}
    />
  );
}
