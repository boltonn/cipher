"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FaceImageWithOverlay } from "@/features/faces/components/face-image-overlay";
import { DetectedFace } from "@/features/faces/types";
import { Check } from "lucide-react";
import { useMemo, useState } from "react";

interface FacePickerContentProps {
  file: File;
  faces: DetectedFace[];
  onConfirm: (index: number) => void;
  onCancel?: () => void;
}

export function FacePickerContent({ file, faces, onConfirm, onCancel }: FacePickerContentProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const previewUrl = useMemo(() => URL.createObjectURL(file), [file]);

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-slate-500">
        {faces.length} faces were detected in this photo. Click one to select it.
      </p>
      <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-black">
        <FaceImageWithOverlay
          src={previewUrl}
          alt={file.name}
          boxes={faces.map((f, i) => ({
            bbox: f.boundingBox,
            isSelected: selected === i,
            label: `${(f.confidence * 100).toFixed(0)}%`,
            onClick: () => setSelected(i),
          }))}
        />
      </div>
      <div className="flex justify-end gap-2">
        {onCancel && (
          <Button variant="ghost" onClick={onCancel} className="text-slate-400">
            Cancel
          </Button>
        )}
        <Button
          onClick={() => selected !== null && onConfirm(selected)}
          disabled={selected === null}
          className="bg-annotation text-annotation-foreground hover:bg-annotation/90 gap-2"
        >
          <Check size={14} />
          Use this face
        </Button>
      </div>
    </div>
  );
}

interface FacePickerDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  file: File | null;
  faces: DetectedFace[];
  onConfirm: (index: number) => void;
}

/** Standalone dialog wrapper around FacePickerContent, for flows with no dialog already open. */
export function FacePickerDialog({ isOpen, onOpenChange, file, faces, onConfirm }: FacePickerDialogProps) {
  if (!file) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-white/10 sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-white tracking-[0.1em] uppercase text-xs font-black">
            Select a Face
          </DialogTitle>
          <DialogDescription className="sr-only">
            Choose which detected face to use for this search
          </DialogDescription>
        </DialogHeader>
        <FacePickerContent
          file={file}
          faces={faces}
          onConfirm={(index) => {
            onConfirm(index);
            onOpenChange(false);
          }}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
