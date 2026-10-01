"use client";

import { SearchBarShell } from "@/components/search-bar-shell";
import { Button } from "@/components/ui/button";
import { facesService } from "@/features/faces/api";
import {
  FaceFilterPanel,
  hasActiveFaceFilters,
} from "@/features/faces/components/face-filter-panel";
import { FacePickerDialog } from "@/features/faces/components/face-picker";
import { FaceFilters } from "@/features/faces/hooks/use-search-controller";
import { DetectedFace } from "@/features/faces/types";
import { cn } from "@/lib/utils";
import { Filter, ScanFace, Upload as UploadIcon } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

interface FaceUploadSearchBarProps {
  onEmbeddingSelected: (embedding: number[], label?: string) => void;
  isSearching: boolean;
  uploadedLabel?: string;
  filters: FaceFilters;
  setFilters: React.Dispatch<React.SetStateAction<FaceFilters>>;
  isSimilarityMode: boolean;
  isFiltersOpen: boolean;
  onToggleFilters: () => void;
}

export const FaceUploadSearchBar: React.FC<FaceUploadSearchBarProps> = ({
  onEmbeddingSelected,
  isSearching,
  uploadedLabel,
  filters,
  setFilters,
  isSimilarityMode,
  isFiltersOpen,
  onToggleFilters,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [pickerState, setPickerState] = useState<{ file: File; faces: DetectedFace[] } | null>(null);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setIsDetecting(true);
    try {
      const detected = await facesService.detect(file);
      if (detected.length === 0) {
        toast.error("No face detected in that photo");
      } else if (detected.length === 1) {
        onEmbeddingSelected(detected[0].embedding, file.name);
      } else {
        setPickerState({ file, faces: detected });
      }
    } finally {
      setIsDetecting(false);
    }
  };

  return (
    <div className="w-full transition-all duration-500">
      <SearchBarShell
        isActive={isSearching || isDetecting || isDragging}
        accent="annotation"
        icon={<ScanFace size={18} strokeWidth={1.5} />}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
      >
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="h-full flex-1 cursor-pointer bg-transparent px-2 text-left text-sm text-muted-foreground"
        >
          {uploadedLabel ? (
            <span className="text-annotation">{uploadedLabel}</span>
          ) : (
            <span className="text-muted-foreground">
              Upload a photo to find similar faces, or drop one here…
            </span>
          )}
        </button>

        <input
          ref={fileInputRef}
          type="file"
          aria-label="Upload photo"
          className="hidden"
          accept="image/*"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />

        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Filters"
            aria-expanded={isFiltersOpen}
            onClick={onToggleFilters}
            className={cn(
              "relative h-7 w-7",
              isFiltersOpen ? "text-annotation" : "text-muted-foreground hover:text-annotation"
            )}
          >
            <Filter size={15} strokeWidth={1.5} />
            {hasActiveFaceFilters(filters) && (
              <span className="absolute top-1 right-1 h-1.5 w-1.5 rounded-full bg-annotation" />
            )}
          </Button>

          <div className="mx-1 h-4 w-px bg-border" />

          <Button
            type="button"
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-annotation"
          >
            <UploadIcon size={13} strokeWidth={1.5} />
            Upload
          </Button>
        </div>
      </SearchBarShell>

      <div
        className={cn(
          "grid transition-all duration-300 ease-in-out overflow-hidden",
          isFiltersOpen ? "grid-rows-[1fr] opacity-100 mt-3" : "grid-rows-[0fr] opacity-0"
        )}
      >
        <div className="min-h-0">
          <FaceFilterPanel
            params={filters}
            setParams={setFilters}
            isSimilarityMode={isSimilarityMode}
          />
        </div>
      </div>

      <FacePickerDialog
        isOpen={!!pickerState}
        onOpenChange={(open) => !open && setPickerState(null)}
        file={pickerState?.file ?? null}
        faces={pickerState?.faces ?? []}
        onConfirm={(index) => {
          if (!pickerState) return;
          onEmbeddingSelected(pickerState.faces[index].embedding, pickerState.file.name);
        }}
      />
    </div>
  );
};
