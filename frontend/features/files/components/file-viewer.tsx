"use client";

import {
  useElementWidth,
  useInlineThumbnailSidebar,
} from "@/components/viewers/document-viewer-sidebar";
import { cn } from "@/lib/utils";
import { FileText, Loader2 } from "lucide-react";
import { filesService, useFile } from "../api";
import type { FileBrowserItem, FileLocationTarget } from "../types";
import { FileViewerContent, useFileViewerData } from "./file-viewer-content";

interface FileViewerProps {
  fileId: string | null | undefined;
  /** Jump target on open (e.g. a search chunk / chat citation). */
  locationTarget?: FileLocationTarget;
  /** Highlighted in the PDF text layer where supported. */
  searchQuery?: string;
  className?: string;
}

/**
 * The one true file preview: renders the *actual* file — PDF, docx, pptx,
 * xlsx, email, image, code/text — via `FileViewerContent`, with all the data
 * fetching (`useFile` + `useFileViewerData`) and width measurement wired up.
 * Drop this in anywhere a file needs to be shown (event source, chat citation,
 * inspector pane) so every surface uses the identical viewer. `FileViewerDialog`
 * / the search preview pane predate it and add their own chrome around the same
 * `FileViewerContent`.
 */
export function FileViewer({ fileId, locationTarget, searchQuery, className }: FileViewerProps) {
  const { data: file, isPending } = useFile(fileId ?? undefined);
  const browserItem: FileBrowserItem | null = file ? { ...file, type: "file" } : null;
  const fileUrl = file?.id ? filesService.getFileUrl(file.id) : undefined;

  const [viewerRef, viewerWidth] = useElementWidth<HTMLDivElement>();
  const sidebarFitsInline = useInlineThumbnailSidebar(viewerWidth);
  const { textContent, isTextLoading, email, isEmailLoading, table, isTableLoading } =
    useFileViewerData(browserItem, fileUrl);

  return (
    <div ref={viewerRef} className={cn("relative flex min-h-0 flex-col overflow-hidden bg-black", className)}>
      {isPending || !browserItem ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          {isPending ? (
            <Loader2 className="size-5 animate-spin" />
          ) : (
            <span className="flex flex-col items-center gap-2 text-xs">
              <FileText className="size-5" />
              File not found
            </span>
          )}
        </div>
      ) : (
        <FileViewerContent
          file={browserItem}
          fileUrl={fileUrl}
          textContent={textContent}
          isTextLoading={isTextLoading}
          email={email}
          isEmailLoading={isEmailLoading}
          table={table}
          isTableLoading={isTableLoading}
          sidebarFitsInline={sidebarFitsInline}
          searchQuery={searchQuery}
          locationTarget={locationTarget}
        />
      )}
    </div>
  );
}
