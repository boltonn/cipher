"use client";

import { Sources, SourcesContent, SourcesTrigger } from "@/components/ai-elements/sources";
import { FileText, Mail } from "lucide-react";
import type { ChatCitation } from "../types";

interface CitationsProps {
  citations: ChatCitation[];
  onOpen: (citation: ChatCitation) => void;
}

/** Renders the `search_documents` tool's output as clickable source cards --
 * clicking one opens the cited file's viewer scrolled to that location. */
export function Citations({ citations, onOpen }: CitationsProps) {
  if (citations.length === 0) return null;

  return (
    <Sources>
      <SourcesTrigger count={citations.length} />
      <SourcesContent>
        {citations.map((citation) => (
          <button
            key={citation.chunkId}
            type="button"
            onClick={() => onOpen(citation)}
            className="flex w-full max-w-md flex-col items-start gap-1 rounded-md border border-white/10 bg-white/[0.02] px-3 py-2 text-left transition-colors hover:border-indigo-500/40 hover:bg-indigo-500/10"
          >
            <span className="flex w-full items-center gap-2 font-medium text-foreground">
              {citation.filetypeGroup === "email" ? (
                <Mail className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
              ) : (
                <FileText className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
              )}
              <span className="truncate">{citation.displayName}</span>
              {citation.pageNumber !== undefined && (
                <span className="ml-auto shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">
                  Page {citation.pageNumber}
                </span>
              )}
            </span>
            {citation.headingPath && citation.headingPath.length > 0 && (
              <span className="truncate text-[11px] text-muted-foreground">
                {citation.headingPath.join(" › ")}
              </span>
            )}
            <span className="line-clamp-2 text-xs text-muted-foreground">{citation.snippet}</span>
          </button>
        ))}
      </SourcesContent>
    </Sources>
  );
}
