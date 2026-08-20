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
import { CopyableId } from "@/components/copyable-id";
import { CommentSection } from "@/features/comments/components/comment-section";
import { cn } from "@/lib/utils";
import {
  ChevronLeft,
  ChevronRight,
  HardDrive,
  Loader2,
  MessageSquare,
  ScrollText,
} from "lucide-react";
import { filesService, useFileText } from "../api";
import type { FileBrowserItem, FileLocationTarget } from "../types";
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
        p-0 bg-card border-white/10 overflow-hidden flex flex-col md:flex-row shadow-2xl
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
        <aside className="w-full md:w-100 border-l border-white/5 flex flex-col bg-popover relative">
          <DialogHeader className="p-12 pb-4">
            <div className="flex items-center justify-between mb-1">
              <DialogTitle className="text-white tracking-[0.2em] uppercase text-[10px] font-black truncate">
                {file.filename}
              </DialogTitle>
              <span className="text-[10px] font-mono text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20 shrink-0 ml-2">
                {file.filetype.toUpperCase()}
              </span>
            </div>
            {file.id && <CopyableId id={file.id} />}
          </DialogHeader>

          <Separator className="bg-white/5" />

          <ScrollArea className="flex-1">
            <div className="p-4">
              <Tabs defaultValue="details" className="w-full">
                <TabsList className="w-full bg-slate-950/50 border border-white/5 h-10 p-1">
                  <TabsTrigger
                    value="details"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-indigo-600"
                  >
                    <HardDrive size={12} className="mr-2" /> Details
                  </TabsTrigger>
                  <TabsTrigger
                    value="text"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-indigo-600"
                    disabled={!file.id}
                  >
                    <ScrollText size={12} className="mr-2" /> Text
                  </TabsTrigger>
                  <TabsTrigger
                    value="comments"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-indigo-600"
                    disabled={!file.id}
                  >
                    <MessageSquare size={12} className="mr-2" /> Comments
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="details" className="mt-4">
                  <FileMetadataPanel file={file} />
                </TabsContent>

                <TabsContent value="text" className="mt-4">
                  <FileTextTab fileId={file.id} />
                </TabsContent>

                <TabsContent value="comments" className="mt-4">
                  {file.id ? (
                    <CommentSection commentableType="file" commentableId={file.id} />
                  ) : (
                    <p className="text-[10px] text-slate-600 text-center italic py-4">
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
            "h-14 w-14 rounded-full bg-black/40 border border-white/10 text-white pointer-events-auto opacity-0 group-hover/viewer:opacity-100 transition-all disabled:opacity-0",
            "hover:bg-indigo-500/20 hover:text-indigo-400 hover:border-indigo-500/50"
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
            "h-14 w-14 rounded-full bg-black/40 border border-white/10 text-white pointer-events-auto opacity-0 group-hover/viewer:opacity-100 transition-all disabled:opacity-0",
            "hover:bg-indigo-500/20 hover:text-indigo-400 hover:border-indigo-500/50"
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

  if (!fileId) {
    return (
      <p className="text-[10px] text-slate-600 text-center italic py-4">Text unavailable.</p>
    );
  }
  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-slate-500">
        <Loader2 size={14} className="animate-spin" /> Loading extracted text...
      </div>
    );
  }
  if (isError || !data) {
    return (
      <p className="text-[10px] text-slate-600 text-center italic py-4">
        Not extracted yet.
      </p>
    );
  }

  return (
    <pre className="text-[10px] font-mono text-slate-300 leading-relaxed whitespace-pre-wrap break-words p-3 rounded-lg bg-black/40 border border-white/5 max-h-125 overflow-auto">
      {data.text}
    </pre>
  );
}

