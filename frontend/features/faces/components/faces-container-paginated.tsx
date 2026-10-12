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
import { EAGER_FACE_COUNT, FaceCard } from "./face-card";
import type { GridSelection } from "@/hooks/use-grid-selection";
import { useAssignFaces } from "../hooks/use-assign-face";
import { useRejectFaces, useUnrejectFaces } from "../hooks/use-reject-faces";

interface FacesContainerPaginatedProps {
  data: PaginatedFacesResponse | PaginatedFaceSimilarityResponse | undefined;
  onSimilar: (id: string) => void;
  /** Enables multi-select checkboxes on the cards. */
  selection?: GridSelection;
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
  selection,
  currentPage,
  onPageChange,
  isLoading,
  itemsPerPage,
  isFullWidth,
  onToggleFilters,
}: FacesContainerPaginatedProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [createPersonFace, setCreatePersonFace] = useState<FacePublic | null>(
    null
  );

  const faces = useMemo(
    () => (data?.data ?? []) as (FacePublic | FaceSimilarityResult)[],
    [data]
  );
  const totalFaces = data?.total ?? 0;

  const handleExpand = useCallback(
    (face: FacePublic) => setSelectedIndex(faces.indexOf(face)),
    [faces]
  );

  const { mutate: rejectFaces } = useRejectFaces();
  const { mutate: unrejectFaces } = useUnrejectFaces();
  const handleReject = useCallback(
    (face: FacePublic) => rejectFaces([face.id]),
    [rejectFaces]
  );
  const handleRestore = useCallback(
    (face: FacePublic) => unrejectFaces([face.id]),
    [unrejectFaces]
  );
  const { mutate: assignFaces } = useAssignFaces();
  const handleAssign = useCallback(
    (face: FacePublic, personId: string, personName?: string) =>
      assignFaces({ faceIds: [face.id], personId, personName }),
    [assignFaces]
  );
  const toggleSelection = selection?.toggle;
  const handleToggleSelect = useCallback(
    (face: FacePublic, range: boolean) =>
      toggleSelection?.(
        face.id,
        faces.map((f) => f.id),
        range
      ),
    [faces, toggleSelection]
  );
  const selectedIds = selection?.selectedIds;
  const isSelectionActive = !!selectedIds?.size;

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
    setSelectedIndex((prev) =>
      prev !== null && prev < faces.length - 1 ? prev + 1 : prev
    );
  }, [faces.length]);

  const handlePrev = useCallback(() => {
    setSelectedIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev));
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight")
        setSelectedIndex((prev) =>
          prev !== null && prev < faces.length - 1 ? prev + 1 : prev
        );
      if (e.key === "ArrowLeft")
        setSelectedIndex((prev) =>
          prev !== null && prev > 0 ? prev - 1 : prev
        );
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [faces.length]);

  if (faces.length === 0 && !isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-40 border border-dashed border-border/50 rounded-3xl bg-muted/10">
        <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-4">
          No Faces Resolved
        </p>
        {isFullWidth && (
          <Button
            variant="ghost"
            onClick={onToggleFilters}
            className="text-xs font-medium text-annotation hover:bg-annotation/5"
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
        {faces.map((face, index) => (
          <FaceCard
            key={face.id}
            face={face}
            isEager={index < EAGER_FACE_COUNT}
            onFindSimilar={onSimilar}
            onExpand={handleExpand}
            onCreatePerson={setCreatePersonFace}
            onAssign={handleAssign}
            onReject={handleReject}
            onRestore={handleRestore}
            isSelected={!!selectedIds?.has(face.id)}
            isSelectionActive={isSelectionActive}
            onToggleSelect={toggleSelection ? handleToggleSelect : undefined}
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
