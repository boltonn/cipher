"use client";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { facesService } from "@/features/faces/api";
import { FacePickerContent } from "@/features/faces/components/face-picker";
import { DetectedFace } from "@/features/faces/types";
import { useAddPersonExample } from "@/features/persons/hooks/use-persons";
import { Loader2 } from "lucide-react";
import { CSSProperties, ReactNode, useRef, useState } from "react";
import { toast } from "sonner";

interface PersonExampleUploadButtonProps {
  personId: string;
  atCap?: boolean;
  className?: string;
  style?: CSSProperties;
  busyIcon?: ReactNode;
  children: ReactNode;
}

/**
 * Self-contained "add an example photo" trigger: hidden file input, face
 * detection, and (when multiple faces are found) a picker dialog to choose
 * one, ending in `useAddPersonExample`. Fully independent per instance so
 * it can be dropped wherever an upload entry point is useful (the gallery's
 * thumbnail rail, its empty state, a toolbar button) without shared state.
 */
export function PersonExampleUploadButton({
  personId,
  atCap,
  className,
  style,
  busyIcon,
  children,
}: PersonExampleUploadButtonProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [detectedFaces, setDetectedFaces] = useState<DetectedFace[]>([]);

  const addExample = useAddPersonExample(personId, () => {
    setPendingFile(null);
    setDetectedFaces([]);
  });

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setIsDetecting(true);
    try {
      const detected = await facesService.detect(file);
      if (detected.length === 0) {
        toast.error("No face detected in that photo");
        return;
      }
      if (detected.length === 1) {
        addExample.mutate({ file, faceIndex: 0 });
      } else {
        setPendingFile(file);
        setDetectedFaces(detected);
      }
    } finally {
      setIsDetecting(false);
    }
  };

  const isBusy = isDetecting || addExample.isPending;

  return (
    <>
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={atCap || isBusy}
        title={atCap ? "Max 10 examples reached" : "Add example photo"}
        className={className}
        style={style}
      >
        {isBusy ? busyIcon ?? <Loader2 size={16} className="animate-spin" /> : children}
      </button>
      <input
        ref={fileInputRef}
        type="file"
        aria-label="Add example photo"
        accept="image/*"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />

      <Dialog open={!!pendingFile} onOpenChange={(open) => !open && setPendingFile(null)}>
        <DialogContent className="bg-card border-border sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white tracking-wide uppercase text-xs font-semibold">
              Select a Face
            </DialogTitle>
          </DialogHeader>
          {pendingFile && (
            <FacePickerContent
              file={pendingFile}
              faces={detectedFaces}
              onConfirm={(index) => addExample.mutate({ file: pendingFile, faceIndex: index })}
              onCancel={() => setPendingFile(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
