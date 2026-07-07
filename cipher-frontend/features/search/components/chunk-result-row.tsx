"use client";

import { HighlightedText } from "@/components/ui/highlighted-text";
import { cn } from "@/lib/utils";
import { FileText, Mail, Target } from "lucide-react";
import type { SearchChunk, SearchMode } from "../types";

interface ChunkResultRowProps {
  chunk: SearchChunk;
  isSelected: boolean;
  onClick: () => void;
  searchMode: SearchMode;
  query: string | null;
  /** Hide the filename/subject line when nested under an already-labeled `FileResultGroup`. */
  showFilename?: boolean;
}

export function ChunkResultRow({
  chunk,
  isSelected,
  onClick,
  searchMode,
  query,
  showFilename = true,
}: ChunkResultRowProps) {
  const Icon = chunk.filetypeGroup === "email" ? Mail : FileText;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative w-full cursor-pointer border-b border-slate-800/50 p-4 text-left transition-all",
        isSelected
          ? "border-l-4 border-l-indigo-500 bg-indigo-500/10 shadow-[inset_0_0_20px_rgba(79,70,229,0.05)]"
          : "border-l-4 border-l-transparent hover:bg-slate-800/30"
      )}
    >
      {showFilename && (
        <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold text-slate-500">
          <Icon className="h-3 w-3 shrink-0" />
          <span className="truncate">{chunk.displayName}</span>
        </div>
      )}
      <p className={cn("mb-2 line-clamp-2 text-sm", isSelected ? "text-slate-100" : "text-slate-400")}>
        <HighlightedText text={chunk.text} query={query ?? undefined} />
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        {(searchMode === "semantic" || searchMode === "hybrid") && (
          <div className="flex items-center gap-1 rounded border border-amber-500/20 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-bold text-amber-500">
            <Target className="h-2.5 w-2.5" />
            {(chunk.score * 100).toFixed(1)}%
          </div>
        )}
        {chunk.tags.map((tag) => (
          <span
            key={tag}
            className="rounded border border-indigo-500/20 bg-indigo-500/20 px-1.5 py-0.5 text-[10px] text-indigo-300"
          >
            {tag}
          </span>
        ))}
      </div>
    </button>
  );
}
