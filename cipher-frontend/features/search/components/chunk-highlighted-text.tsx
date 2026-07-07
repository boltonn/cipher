"use client";

import { useFileText } from "@/features/files/api";
import { Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import type { SearchChunk } from "../types";

interface ChunkHighlightedTextProps {
  fileId: string;
  chunk: SearchChunk;
}

/**
 * Locates `chunk.text` inside the file's full reconstructed text (verbatim
 * substring match, not the chunk's `startOffset`/`endOffset` -- those are
 * offsets into the original extractor output, while `GET /files/{id}/text`
 * rebuilds the text by joining chunks with `"\n\n"`, which can drift from the
 * original offsets) and highlights it in place.
 */
export function ChunkHighlightedText({ fileId, chunk }: ChunkHighlightedTextProps) {
  const { data, isPending, isError } = useFileText(fileId);
  const markRef = useRef<HTMLElement>(null);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [chunk.id, data]);

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

  const matchIndex = data.text.indexOf(chunk.text);

  if (matchIndex === -1) {
    return (
      <div className="h-full overflow-auto p-6">
        <pre className="whitespace-pre-wrap break-words font-mono text-sm text-slate-300">
          <mark ref={markRef} className="rounded-[2px] bg-amber-400/40 text-inherit">
            {chunk.text}
          </mark>
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
        {before}
        <mark ref={markRef} className="rounded-[2px] bg-amber-400/40 text-inherit">
          {match}
        </mark>
        {after}
      </pre>
    </div>
  );
}
