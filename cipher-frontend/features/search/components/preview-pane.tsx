"use client";

import { CopyableId } from "@/components/copyable-id";
import {
  useElementWidth,
  useInlineThumbnailSidebar,
} from "@/components/viewers/document-viewer-sidebar";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { filesService, useFile } from "@/features/files/api";
import { FileMetadataPanel } from "@/features/files/components/file-metadata-panel";
import { FileViewerContent, useFileViewerData } from "@/features/files/components/file-viewer-content";
import type { FileBrowserItem } from "@/features/files/types";
import { cn } from "@/lib/utils";
import { AlignLeft, Eye, Info, Loader2, Maximize2, Minimize2 } from "lucide-react";
import { useState } from "react";
import { matchTerms } from "../highlight";
import type { SearchChunk } from "../types";
import { ChunkHighlightedText } from "./chunk-highlighted-text";

interface PreviewPaneProps {
  fileId: string | null;
  chunk?: SearchChunk;
  query: string | null;
  /** Whether the pane currently has the full width (results list hidden). */
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

type FileViewMode = "rendered" | "text";

/**
 * File selected (no chunk) -> rendered file preview or the file's extracted
 * text, toggled in the control bar (PDFs get the query highlighted in-page
 * via `FileViewerContent`'s `searchQuery`). Chunk selected -> the file's
 * extracted text with that chunk's region highlighted (toggleable); matched
 * words/phrases from Elasticsearch are always highlighted either way. A
 * Details toggle swaps the content for the file's metadata in either mode.
 */
export function PreviewPane({ fileId, chunk, query, isExpanded, onToggleExpand }: PreviewPaneProps) {
  const [fileViewMode, setFileViewMode] = useState<FileViewMode>("rendered");
  const [highlightChunk, setHighlightChunk] = useState(true);
  const [showMetadata, setShowMetadata] = useState(false);
  // Jump to the extracted-text view the moment a *new* chunk is selected
  // (matching search's purpose -- show the hit in context), without trapping
  // the user there: they can still switch back to Rendered afterward.
  const [lastChunkId, setLastChunkId] = useState(chunk?.id);
  if (chunk?.id !== lastChunkId) {
    setLastChunkId(chunk?.id);
    if (chunk) setFileViewMode("text");
  }
  const { data: file, isPending } = useFile(fileId ?? undefined);
  const [viewerRef, viewerWidth] = useElementWidth<HTMLDivElement>();
  const sidebarFitsInline = useInlineThumbnailSidebar(viewerWidth);
  const fileUrl = file?.id ? filesService.getFileUrl(file.id) : undefined;
  const browserItem: FileBrowserItem | null = file ? { ...file, type: "file" } : null;
  const { textContent, isTextLoading, email, isEmailLoading, table, isTableLoading } = useFileViewerData(
    browserItem,
    fileUrl
  );

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

  const terms = matchTerms(chunk, query);

  const barActions = (
    <>
      <button
        type="button"
        onClick={() => setShowMetadata((current) => !current)}
        className={cn(
          "flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors",
          showMetadata ? "bg-indigo-600 text-white" : "text-slate-500 hover:text-slate-300"
        )}
      >
        <Info className="h-3.5 w-3.5 shrink-0" />
        Details
      </button>
      {onToggleExpand && (
        <button
          type="button"
          onClick={onToggleExpand}
          title={isExpanded ? "Show results list" : "Expand preview"}
          className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:text-slate-300"
        >
          {isExpanded ? (
            <Minimize2 className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <Maximize2 className="h-3.5 w-3.5 shrink-0" />
          )}
        </button>
      )}
    </>
  );

  // The Rendered/Extracted-text toggle stays available whether or not a
  // chunk is selected -- a selected chunk only changes what the text view
  // highlights, it shouldn't lock the user out of the rendered file.
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-0.5 border-b border-white/10 px-4 py-2">
        {(
          [
            { mode: "rendered", label: "Rendered", Icon: Eye },
            { mode: "text", label: "Extracted text", Icon: AlignLeft },
          ] as const
        ).map(({ mode, label, Icon }) => (
          <button
            key={mode}
            type="button"
            onClick={() => {
              setFileViewMode(mode);
              setShowMetadata(false);
            }}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors",
              fileViewMode === mode && !showMetadata
                ? "bg-indigo-600 text-white"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" />
            {label}
          </button>
        ))}
        {chunk && fileViewMode === "text" && !showMetadata && (
          <div className="ml-3 flex items-center gap-2">
            <Switch id="highlight-chunk" checked={highlightChunk} onCheckedChange={setHighlightChunk} />
            <Label htmlFor="highlight-chunk" className="text-xs text-slate-400">
              Highlight chunk
            </Label>
          </div>
        )}
        <div className="ml-auto flex items-center gap-1">{barActions}</div>
      </div>
      {showMetadata ? (
        <MetadataView file={browserItem} />
      ) : fileViewMode === "text" ? (
        <div className="min-h-0 flex-1">
          <ChunkHighlightedText fileId={fileId} chunk={chunk} terms={terms} highlightChunk={highlightChunk} />
        </div>
      ) : (
        <div ref={viewerRef} className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-black">
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
            searchQuery={query ?? undefined}
          />
        </div>
      )}
    </div>
  );
}

function MetadataView({ file }: { file: FileBrowserItem }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-2xl">
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="truncate text-[10px] font-black uppercase tracking-[0.2em] text-white">
            {file.filename}
          </span>
          <span className="shrink-0 rounded border border-indigo-500/20 bg-indigo-500/10 px-2 py-0.5 font-mono text-[10px] text-indigo-400">
            {file.filetype.toUpperCase()}
          </span>
        </div>
        {file.id && (
          <div className="mb-4">
            <CopyableId id={file.id} />
          </div>
        )}
        <FileMetadataPanel file={file} />
      </div>
    </div>
  );
}
