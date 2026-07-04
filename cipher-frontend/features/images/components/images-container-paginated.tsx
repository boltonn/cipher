// images-container-paginated.tsx
"use client";

import { Pagination } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { PaginatedImagesResponse, PaginatedImageSimilarityResponse } from "../types";
import { ImageCard } from "./image-card";
import { ImageDetailDialog } from "./image-detail-dialog";

interface ImagesContainerPaginatedProps {
  data: PaginatedImagesResponse | PaginatedImageSimilarityResponse | undefined;
  onSimilar: (id: string) => void;
  currentPage: number;
  onPageChange: (page: number) => void;
  isLoading: boolean;
  itemsPerPage: number;
  isFullWidth?: boolean;
  onToggleFilters?: () => void;
}

export function ImagesContainerPaginated({
  data,
  onSimilar,
  currentPage,
  onPageChange,
  isLoading,
  itemsPerPage,
  isFullWidth,
  onToggleFilters,
}: ImagesContainerPaginatedProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const images = data?.data ?? [];
  const totalAssets = data?.total ?? 0;

  const handleNext = useCallback(() => {
    setSelectedIndex(prev =>
      prev !== null && prev < images.length - 1 ? prev + 1 : prev
    );
  }, [images.length]);

  const handlePrev = useCallback(() => {
    setSelectedIndex(prev => (prev !== null && prev > 0 ? prev - 1 : prev));
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight")
        setSelectedIndex(prev =>
          prev !== null && prev < images.length - 1 ? prev + 1 : prev
        );
      if (e.key === "ArrowLeft")
        setSelectedIndex(prev => (prev !== null && prev > 0 ? prev - 1 : prev));
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [images.length]);

  if (images.length === 0 && !isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-40 border border-dashed border-white/5 rounded-3xl bg-slate-900/10">
        <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-slate-600 mb-4">
          No Assets Resolved
        </p>
        {isFullWidth && (
          <Button
            variant="ghost"
            onClick={onToggleFilters}
            className="text-[9px] font-bold uppercase tracking-widest text-indigo-400 hover:bg-indigo-500/5"
          >
            <SlidersHorizontal size={12} className="mr-2" /> Expand Filters
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <div
        className={cn(
          "grid gap-6 transition-all duration-500 ease-in-out",
          isFullWidth
            ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5"
            : "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3"
        )}
      >
        {images.map((image, index) => (
          <ImageCard
            key={`${image.id}-${index}`}
            image={image}
            onFindSimilar={onSimilar}
            onExpand={() => setSelectedIndex(index)}
          />
        ))}
      </div>

      {selectedIndex !== null && (
        <ImageDetailDialog
          image={images[selectedIndex]}
          isOpen={selectedIndex !== null}
          onOpenChange={(open) => !open && setSelectedIndex(null)}
          onNext={handleNext}
          onPrev={handlePrev}
          hasMore={selectedIndex < images.length - 1}
          hasPrev={selectedIndex > 0}
        />
      )}

      <Pagination
        currentPage={currentPage}
        totalItems={totalAssets}
        itemsPerPage={itemsPerPage}
        onPageChange={onPageChange}
        isLoading={isLoading}
        siblingCount={2}
      />
    </div>
  );
}
