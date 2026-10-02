"use client";

import { Button } from "@/components/ui/button";
import { VirtualizedGrid } from "@/components/virtualized-grid";
import { CreatePersonDialog } from "@/features/persons/components/create-person-dialog";
import { ColumnBreakpoint } from "@/hooks/use-responsive-columns";
import type { InfiniteData } from "@tanstack/react-query";
import { Loader2, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  FacePublic,
  FaceSimilarityResult,
  PaginatedFacesResponse,
  PaginatedFaceSimilarityResponse,
} from "../types";
import { ImageViewerDialog } from "@/features/images/components/image-viewer-dialog";
import { FaceCard } from "./face-card";
import type { GridSelection } from "@/hooks/use-grid-selection";
import { useAssignFaces } from "../hooks/use-assign-face";
import { useRejectFaces, useUnrejectFaces } from "../hooks/use-reject-faces";

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
  data:
    | InfiniteData<PaginatedFacesResponse | PaginatedFaceSimilarityResponse>
    | undefined;
  onSimilar: (id: string) => void;
  /** Enables multi-select checkboxes on the cards. */
  selection?: GridSelection;
  fetchNextPage: () => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isFullWidth?: boolean;
  onToggleFilters?: () => void;
}

export function FacesContainerInfinite({
  data,
  onSimilar,
  selection,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  isFullWidth,
  onToggleFilters,
}: FacesContainerInfiniteProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [createPersonFace, setCreatePersonFace] = useState<FacePublic | null>(
    null
  );

  const faces = useMemo(() => {
    if (!data) return [];
    return data.pages.flatMap((page) => page.data) as (
      | FacePublic
      | FaceSimilarityResult
    )[];
  }, [data]);

  // `handleExpand`/`renderItem` must keep a stable identity across renders --
  // they're passed to every memoized FaceCard, so recreating them (e.g. when a
  // new page appends to `faces`) would re-render the whole grid. Read the
  // current list through a ref instead of closing over it. (`onSimilar` is
  // already stable -- it comes from a useMemo'd actions object.)
  const facesRef = useRef(faces);
  useEffect(() => {
    facesRef.current = faces;
  }, [faces]);
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
        facesRef.current.map((f) => f.id),
        range
      ),
    [toggleSelection]
  );
  const selectedIds = selection?.selectedIds;
  const isSelectionActive = !!selectedIds?.size;
  const handleExpand = useCallback(
    (face: FacePublic) => setSelectedIndex(facesRef.current.indexOf(face)),
    []
  );
  const renderItem = useCallback(
    (face: FacePublic | FaceSimilarityResult) => (
      <FaceCard
        face={face}
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
    ),
    [
      onSimilar,
      handleExpand,
      handleAssign,
      handleReject,
      handleRestore,
      selectedIds,
      isSelectionActive,
      toggleSelection,
      handleToggleSelect,
    ]
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

  const lastElementRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (!hasNextPage || isFetchingNextPage) return;
      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting && hasNextPage && !isFetchingNextPage)
            fetchNextPage();
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
      <VirtualizedGrid
        items={faces}
        breakpoints={isFullWidth ? FULL_WIDTH_COLUMNS : NARROW_COLUMNS}
        getKey={(face) => face.id}
        renderItem={renderItem}
      />

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

      <div
        ref={lastElementRef}
        className="py-20 flex flex-col items-center gap-4"
      >
        {isFetchingNextPage ? (
          <div className="flex items-center gap-3 text-annotation text-[11px] font-bold uppercase tracking-wide">
            <Loader2 className="h-4 w-4 animate-spin" /> Batching
          </div>
        ) : hasNextPage ? (
          <div className="h-1 w-12 rounded-full bg-annotation/20 animate-pulse" />
        ) : (
          <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wide">
            End of Chain
          </span>
        )}
      </div>
    </div>
  );
}
