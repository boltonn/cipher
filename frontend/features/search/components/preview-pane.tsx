"use client";

import { CopyableId } from "@/components/copyable-id";
import {
  useElementWidth,
  useInlineThumbnailSidebar,
} from "@/components/viewers/document-viewer-sidebar";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";
import { filesService, useFile } from "@/features/files/api";
import { FileMetadataPanel } from "@/features/files/components/file-metadata-panel";
import { FileViewerContent, useFileViewerData } from "@/features/files/components/file-viewer-content";
import type { FileBrowserItem } from "@/features/files/types";
import { cn } from "@/lib/utils";
import { AlignLeft, ChevronLeft, ChevronRight, Eye, Info, Loader2, Maximize2, Minimize2 } from "lucide-react";
import { useState } from "react";
import { matchTerms } from "../highlight";
import type { SearchChunk, SearchMode } from "../types";
import { ChunkHighlightedText } from "./chunk-highlighted-text";

interface PreviewPaneProps {
  fileId: string | null;
  chunk?: SearchChunk;
  query: string | null;
  /** Drives what gets highlighted: `text` marks matched words, `semantic` marks the chunk region, `hybrid` does both. */
  searchMode: SearchMode;
  /** Every match for the current file, in reading order -- powers the match navigator when there's more than one. */
  matches?: SearchChunk[];
  onSelectChunk?: (chunkId: string) => void;
  /** Whether the pane currently has the full width (results list hidden). */
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

type FileViewMode = "rendered" | "text";

/**
 * Rendered file preview or the file's extracted text, toggled in the control
 * bar -- the choice is remembered across results and sessions
 * (`useLocalStorageState`) so switching between hits doesn't keep snapping
 * back. What gets highlighted follows the search mode: a `text` query marks
 * its matched words/phrases (ES highlights, or the raw query) in both the
 * rendered PDF and the text view; a `semantic` query instead block-highlights
 * the selected chunk's whole region in the text view and marks no words --
 * the natural-language query isn't a literal string worth marking; `hybrid`
 * does both. The text view's chunk-region highlight can still be toggled off.
 * A Details toggle swaps the content for the file's metadata in either mode.
 */
export function PreviewPane({ fileId, chunk, query, searchMode, matches, onSelectChunk, isExpanded, onToggleExpand }: PreviewPaneProps) {
  const [fileViewMode, setFileViewMode] = useLocalStorageState<FileViewMode>("cipher:search:file-view-mode", "rendered");
  const [highlightChunk, setHighlightChunk] = useState(searchMode !== "text");
  const [showMetadata, setShowMetadata] = useState(false);
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
      <div className="flex h-full items-center justify-center text-sm italic text-muted-foreground">
        Select a result to preview.
      </div>
    );
  }

  if (isPending || !browserItem) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading file...
      </div>
    );
  }

  // Semantic queries carry no literal words to mark -- the chunk region is the highlight instead.
  const terms = searchMode === "semantic" ? [] : matchTerms(chunk, query);
  const matchIndex = chunk && matches ? matches.findIndex((m) => m.id === chunk.id) : -1;
  const hasMultipleMatches = matchIndex >= 0 && (matches?.length ?? 0) > 1;
  const stepMatch = (delta: number) => {
    if (!matches || matchIndex < 0 || !onSelectChunk) return;
    const next = matches[(matchIndex + delta + matches.length) % matches.length];
    onSelectChunk(next.id);
  };

  const barActions = (
    <>
      <button
        type="button"
        onClick={() => setShowMetadata((current) => !current)}
        className={cn(
          "flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors",
          showMetadata ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
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
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground"
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
      <div className="flex shrink-0 items-center gap-0.5 border-b border-border px-4 py-2">
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
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" />
            {label}
          </button>
        ))}
        {chunk && fileViewMode === "text" && !showMetadata && (
          <div className="ml-3 flex items-center gap-2 border-l border-border pl-3">
            <Switch id="highlight-chunk" checked={highlightChunk} onCheckedChange={setHighlightChunk} />
            <Label htmlFor="highlight-chunk" className="text-xs text-muted-foreground">
              Highlight chunk
            </Label>
          </div>
        )}
        {hasMultipleMatches && fileViewMode === "text" && !showMetadata && (
          <div className="ml-3 flex items-center gap-0.5 border-l border-border pl-3">
            <button
              type="button"
              onClick={() => stepMatch(-1)}
              title="Previous match"
              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <span className="px-0.5 text-xs tabular-nums text-muted-foreground">
              Match {matchIndex + 1} of {matches?.length}
            </span>
            <button
              type="button"
              onClick={() => stepMatch(1)}
              title="Next match"
              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
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
            searchQuery={searchMode === "semantic" ? undefined : query ?? undefined}
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
          <span className="shrink-0 rounded border border-primary/20 bg-primary/10 px-2 py-0.5 font-mono text-[10px] text-primary">
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
