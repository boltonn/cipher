"use client";

import {
  useElementWidth,
  useInlineThumbnailSidebar,
} from "@/components/ui/document-viewer-sidebar";
import { filesService, useFile } from "@/features/files/api";
import { FileViewerContent, useFileViewerData } from "@/features/files/components/file-viewer-content";
import type { FileBrowserItem } from "@/features/files/types";
import { Loader2 } from "lucide-react";
import type { SearchChunk } from "../types";
import { ChunkHighlightedText } from "./chunk-highlighted-text";

interface PreviewPaneProps {
  fileId: string | null;
  chunk?: SearchChunk;
  query: string | null;
}

/**
 * File selected (no chunk) -> rendered file preview (PDFs get the query
 * highlighted in-page via `FileViewerContent`'s `searchQuery`). Chunk selected
 * -> the file's extracted text with that chunk highlighted, via
 * `ChunkHighlightedText`.
 */
export function PreviewPane({ fileId, chunk, query }: PreviewPaneProps) {
  const { data: file, isPending } = useFile(fileId ?? undefined);
  const [viewerRef, viewerWidth] = useElementWidth<HTMLDivElement>();
  const sidebarFitsInline = useInlineThumbnailSidebar(viewerWidth);
  const fileUrl = file?.id ? filesService.getFileUrl(file.id) : undefined;
  const browserItem: FileBrowserItem | null = file ? { ...file, type: "file" } : null;
  const { textContent, isTextLoading, email, isEmailLoading } = useFileViewerData(browserItem, fileUrl);

  if (!fileId) {
    return (
      <div className="flex h-full items-center justify-center text-sm italic text-slate-600">
        Select a result to preview.
      </div>
    );
  }

  if (isPending || !browserItem) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading file...
      </div>
    );
  }

  if (chunk) {
    return <ChunkHighlightedText fileId={fileId} chunk={chunk} />;
  }

  return (
    <div ref={viewerRef} className="relative flex h-full flex-1 flex-col overflow-hidden bg-black">
      <FileViewerContent
        file={browserItem}
        fileUrl={fileUrl}
        textContent={textContent}
        isTextLoading={isTextLoading}
        email={email}
        isEmailLoading={isEmailLoading}
        sidebarFitsInline={sidebarFitsInline}
        searchQuery={query ?? undefined}
      />
    </div>
  );
}
