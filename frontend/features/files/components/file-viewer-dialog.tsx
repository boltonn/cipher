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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { CopyableId } from "@/components/copyable-id";
import { CommentSection } from "@/features/comments/components/comment-section";
import { EntityMentionText } from "@/features/entities/components/entity-mention-text";
import { cn } from "@/lib/utils";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  HardDrive,
  Loader2,
  MessageSquare,
  ScanText,
  ScrollText,
  Waypoints,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { filesService, useFile, useFileText } from "../api";
import type { FileBrowserItem, FileLocationTarget } from "../types";
import { FileTagsEditor } from "./file-tags-editor";
import { FileMetadataPanel } from "./file-metadata-panel";
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

  const { textContent, isTextLoading, email, isEmailLoading, table, isTableLoading } = useFileViewerData(
    file,
    fileUrl
  );

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
                  href={`/files/${file.id}`}
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline shrink-0"
                >
                  Open file page <ExternalLink size={10} />
                </Link>
              </div>
            )}
          </DialogHeader>

          <Separator className="bg-white/5" />

          <ScrollArea className="min-h-0 flex-1">
            <div className="p-4">
              <Tabs defaultValue="details" className="w-full">
                <TabsList className="w-full bg-muted/50 border border-border/50 h-10 p-1">
                  <TabsTrigger
                    value="details"
                    className="flex-1 text-xs font-medium data-[state=active]:bg-primary"
                  >
                    <HardDrive size={12} className="mr-2" /> Details
                  </TabsTrigger>
                  <TabsTrigger
                    value="text"
                    className="flex-1 text-xs font-medium data-[state=active]:bg-primary"
                    disabled={!file.id}
                  >
                    <ScrollText size={12} className="mr-2" /> Text
                  </TabsTrigger>
                  <TabsTrigger
                    value="comments"
                    className="flex-1 text-xs font-medium data-[state=active]:bg-primary"
                    disabled={!file.id}
                  >
                    <MessageSquare size={12} className="mr-2" /> Comments
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="details" className="mt-4">
                  <div className="space-y-4">
                    <FileMetadataPanel file={file} />
                    {file.id && <FileTagsEditor fileId={file.id} />}
                  </div>
                </TabsContent>

                <TabsContent value="text" className="mt-4">
                  <FileTextTab fileId={file.id} />
                </TabsContent>

                <TabsContent value="comments" className="mt-4">
                  {file.id ? (
                    <CommentSection commentableType="file" commentableId={file.id} />
                  ) : (
                    <p className="text-[11px] text-muted-foreground text-center italic py-4">
                      Comments unavailable.
                    </p>
                  )}
                </TabsContent>
              </Tabs>
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
}: ViewerPaneProps) {
  const [viewerRef, viewerWidth] = useElementWidth<HTMLDivElement>();
  const sidebarFitsInline = useInlineThumbnailSidebar(viewerWidth);

  return (
    <div ref={viewerRef} className="flex-1 bg-black relative flex flex-col overflow-hidden group/viewer">
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

function FileTextTab({ fileId }: { fileId?: string }) {
  const { data, isPending, isError } = useFileText(fileId);
  const { data: file } = useFile(fileId);
  const [showEntities, setShowEntities] = useState(false);

  if (!fileId) {
    return (
      <p className="text-[11px] text-muted-foreground text-center italic py-4">Text unavailable.</p>
    );
  }
  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" /> Loading extracted text...
      </div>
    );
  }
  if (isError || !data) {
    return (
      <p className="text-[11px] text-muted-foreground text-center italic py-4">
        Not extracted yet.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {data.imagePages.length > 0 && (
        <p className="flex items-center gap-1.5 text-[11px] text-annotation">
          <ScanText size={12} />
          {data.imagePages.length} image-based page{data.imagePages.length === 1 ? "" : "s"} (
          {data.imagePages.join(", ")}) ·{" "}
          {data.ocrModel ? `text by OCR (${data.ocrModel})` : "no OCR text yet"}
        </p>
      )}
      {file?.datasetId && (
        <label className="flex items-center justify-end gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
          <Waypoints size={12} /> Entities
          <Switch checked={showEntities} onCheckedChange={setShowEntities} />
        </label>
      )}
      {showEntities && file?.datasetId ? (
        <div className="max-h-125 overflow-auto rounded-lg border border-border/50 bg-black/40 text-[11px]">
          <EntityMentionText fileId={fileId} datasetId={file.datasetId} />
        </div>
      ) : (
        <pre className="text-[11px] font-mono text-foreground leading-relaxed whitespace-pre-wrap break-words p-3 rounded-lg bg-black/40 border border-border/50 max-h-125 overflow-auto">
          {data.text}
        </pre>
      )}
    </div>
  );
}

