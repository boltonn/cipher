"use client";

import {
  ChevronLeft,
  ChevronRight,
  FileText,
  HardDrive,
  Loader2,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { CommentSection } from "@/features/comments/components/comment-section";
import { useFile } from "@/features/files/api";
import { cn, formatBytes } from "@/lib/utils";
import { ImagePublic, ImageSimilarityResult } from "../types";
import { ImageViewerContent } from "./image-viewer-content";

interface ImageViewerDialogProps {
  image: ImagePublic | ImageSimilarityResult;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onNext: () => void;
  onPrev: () => void;
  hasMore: boolean;
  hasPrev: boolean;
}

export function ImageViewerDialog({
  image,
  isOpen,
  onOpenChange,
  onNext,
  onPrev,
  hasMore,
  hasPrev,
}: ImageViewerDialogProps) {
  const { data: file, isPending: isFileLoading } = useFile(image.fileId);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[95vw] md:max-w-[90vw] lg:max-w-[85vw] w-full h-[92vh]
        p-0 bg-card border-border overflow-hidden flex flex-col md:flex-row shadow-2xl
        ring-1 ring-white/5 gap-0"
        aria-describedby={undefined}
      >
        {/* Left: Image Preview Section */}
        <div className="flex-1 bg-black relative flex flex-col overflow-hidden group/image">
          <ImageViewerContent image={image} />

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
        <aside className="w-full md:w-100 border-l border-border/50 flex flex-col bg-popover relative">
          {/* Loading Overlay for Sidebar */}
          {isFileLoading && (
            <div className="absolute inset-0 z-50 bg-popover/80 backdrop-blur-sm flex flex-col items-center justify-center space-y-4">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <span className="text-[10px] font-black uppercase tracking-[0.3em] text-primary/70">
                Loading File Metadata...
              </span>
            </div>
          )}

          <DialogHeader className="p-12 pb-4">
            <div className="flex items-center justify-between mb-1">
              <DialogTitle className="text-white tracking-[0.2em] uppercase text-[10px] font-black">
                Image Details
              </DialogTitle>
              <span className="text-[10px] font-mono text-primary bg-primary/10 px-2 py-0.5 rounded border border-primary/20">
                {image.width} × {image.height}
              </span>
            </div>
            <CopyableId id={image.id} />
          </DialogHeader>

          <Separator className="bg-white/5" />

          <ScrollArea className="flex-1">
            <div className="p-4">
              {/* File Section */}
              {file && (
                <section className="p-4 rounded-xl bg-black/40 border border-border/50 space-y-4">
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-emerald-500" />
                    <h4 className="text-[10px] font-black text-foreground uppercase tracking-widest">
                      File Metadata
                    </h4>
                  </div>
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <p className="text-[9px] font-mono text-muted-foreground break-all">
                        {file.path ?? file.filename}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-[8px] text-muted-foreground font-bold uppercase">
                        SHA256 Hash
                      </p>
                      <p className="text-[9px] font-mono text-emerald-500/80 break-all bg-emerald-500/5 p-1.5 rounded border border-emerald-500/10 uppercase">
                        {file.sha256}
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <DataPoint label="Mime Type" value={file.mimeType} />
                      <DataPoint label="Storage" value={formatBytes(file.size)} />
                      {file.device && <DataPoint label="Device" value={file.device} />}
                      <DataPoint
                        label="Loaded"
                        value={
                          file.dateCreated
                            ? new Date(file.dateCreated).toLocaleDateString()
                            : "—"
                        }
                      />
                    </div>
                  </div>
                </section>
              )}

              <Separator className="my-2 bg-white/5" />

              {/* EXIF Section */}
              <section className="p-4 rounded-xl bg-black/40 border border-border/50 space-y-4">
                <div className="flex items-center gap-2 mb-4">
                  <ShieldCheck size={14} className="text-primary" />
                  <h4 className="text-[10px] font-black text-foreground uppercase tracking-widest">
                    Telemetry
                  </h4>
                </div>
                <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                  <DataPoint
                    label="Equipment"
                    value={`${image.cameraMake || "—"} ${image.cameraModel || ""}`}
                  />
                  <DataPoint
                    label="Aperture"
                    value={image.aperture ? `ƒ/${image.aperture}` : "—"}
                  />
                  <DataPoint label="ISO" value={image.iso?.toString() || "—"} />
                  <DataPoint
                    label="Focal"
                    value={image.focalLength ? `${image.focalLength}mm` : "—"}
                  />
                  <DataPoint
                    label="Timestamp"
                    value={
                      image.dateTaken
                        ? new Date(image.dateTaken).toLocaleDateString()
                        : "—"
                    }
                  />
                  <DataPoint
                    label="Elevation"
                    value={
                      image.gpsAltitude
                        ? `${image.gpsAltitude.toFixed(1)}m`
                        : "—"
                    }
                  />
                </div>
              </section>

              {/* Interaction Area */}
              <Tabs defaultValue="file" className="w-full mt-6">
                <TabsList className="w-full bg-muted/50 border border-border/50 h-10 p-1">
                  <TabsTrigger
                    value="file"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-primary"
                  >
                    <HardDrive size={12} className="mr-2" /> Source File
                  </TabsTrigger>
                  <TabsTrigger
                    value="comments"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-primary"
                  >
                    <MessageSquare size={12} className="mr-2" /> Comments
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="file" className="space-y-3 mt-4">
                  {file ? (
                    <div className="p-3 rounded-lg bg-white/2 border border-border/50 space-y-2">
                      <DataPoint label="Filename" value={file.filename} />
                      <DataPoint label="Filetype" value={file.filetypeName ?? file.filetype} />
                      <DataPoint label="URI" value={file.uri ?? "—"} />
                      <DataPoint label="MD5" value={file.md5} />
                    </div>
                  ) : (
                    <p className="text-[10px] text-muted-foreground text-center italic py-4">
                      No source file found for this image.
                    </p>
                  )}
                </TabsContent>

                <TabsContent value="comments" className="mt-4">
                  <CommentSection commentableType="image" commentableId={image.id} />
                </TabsContent>
              </Tabs>
            </div>
          </ScrollArea>
        </aside>
      </DialogContent>
    </Dialog>
  );
}

const DataPoint = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-0.5 min-w-0">
    <p className="text-muted-foreground uppercase text-[8px] font-black tracking-widest leading-none mb-1">
      {label}
    </p>
    <p className="text-foreground font-mono text-[11px] truncate leading-none">
      {value}
    </p>
  </div>
);
