"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import type { GroupedFileResult, SearchChunk, SearchMode, SearchSelection } from "../types";
import { ChunkResultRow } from "./chunk-result-row";
import { FileResultGroup } from "./file-result-group";

interface ResultsListProps {
  chunks: SearchChunk[];
  groupedResults: GroupedFileResult[];
  groupByFile: boolean;
  selection: SearchSelection | null;
  onSelectFile: (fileId: string) => void;
  onSelectChunk: (fileId: string, chunkId: string) => void;
  searchMode: SearchMode;
  query: string | null;
  isPending: boolean;
  hasMore: boolean;
  isFetching: boolean;
  onLoadMore: () => void;
}

export function ResultsList({
  chunks,
  groupedResults,
  groupByFile,
  selection,
  onSelectFile,
  onSelectChunk,
  searchMode,
  query,
  isPending,
  hasMore,
  isFetching,
  onLoadMore,
}: ResultsListProps) {
  const [expandedFileIds, setExpandedFileIds] = useState<Set<string>>(new Set());

  const toggleExpand = (fileId: string) => {
    setExpandedFileIds((current) => {
      const next = new Set(current);
      if (next.has(fileId)) next.delete(fileId);
      else next.add(fileId);
      return next;
    });
  };

  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Searching...
      </div>
    );
  }

  if (!query) {
    return <p className="p-6 text-center text-xs italic text-slate-600">Search to see results.</p>;
  }

  if (chunks.length === 0) {
    return <p className="p-6 text-center text-xs italic text-slate-600">No matches found.</p>;
  }

  return (
    <div>
      {groupByFile
        ? groupedResults.map((group) => (
            <FileResultGroup
              key={group.fileId}
              group={group}
              isExpanded={expandedFileIds.has(group.fileId)}
              onToggleExpand={() => toggleExpand(group.fileId)}
              isFileSelected={selection?.fileId === group.fileId && !selection.chunkId}
              onSelectFile={() => onSelectFile(group.fileId)}
              selectedChunkId={selection?.fileId === group.fileId ? selection.chunkId : undefined}
              onSelectChunk={(chunkId) => onSelectChunk(group.fileId, chunkId)}
              searchMode={searchMode}
              query={query}
            />
          ))
        : chunks.map((chunk) => (
            <ChunkResultRow
              key={chunk.id}
              chunk={chunk}
              isSelected={selection?.chunkId === chunk.id}
              onClick={() => onSelectChunk(chunk.fileId, chunk.id)}
              searchMode={searchMode}
              query={query}
            />
          ))}

      {hasMore && (
        <button
          type="button"
          disabled={isFetching}
          onClick={onLoadMore}
          className="flex w-full items-center justify-center gap-2 py-3 text-xs italic text-slate-500 hover:bg-slate-800/30 disabled:opacity-50"
        >
          {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Load more results..."}
        </button>
      )}
    </div>
  );
}
