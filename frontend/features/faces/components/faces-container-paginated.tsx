"use client";

import { Pagination } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { CreatePersonDialog } from "@/features/persons/components/create-person-dialog";
import { cn } from "@/lib/utils";
import { SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  FacePublic,
  FaceSimilarityResult,
  PaginatedFacesResponse,
  PaginatedFaceSimilarityResponse,
} from "../types";
import { ImageViewerDialog } from "@/features/images/components/image-viewer-dialog";
import { FaceCard } from "./face-card";

interface FacesContainerPaginatedProps {
  data: PaginatedFacesResponse | PaginatedFaceSimilarityResponse | undefined;
  onSimilar: (id: string) => void;
  onDelete?: (id: string) => void;
  currentPage: number;
  onPageChange: (page: number) => void;
  isLoading: boolean;
  itemsPerPage: number;
  isFullWidth?: boolean;
  onToggleFilters?: () => void;
}

export function FacesContainerPaginated({
  data,
  onSimilar,
  onDelete,
  currentPage,
  onPageChange,
  isLoading,
  itemsPerPage,
  isFullWidth,
  onToggleFilters,
}: FacesContainerPaginatedProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [createPersonFace, setCreatePersonFace] = useState<FacePublic | null>(null);

  const faces = useMemo(
    () => (data?.data ?? []) as (FacePublic | FaceSimilarityResult)[],
    [data]
  );
  const totalFaces = data?.total ?? 0;

  const handleExpand = useCallback(
    (face: FacePublic) => setSelectedIndex(faces.indexOf(face)),
    [faces]
  );

  // From inside the viewer, a similarity search replaces the whole grid --
  // close the dialog so the new results aren't hidden behind it.
  const handleFindSimilarFromDialog = useCallback(
    (id: string) => {
      setSelectedIndex(null);
      onSimilar(id);
    },
    [onSimilar]
  );

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

  if (faces.length === 0 && !isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-40 border border-dashed border-border/50 rounded-3xl bg-muted/10">
        <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-muted-foreground mb-4">
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
      <div
        className={cn(
          "grid gap-4 transition-all duration-500 ease-in-out",
          isFullWidth
            ? "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6"
            : "grid-cols-2 sm:grid-cols-3 xl:grid-cols-4"
        )}
      >
        {faces.map((face) => (
          <FaceCard
            key={face.id}
            face={face}
            onFindSimilar={onSimilar}
            onExpand={handleExpand}
            onCreatePerson={setCreatePersonFace}
          />
        ))}
      </div>

      {selectedIndex !== null && faces[selectedIndex] && (
        <ImageViewerDialog
          imageId={faces[selectedIndex].imageId}
          focusFaceId={faces[selectedIndex].id}
          isOpen={selectedIndex !== null}
          onOpenChange={(open) => !open && setSelectedIndex(null)}
          onNext={handleNext}
          onPrev={handlePrev}
          hasMore={selectedIndex < faces.length - 1}
          hasPrev={selectedIndex > 0}
          onFindSimilarFace={handleFindSimilarFromDialog}
          onCreatePersonFromFace={setCreatePersonFace}
          onDeleteFace={onDelete}
        />
      )}

      <CreatePersonDialog
        isOpen={!!createPersonFace}
        onOpenChange={(open) => !open && setCreatePersonFace(null)}
        sourceFace={createPersonFace ?? undefined}
      />

      <Pagination
        currentPage={currentPage}
        totalItems={totalFaces}
        itemsPerPage={itemsPerPage}
        onPageChange={onPageChange}
        isLoading={isLoading}
        siblingCount={2}
      />
    </div>
  );
}
