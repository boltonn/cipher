"use client";

import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { Database, FileText, Mail, Target } from "lucide-react";
import { matchTerms, snippetRange } from "../highlight";
import type { GroupedFileResult, SearchMode } from "../types";
import { MentionMarkedText } from "./mention-marked-text";
import { SOURCE_ORIGIN, sourceLabel } from "./source-filter";

interface FileResultGroupProps {
  group: GroupedFileResult;
  isSelected: boolean;
  onSelect: (chunkId: string) => void;
  searchMode: SearchMode;
  query: string | null;
}

/** One row per file: its best-matching snippet, plus (semantic/hybrid only) a
 * match count -- step through the rest from the preview pane's match
 * navigator. BM25 text search (and browsing) skips the count: every chunk
 * of a file that mentions the term "matches" in some literal sense, so the
 * number doesn't carry the same signal a fuzzy semantic/hybrid match count does. */
export function FileResultGroup({ group, isSelected, onSelect, searchMode, query }: FileResultGroupProps) {
  const Icon = group.filetypeGroup === "email" ? Mail : FileText;
  const topChunk = group.chunks.find((c) => c.id === group.topChunkId) ?? group.chunks[0];
  const showMatchSignals = searchMode === "semantic" || searchMode === "hybrid";

  const dateLabel = (() => {
    const raw = topChunk.dateCreated;
    if (!raw) return null;
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? null : format(d, "MMM d, yyyy");
  })();
  const meta = [
    group.filetypeGroup === "email" ? "Email" : "Document",
    topChunk.pageNumber ? `p. ${topChunk.pageNumber}` : null,
    dateLabel,
  ].filter(Boolean);
  const terms = matchTerms(topChunk, query, searchMode);
  const spans = topChunk.mentionSpans;
  const snippet = snippetRange(topChunk.text, terms, spans.length ? spans[0].startOffset - topChunk.startOffset : undefined);

  return (
    <button
      type="button"
      onClick={() => onSelect(group.topChunkId)}
      className={cn(
        "group relative block w-full cursor-pointer border-b border-border/50 p-4 text-left transition-all",
        isSelected
          ? "border-l-4 border-l-primary bg-primary/10 shadow-[inset_0_0_20px_color-mix(in_oklab,var(--primary)_6%,transparent)]"
          : "border-l-4 border-l-transparent hover:bg-muted/30"
      )}
    >
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-bold text-muted-foreground">
        <Icon className="h-3 w-3 shrink-0" />
        <span className="flex-1 truncate">{group.displayName}</span>
        {showMatchSignals && group.matchCount > 1 && (
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] font-bold text-muted-foreground">
            {group.matchCount} matches
          </span>
        )}
      </div>
      <div className="mb-2 truncate font-mono text-[11px] text-muted-foreground/70">
        {meta.join("  ·  ")}
      </div>
      <p
        className={cn(
          "mb-2 line-clamp-3 text-sm",
          // Semantic/hybrid: the whole snippet is the matched chunk -- a left
          // rule in the app's indigo mirrors the preview pane's chunk wash.
          // Text mode leans on the cyan word marks instead.
          showMatchSignals && "border-l-2 border-primary/30 pl-2.5",
          isSelected ? "text-foreground" : "text-muted-foreground"
        )}
      >
        {snippet.start > 0 && "…"}
        <MentionMarkedText
          text={topChunk.text.slice(snippet.start, snippet.end)}
          offset={topChunk.startOffset + snippet.start}
          spans={spans}
          terms={terms}
        />
        {snippet.end < topChunk.text.length && "…"}
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        {showMatchSignals && (
          <div className="flex items-center gap-1 rounded border border-annotation/20 bg-annotation/10 px-1.5 py-0.5 text-[11px] font-bold text-annotation">
            <Target className="h-2.5 w-2.5" />
            {(topChunk.score * 100).toFixed(1)}%
          </div>
        )}
        {group.tags.map((tag) => (
          <span
            key={tag}
            className="rounded border border-primary/20 bg-primary/20 px-1.5 py-0.5 text-[11px] text-primary"
          >
            {tag}
          </span>
        ))}
        {[...group.messageStates, ...group.sourceTags].map((value) => (
          <span
            key={value}
            title={SOURCE_ORIGIN}
            className="flex items-center gap-1 rounded border border-border bg-secondary px-1.5 py-0.5 text-[11px] text-secondary-foreground"
          >
            <Database className="h-2.5 w-2.5 opacity-60" />
            {sourceLabel(value)}
          </span>
        ))}
      </div>
    </button>
  );
}
