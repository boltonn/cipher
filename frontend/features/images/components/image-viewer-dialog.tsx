"use client";

import { ChevronLeft, ChevronRight, FileText, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/copyable-id";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

import { CommentSection } from "@/features/comments/components/comment-section";
import type { FacePublic } from "@/features/faces/types";
import { cn, formatBytes } from "@/lib/utils";
import { useImage, useImageFiles } from "../api";
import { ImagePublic, ImageSimilarityResult } from "../types";
import {
  ImageCameraSection,
  ImageFacesSection,
  useImageFaceSelection,
} from "./image-details";
import { ImageViewerContent } from "./image-viewer-content";

interface ImageViewerDialogProps {
  /** The full image record (images grids already have it). */
  image?: ImagePublic | ImageSimilarityResult;
  /** Content id to resolve the image from -- faces grids / person page pass this. */
  imageId?: string;
  /** Face to pre-select in the triage sidebar. */
  focusFaceId?: string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onNext: () => void;
  onPrev: () => void;
  hasMore: boolean;
  hasPrev: boolean;
  /** Hide the face overlays + triage sidebar (default: shown). */
  showFaces?: boolean;
  /** Run a "find similar faces" search; defaults to navigating to /faces?similar=<id>. */
  onFindSimilarFace?: (faceId: string) => void;
  onCreatePersonFromFace?: (face: FacePublic) => void;
}

export function ImageViewerDialog({
  image,
  imageId,
  focusFaceId,
  isOpen,
  onOpenChange,
  onNext,
  onPrev,
  hasMore,
  hasPrev,
  showFaces = true,
  onFindSimilarFace,
  onCreatePersonFromFace,
}: ImageViewerDialogProps) {
  const { data: fetchedImage } = useImage(imageId, { enabled: !image });
  const resolvedImage = image ?? fetchedImage;

  const { data: files = [], isPending: isFilesLoading } = useImageFiles(
    resolvedImage?.id
  );
  const faceSelection = useImageFaceSelection(
    showFaces ? resolvedImage?.id : undefined,
    {
      focusFaceId,
      onFindSimilarFace,
    }
  );

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[95vw] md:max-w-[90vw] lg:max-w-[85vw] w-full h-[92vh]
        p-0 bg-card border-border overflow-hidden flex flex-col md:flex-row shadow-2xl
        ring-1 ring-white/5 gap-0"
        aria-describedby={undefined}
      >
        {!resolvedImage ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 bg-black">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <DialogTitle className="text-white tracking-wide uppercase text-[11px] font-semibold">
              Loading…
            </DialogTitle>
          </div>
        ) : (
          <>
            {/* Left: Image Preview Section */}
            <div className="flex-1 bg-black relative flex flex-col overflow-hidden group/image">
              <ImageViewerContent
                image={resolvedImage}
                overlayBoxes={faceSelection.overlayBoxes}
              />

              <div className="absolute inset-0 flex items-center justify-between px-4 pointer-events-none">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onPrev}
                  disabled={!hasPrev}
                  className={cn(
                    "h-14 w-14 rounded-full bg-black/40 border border-border text-white pointer-events-auto opacity-0 group-hover/image:opacity-100 transition-all disabled:opacity-0",
                    "hover:bg-primary/20 hover:text-primary hover:border-primary/50"
                  )}
                >
                  <ChevronLeft className="h-8 w-8" strokeWidth={1.5} />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onNext}
                  disabled={!hasMore}
                  className={cn(
                    "h-14 w-14 rounded-full bg-black/40 border border-border text-white pointer-events-auto opacity-0 group-hover/image:opacity-100 transition-all disabled:opacity-0",
                    "hover:bg-primary/20 hover:text-primary hover:border-primary/50"
                  )}
                >
                  <ChevronRight className="h-8 w-8" strokeWidth={1.5} />
                </Button>
              </div>
            </div>

            {/* Right: Data Sidebar */}
            <aside className="w-full md:w-100 border-l border-border/50 flex flex-col min-h-0 bg-popover relative">
              {isFilesLoading && (
                <div className="absolute inset-0 z-50 bg-popover/80 backdrop-blur-sm flex flex-col items-center justify-center space-y-4">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-primary/70">
                    Loading File Metadata...
                  </span>
                </div>
              )}

              <DialogHeader className="shrink-0 p-5 pb-4">
                <div className="flex items-center justify-between mb-1">
                  <DialogTitle className="text-white tracking-wide uppercase text-[11px] font-semibold">
                    Image Details
                  </DialogTitle>
                  <span className="text-[11px] font-mono text-primary bg-primary/10 px-2 py-0.5 rounded border border-primary/20">
                    {resolvedImage.width} × {resolvedImage.height}
                  </span>
                </div>
                <CopyableId id={resolvedImage.id} />
              </DialogHeader>

              <Separator className="bg-white/5" />

              <ScrollArea className="min-h-0 flex-1">
                <div className="p-4 space-y-2">
                  <ImageFacesSection
                    selection={faceSelection}
                    onCreatePerson={onCreatePersonFromFace}
                  />

                  {/* Source files -- every file this image's content was found in */}
                  {files.length > 0 && (
                    <section className="p-4 rounded-xl bg-black/40 border border-border/50 space-y-4">
                      <div className="flex items-center gap-2">
                        <FileText size={14} className="text-emerald-500" />
                        <h4 className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
                          Source Files
                        </h4>
                        <span className="ml-auto text-[11px] font-mono text-muted-foreground">
                          {files.length} {files.length === 1 ? "file" : "files"}
                        </span>
                      </div>

                      <div className="space-y-1">
                        <p className="text-[11px] text-muted-foreground font-bold uppercase">
                          SHA256 Hash
                        </p>
                        <p className="text-[11px] font-mono text-emerald-500/80 break-all bg-emerald-500/5 p-1.5 rounded border border-emerald-500/10 uppercase">
                          {files[0].sha256}
                        </p>
                      </div>

                      {files.map((file) => (
                        <div
                          key={file.id}
                          className="space-y-3 rounded-lg border border-border/40 bg-black/30 p-3"
                        >
                          <p className="text-[11px] font-mono text-muted-foreground break-all">
                            {file.path ?? file.filename}
                          </p>
                          <div className="grid grid-cols-2 gap-4">
                            <DataPoint label="Filename" value={file.filename} />
                            <DataPoint
                              label="Filetype"
                              value={file.filetypeName ?? file.filetype}
                            />
                            <DataPoint
                              label="Mime Type"
                              value={file.mimeType}
                            />
                            <DataPoint
                              label="Storage"
                              value={formatBytes(file.size)}
                            />
                            {file.device && (
                              <DataPoint label="Device" value={file.device} />
                            )}
                            <DataPoint
                              label="Loaded"
                              value={
                                file.dateCreated
                                  ? new Date(
                                      file.dateCreated
                                    ).toLocaleDateString()
                                  : "—"
                              }
                            />
                            <DataPoint label="MD5" value={file.md5} />
                          </div>
                          {file.uri && (
                            <div className="space-y-1">
                              <p className="text-[11px] text-muted-foreground font-bold uppercase">
                                URI
                              </p>
                              <p className="text-[11px] font-mono text-muted-foreground break-all">
                                {file.uri}
                              </p>
                            </div>
                          )}
                        </div>
                      ))}
                    </section>
                  )}

                  <Separator className="my-2 bg-white/5" />

                  <ImageCameraSection image={resolvedImage} />

                  {/* Comments (CommentSection renders its own header) */}
                  <section className="mt-6 p-4 rounded-xl bg-black/40 border border-border/50">
                    <CommentSection
                      commentableType="image"
                      commentableId={resolvedImage.id}
                    />
                  </section>
                </div>
              </ScrollArea>
            </aside>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

const DataPoint = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-0.5 min-w-0">
    <p className="text-muted-foreground uppercase text-[11px] font-semibold tracking-wide leading-none mb-1">
      {label}
    </p>
    <p className="text-foreground font-mono text-[11px] truncate leading-none">
      {value}
    </p>
  </div>
);
