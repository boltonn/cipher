"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useElementWidth,
  useInlineThumbnailSidebar,
} from "@/components/viewers/document-viewer-sidebar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/copyable-id";
import { cn } from "@/lib/utils";
import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import Link from "next/link";
import { filesService } from "../api";
import type { FileBrowserItem, FileLocationTarget } from "../types";
import type { OverlayBox } from "@/features/faces/components/face-image-overlay";
import {
  FileImageDetails,
  useFileImageDetails,
} from "@/features/images/components/image-details";
import { FileSidePanel } from "./file-side-panel";
import { FileViewerContent, useFileViewerData } from "./file-viewer-content";

interface FileViewerDialogProps {
  file: FileBrowserItem | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** Prev/next navigation across a file list -- omit for single-file contexts (e.g. opening a chat citation). */
  onNext?: () => void;
  onPrev?: () => void;
  hasNext?: boolean;
  hasPrev?: boolean;
  /** Where to jump on open -- e.g. a search result's chunk or a chat citation. */
  locationTarget?: FileLocationTarget;
}

export function FileViewerDialog({
  file,
  isOpen,
  onOpenChange,
  onNext,
  onPrev,
  hasNext = false,
  hasPrev = false,
  locationTarget,
}: FileViewerDialogProps) {
  const fileUrl = file?.id ? filesService.getFileUrl(file.id) : undefined;

  const {
    textContent,
    isTextLoading,
    email,
    isEmailLoading,
    table,
    isTableLoading,
  } = useFileViewerData(file, fileUrl);

  const { image, selection } = useFileImageDetails({
    id: file?.id,
    filetypeGroup: file?.filetypeGroup ?? "",
  });

  if (!file) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[95vw] md:max-w-[90vw] lg:max-w-[85vw] w-full h-[92vh]
        p-0 bg-card border-border overflow-hidden flex flex-col md:flex-row shadow-2xl
        ring-1 ring-white/5 gap-0"
        aria-describedby={undefined}
      >
        {/* Left: Viewer -- keyed by file so the width-measuring hook inside
            remounts fresh per file (its effect only runs once per mount) */}
        <ViewerPane
          key={file.id ?? file.path ?? file.filename}
          file={file}
          fileUrl={fileUrl}
          textContent={textContent}
          isTextLoading={isTextLoading}
          email={email}
          isEmailLoading={isEmailLoading}
          table={table}
          isTableLoading={isTableLoading}
          onNext={onNext}
          onPrev={onPrev}
          hasNext={hasNext}
          hasPrev={hasPrev}
          locationTarget={locationTarget}
          imageOverlayBoxes={selection.overlayBoxes}
        />

        {/* Right: Metadata Sidebar */}
        <aside className="w-full md:w-100 border-l border-border/50 flex flex-col min-h-0 bg-popover relative">
          <DialogHeader className="shrink-0 p-5 pb-4">
            <div className="flex items-center justify-between mb-1">
              <DialogTitle className="text-white tracking-wide uppercase text-[11px] font-semibold truncate">
                {file.filename}
              </DialogTitle>
              <span className="text-[11px] font-mono text-primary bg-primary/10 px-2 py-0.5 rounded border border-primary/20 shrink-0 ml-2">
                {file.filetype.toUpperCase()}
              </span>
            </div>
            {file.id && (
              <div className="flex items-center justify-between gap-2">
                <CopyableId id={file.id} />
                <Link
                  href={
                    file.filetypeGroup === "table"
                      ? `/tables/${file.sha256}`
                      : `/files/${file.id}`
                  }
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline shrink-0"
                >
                  {file.filetypeGroup === "table"
                    ? "Open table"
                    : "Open file page"}{" "}
                  <ExternalLink size={10} />
                </Link>
              </div>
            )}
          </DialogHeader>

          <Separator className="bg-white/5" />

          <ScrollArea className="min-h-0 flex-1">
            <div className="p-4">
              <FileSidePanel
                file={file}
                imageDetails={
                  image && (
                    <FileImageDetails image={image} selection={selection} />
                  )
                }
              />
            </div>
          </ScrollArea>
        </aside>
      </DialogContent>
    </Dialog>
  );
}

interface ViewerPaneProps {
  file: FileBrowserItem;
  fileUrl?: string;
  textContent?: string;
  isTextLoading: boolean;
  email: import("@/features/emails/types").EmailBase | undefined;
  isEmailLoading: boolean;
  table: import("../types").FileTables | undefined;
  isTableLoading: boolean;
  onNext?: () => void;
  onPrev?: () => void;
  hasNext: boolean;
  hasPrev: boolean;
  locationTarget?: import("../types").FileLocationTarget;
  imageOverlayBoxes?: OverlayBox[];
}

function ViewerPane({
  file,
  fileUrl,
  textContent,
  isTextLoading,
  email,
  isEmailLoading,
  table,
  isTableLoading,
  onNext,
  onPrev,
  hasNext,
  hasPrev,
  locationTarget,
  imageOverlayBoxes,
}: ViewerPaneProps) {
  const [viewerRef, viewerWidth] = useElementWidth<HTMLDivElement>();
  const sidebarFitsInline = useInlineThumbnailSidebar(viewerWidth);

  return (
    <div
      ref={viewerRef}
      className="flex-1 bg-black relative flex flex-col overflow-hidden group/viewer"
    >
      <FileViewerContent
        file={file}
        fileUrl={fileUrl}
        textContent={textContent}
        isTextLoading={isTextLoading}
        email={email}
        isEmailLoading={isEmailLoading}
        table={table}
        isTableLoading={isTableLoading}
        sidebarFitsInline={sidebarFitsInline}
        locationTarget={locationTarget}
        imageOverlayBoxes={imageOverlayBoxes}
      />

      <div className="absolute inset-0 flex items-center justify-between px-4 pointer-events-none">
        <Button
          variant="ghost"
          size="icon"
          onClick={onPrev}
          disabled={!hasPrev}
          className={cn(
            "h-14 w-14 rounded-full bg-black/40 border border-border text-white pointer-events-auto opacity-0 group-hover/viewer:opacity-100 transition-all disabled:opacity-0",
            "hover:bg-primary/20 hover:text-primary hover:border-primary/50"
          )}
        >
          <ChevronLeft className="h-8 w-8" strokeWidth={1.5} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onNext}
          disabled={!hasNext}
          className={cn(
            "h-14 w-14 rounded-full bg-black/40 border border-border text-white pointer-events-auto opacity-0 group-hover/viewer:opacity-100 transition-all disabled:opacity-0",
            "hover:bg-primary/20 hover:text-primary hover:border-primary/50"
          )}
        >
          <ChevronRight className="h-8 w-8" strokeWidth={1.5} />
        </Button>
      </div>
    </div>
  );
}
