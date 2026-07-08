"use client";

import { HighlightedText } from "@/components/ui/highlighted-text";
import { useFileText } from "@/features/files/api";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import type { SearchChunk } from "../types";

interface ChunkHighlightedTextProps {
  fileId: string;
  /** Omit to render the file's full extracted text with term highlights only (no chunk region). */
  chunk?: SearchChunk;
  /** Words/phrases (ES matches or the query) always marked throughout the text. */
  terms: string[];
  /** Whether the selected chunk's whole region gets a block highlight -- term matches are always marked. */
  highlightChunk?: boolean;
}

/**
 * Locates `chunk.text` inside the file's full reconstructed text (verbatim
 * substring match, not the chunk's `startOffset`/`endOffset` -- those are
 * offsets into the original extractor output, while `GET /files/{id}/text`
 * rebuilds the text by joining chunks with `"\n\n"`, which can drift from the
 * original offsets) and highlights it in place. The chunk region uses the
 * app's indigo accent, not amber -- amber is reserved for AI/ML annotation.
 */
export function ChunkHighlightedText({ fileId, chunk, terms, highlightChunk = true }: ChunkHighlightedTextProps) {
  const { data, isPending, isError } = useFileText(fileId);
  const markRef = useRef<HTMLElement>(null);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [chunk?.id, data]);

  if (isPending) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading extracted text...
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="flex h-full items-center justify-center p-6 text-center text-xs italic text-slate-600">
        Extracted text unavailable.
      </p>
    );
  }

  const chunkMarkClassName = cn(
    "rounded-[2px] text-inherit",
    highlightChunk ? "bg-indigo-500/20 shadow-[inset_0_0_0_1px_rgba(99,102,241,0.25)]" : "bg-transparent"
  );

  const matchIndex = chunk ? data.text.indexOf(chunk.text) : -1;

  // Always render the full reconstructed text -- if the chunk's region can't
  // be verbatim-located (offset drift, see above), fall back to term-only
  // highlighting rather than truncating the view down to just that chunk.
  if (!chunk || matchIndex === -1) {
    return (
      <div className="h-full overflow-auto p-6">
        <pre className="whitespace-pre-wrap break-words font-mono text-sm text-slate-300">
          <HighlightedText text={data.text} terms={terms} />
        </pre>
      </div>
    );
  }

  const before = data.text.slice(0, matchIndex);
  const match = data.text.slice(matchIndex, matchIndex + chunk.text.length);
  const after = data.text.slice(matchIndex + chunk.text.length);

  return (
    <div className="h-full overflow-auto p-6">
      <pre className="whitespace-pre-wrap break-words font-mono text-sm text-slate-300">
        <HighlightedText text={before} terms={terms} />
        <mark ref={markRef} className={chunkMarkClassName}>
          <HighlightedText text={match} terms={terms} />
        </mark>
        <HighlightedText text={after} terms={terms} />
      </pre>
    </div>
  );
}
