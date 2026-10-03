// images-container-infinite.tsx
"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { InfiniteData } from "@tanstack/react-query";
import { Loader2, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  ImagePublic,
  ImageSimilarityResult,
  PaginatedImagesResponse,
  PaginatedImageSimilarityResponse,
} from "../types";
import type { GridSelection } from "@/hooks/use-grid-selection";
import type { ImageAnnotation } from "../hooks/use-image-annotation";
import { ImageCard } from "./image-card";
import { ImageViewerDialog } from "./image-viewer-dialog";

interface ImagesContainerInfiniteProps {
  data:
    | InfiniteData<PaginatedImagesResponse | PaginatedImageSimilarityResponse>
    | undefined;
  onSimilar: (id: string) => void;
  /** Enables multi-select checkboxes on the cards. */
  selection?: GridSelection;
  /** Annotate mode: card clicks label the annotation's tag instead of selecting / expanding. */
  annotation?: ImageAnnotation;
  /** Tags the grid is filtered to, so cards can show their rejected / predicted state. */
  reviewTags?: string[];
  fetchNextPage: () => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isFullWidth?: boolean;
  onToggleFilters?: () => void;
}

export function ImagesContainerInfinite({
  data,
  onSimilar,
  selection,
  annotation,
  reviewTags,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  isFullWidth,
  onToggleFilters,
}: ImagesContainerInfiniteProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const images = useMemo(() => {
    if (!data) return [];
    const flat = data.pages.flatMap((page) => page.data) as (
      | ImagePublic
      | ImageSimilarityResult
    )[];
    // The backend returns one row per distinct image (`id` == sha256), but an
    // ANN similarity page boundary can still transiently repeat one; drop it so
    // React keys stay unique.
    const seen = new Set<string>();
    return flat.filter((image) => {
      if (seen.has(image.id)) return false;
      seen.add(image.id);
      return true;
    });
  }, [data]);

  const handleNext = useCallback(() => {
    setSelectedIndex((prev) =>
      prev !== null && prev < images.length - 1 ? prev + 1 : prev
    );
  }, [images.length]);

  const handlePrev = useCallback(() => {
    setSelectedIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev));
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight")
        setSelectedIndex((prev) =>
          prev !== null && prev < images.length - 1 ? prev + 1 : prev
        );
      if (e.key === "ArrowLeft")
        setSelectedIndex((prev) =>
          prev !== null && prev > 0 ? prev - 1 : prev
        );
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [images.length]);

  const lastElementRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (!hasNextPage || isFetchingNextPage) return;

      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
            fetchNextPage();
          }
        },
        { threshold: 0.5 }
      );

      if (node) observer.observe(node);
      return () => observer.disconnect();
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage]
  );

  if (images.length === 0 && !isFetchingNextPage) {
    return (
      <div className="flex flex-col items-center justify-center py-40 border border-dashed border-border/50 rounded-3xl bg-muted/10">
        <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-4">
          No Assets Resolved
        </p>
        {isFullWidth && (
          <Button
            variant="ghost"
            onClick={onToggleFilters}
            className="text-xs font-medium text-primary hover:bg-primary/5"
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
            key={image.id}
            image={image}
            onFindSimilar={onSimilar}
            onExpand={() => setSelectedIndex(index)}
            reviewTags={reviewTags}
            isSelected={!!selection?.selectedIds.has(image.id)}
            isSelectionActive={!!selection?.selectedIds.size}
            onToggleSelect={
              selection &&
              ((target, range) =>
                selection.toggle(
                  target.id,
                  images.map((i) => i.id),
                  range
                ))
            }
            annotation={
              annotation && {
                label: annotation.labelFor(image),
                isStaged: annotation.isStaged(image.id),
              }
            }
            onAnnotate={(target, range) => annotation?.cycle(target, images, range)}
          />
        ))}
      </div>

      {selectedIndex !== null && (
        <ImageViewerDialog
          image={images[selectedIndex]}
          isOpen={selectedIndex !== null}
          onOpenChange={(open) => !open && setSelectedIndex(null)}
          onNext={handleNext}
          onPrev={handlePrev}
          hasMore={selectedIndex < images.length - 1}
          hasPrev={selectedIndex > 0}
        />
      )}

      <div
        ref={lastElementRef}
        className="py-20 flex flex-col items-center gap-4"
      >
        {isFetchingNextPage ? (
          <div className="flex items-center gap-3 text-primary text-[11px] font-bold uppercase tracking-wide">
            <Loader2 className="h-4 w-4 animate-spin" /> Batching
          </div>
        ) : hasNextPage ? (
          <div className="h-1 w-12 rounded-full bg-primary/20 animate-pulse" />
        ) : (
          <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wide">
            End of Chain
          </span>
        )}
      </div>
    </div>
  );
}
