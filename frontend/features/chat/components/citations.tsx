"use client";

import {
  Sources,
  SourcesContent,
  SourcesTrigger,
} from "@/components/ai-elements/sources";
import { Database, FileText, Mail, User, Waypoints } from "lucide-react";
import Link from "next/link";
import type { ChatCitation, CitationKind } from "../types";
import { isNavigableCitation } from "../types";

interface CitationsProps {
  citations: ChatCitation[];
  /** Called for passage citations (document/email) -- opens the file viewer at the span. */
  onOpen: (citation: ChatCitation) => void;
}

const KIND_ICON: Record<CitationKind, typeof FileText> = {
  document: FileText,
  email: Mail,
  person: User,
  dataset: Database,
  entity: Waypoints,
};

const cardClass =
  "flex w-full max-w-md flex-col items-start gap-1 rounded-md border border-border bg-white/[0.02] px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-primary/10";

function CitationBody({ citation }: { citation: ChatCitation }) {
  const Icon = KIND_ICON[citation.kind] ?? FileText;
  return (
    <>
      <span className="flex w-full items-center gap-2 font-medium text-foreground">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
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
      {citation.snippet && (
        <span className="line-clamp-2 text-xs text-muted-foreground">
          {citation.snippet}
        </span>
      )}
    </>
  );
}

/** Renders a citation-returning tool's output as source cards. `href` citations
 * navigate to the record's page; passage citations open the file viewer. */
export function Citations({ citations, onOpen }: CitationsProps) {
  if (citations.length === 0) return null;

  return (
    <Sources>
      <SourcesTrigger count={citations.length} />
      <SourcesContent>
        {citations.map((citation, i) => {
          const key = citation.chunkId ?? citation.targetId ?? `${citation.kind}-${i}`;
          if (isNavigableCitation(citation)) {
            return (
              <Link key={key} href={citation.href} className={cardClass}>
                <CitationBody citation={citation} />
              </Link>
            );
          }
          return (
            <button
              key={key}
              type="button"
              onClick={() => onOpen(citation)}
              className={cardClass}
            >
              <CitationBody citation={citation} />
            </button>
          );
        })}
      </SourcesContent>
    </Sources>
  );
}
