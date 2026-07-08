"use client";

import { cn } from "@/lib/utils";
import { ChevronRight, FileText, Mail } from "lucide-react";
import type { GroupedFileResult, SearchMode } from "../types";
import { ChunkResultRow } from "./chunk-result-row";

interface FileResultGroupProps {
  group: GroupedFileResult;
  isExpanded: boolean;
  onToggleExpand: () => void;
  isFileSelected: boolean;
  onSelectFile: () => void;
  selectedChunkId?: string;
  onSelectChunk: (chunkId: string) => void;
  searchMode: SearchMode;
  query: string | null;
}

export function FileResultGroup({
  group,
  isExpanded,
  onToggleExpand,
  isFileSelected,
  onSelectFile,
  selectedChunkId,
  onSelectChunk,
  searchMode,
  query,
}: FileResultGroupProps) {
  const Icon = group.filetypeGroup === "email" ? Mail : FileText;

  return (
    <div className="border-b border-white/5">
      <button
        type="button"
        onClick={() => {
          onSelectFile();
          onToggleExpand();
        }}
        className={cn(
          "flex w-full cursor-pointer items-center gap-2 p-3 text-left transition-all",
          isFileSelected
            ? "border-l-4 border-l-indigo-500 bg-indigo-500/10"
            : "border-l-4 border-l-transparent hover:bg-slate-800/30"
        )}
      >
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-slate-500 transition-transform",
            isExpanded && "rotate-90"
          )}
        />
        <Icon className="h-3.5 w-3.5 shrink-0 text-slate-500" />
        <span className="flex-1 truncate text-sm text-slate-200">{group.displayName}</span>
        <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-bold text-slate-400">
          {group.chunks.length} match{group.chunks.length === 1 ? "" : "es"}
        </span>
      </button>

      {isExpanded && (
        <div className="pl-4">
          {group.chunks.map((chunk) => (
            <ChunkResultRow
              key={chunk.id}
              chunk={chunk}
              isSelected={selectedChunkId === chunk.id}
              onClick={() => onSelectChunk(chunk.id)}
              searchMode={searchMode}
              query={query}
              showFilename={false}
            />
          ))}
        </div>
      )}
    </div>
  );
}
