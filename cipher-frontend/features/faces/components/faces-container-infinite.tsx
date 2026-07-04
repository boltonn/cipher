"use client";

import { Button } from "@/components/ui/button";
import { VirtualizedGrid } from "@/components/virtualized-grid";
import { CreatePersonDialog } from "@/features/persons/components/create-person-dialog";
import { ColumnBreakpoint } from "@/hooks/use-responsive-columns";
import type { InfiniteData } from "@tanstack/react-query";
import { Loader2, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  FacePublic,
  FaceSimilarityResult,
  PaginatedFacesResponse,
  PaginatedFaceSimilarityResponse,
} from "../types";
import { FaceCard } from "./face-card";
import { FaceDetailDialog } from "./face-detail-dialog";

// Mirrors this grid's `grid-cols-*` breakpoints as plain numbers for virtualization.
const FULL_WIDTH_COLUMNS: ColumnBreakpoint[] = [
  { minWidth: 0, columns: 2 },
  { minWidth: 640, columns: 3 },
  { minWidth: 1024, columns: 4 },
  { minWidth: 1280, columns: 5 },
  { minWidth: 1536, columns: 6 },
];
const NARROW_COLUMNS: ColumnBreakpoint[] = [
  { minWidth: 0, columns: 2 },
  { minWidth: 640, columns: 3 },
  { minWidth: 1280, columns: 4 },
];

interface FacesContainerInfiniteProps {
  data: InfiniteData<PaginatedFacesResponse | PaginatedFaceSimilarityResponse> | undefined;
  onSimilar: (id: string) => void;
  onDelete?: (id: string) => void;
  fetchNextPage: () => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isFullWidth?: boolean;
  onToggleFilters?: () => void;
}

export function FacesContainerInfinite({
  data,
  onSimilar,
  onDelete,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  isFullWidth,
  onToggleFilters,
}: FacesContainerInfiniteProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [createPersonFace, setCreatePersonFace] = useState<FacePublic | null>(null);

  const faces = useMemo(() => {
    if (!data) return [];
    return data.pages.flatMap((page) => page.data) as (FacePublic | FaceSimilarityResult)[];
  }, [data]);

  const handleNext = useCallback(() => {
    setSelectedIndex((prev) => (prev !== null && prev < faces.length - 1 ? prev + 1 : prev));
  }, [faces.length]);

  const handlePrev = useCallback(() => {
    setSelectedIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev));
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight")
        setSelectedIndex((prev) => (prev !== null && prev < faces.length - 1 ? prev + 1 : prev));
      if (e.key === "ArrowLeft")
        setSelectedIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev));
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [faces.length]);

  const lastElementRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (!hasNextPage || isFetchingNextPage) return;
      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage();
        },
        { threshold: 0.5 }
      );
      if (node) observer.observe(node);
      return () => observer.disconnect();
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage]
  );

  if (faces.length === 0 && !isFetchingNextPage) {
    return (
      <div className="flex flex-col items-center justify-center py-40 border border-dashed border-white/5 rounded-3xl bg-slate-900/10">
        <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-slate-600 mb-4">
          No Faces Resolved
        </p>
        {isFullWidth && (
          <Button
            variant="ghost"
            onClick={onToggleFilters}
            className="text-[9px] font-bold uppercase tracking-widest text-annotation hover:bg-annotation/5"
          >
            <SlidersHorizontal size={12} className="mr-2" /> Expand Filters
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <VirtualizedGrid
        items={faces}
        breakpoints={isFullWidth ? FULL_WIDTH_COLUMNS : NARROW_COLUMNS}
        getKey={(face, index) => `${face.id}-${index}`}
        renderItem={(face, index) => (
          <FaceCard
            face={face}
            onFindSimilar={onSimilar}
            onExpand={() => setSelectedIndex(index)}
            onCreatePerson={setCreatePersonFace}
          />
        )}
      />

      {selectedIndex !== null && (
        <FaceDetailDialog
          face={faces[selectedIndex]}
          isOpen={selectedIndex !== null}
          onOpenChange={(open) => !open && setSelectedIndex(null)}
          onNext={handleNext}
          onPrev={handlePrev}
          hasMore={selectedIndex < faces.length - 1}
          hasPrev={selectedIndex > 0}
          onFindSimilar={onSimilar}
          onCreatePerson={setCreatePersonFace}
          onDelete={onDelete}
        />
      )}

      <CreatePersonDialog
        isOpen={!!createPersonFace}
        onOpenChange={(open) => !open && setCreatePersonFace(null)}
        sourceFace={createPersonFace ?? undefined}
      />

      <div ref={lastElementRef} className="py-20 flex flex-col items-center gap-4">
        {isFetchingNextPage ? (
          <div className="flex items-center gap-3 text-annotation text-[10px] font-bold uppercase tracking-widest">
            <Loader2 className="h-4 w-4 animate-spin" /> Batching
          </div>
        ) : hasNextPage ? (
          <div className="h-1 w-12 rounded-full bg-annotation/20 animate-pulse" />
        ) : (
          <span className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">
            End of Chain
          </span>
        )}
      </div>
    </div>
  );
}
