"use client";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { cn } from "@/lib/utils";
import { Database, FileText, Mail, User, Waypoints } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
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

/** How many pills to show before collapsing the rest behind a "+N" toggle. */
const COLLAPSE_AFTER = 6;

const pillClass =
  "inline-flex h-6 max-w-[14rem] items-center gap-1.5 rounded-md border border-border bg-white/[0.02] px-2 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function CitationBody({ citation }: { citation: ChatCitation }) {
  const Icon = KIND_ICON[citation.kind] ?? FileText;
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="flex w-full items-center gap-2 font-medium text-foreground">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
        <span className="truncate">{citation.displayName}</span>
        {citation.pageNumber != null && (
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
        <span className="line-clamp-3 text-xs text-muted-foreground">
          {citation.snippet}
        </span>
      )}
    </div>
  );
}

function CitationPill({
  citation,
  index,
  onOpen,
}: {
  citation: ChatCitation;
  index: number;
  onOpen: (citation: ChatCitation) => void;
}) {
  const Icon = KIND_ICON[citation.kind] ?? FileText;
  const inner = (
    <>
      <span className="font-mono text-[10px] text-muted-foreground/70">{index}</span>
      <Icon className="h-3 w-3 shrink-0" />
      <span className="truncate">{citation.displayName}</span>
    </>
  );

  return (
    <HoverCard openDelay={120} closeDelay={0}>
      <HoverCardTrigger asChild>
        {isNavigableCitation(citation) ? (
          <Link href={citation.href} className={pillClass}>
            {inner}
          </Link>
        ) : (
          <button type="button" onClick={() => onOpen(citation)} className={pillClass}>
            {inner}
          </button>
        )}
      </HoverCardTrigger>
      <HoverCardContent className="w-80 p-3">
        <CitationBody citation={citation} />
      </HoverCardContent>
    </HoverCard>
  );
}

/**
 * A citation-returning tool's output, rendered as an inline row of source
 * pills under the message. Each pill hover-previews the source and, on click,
 * navigates to the record (person/dataset/entity) or opens the file viewer at
 * the cited span (document/email).
 */
export function Citations({ citations, onOpen }: CitationsProps) {
  const [expanded, setExpanded] = useState(false);
  if (citations.length === 0) return null;

  const overflow = citations.length - COLLAPSE_AFTER;
  const visible = expanded ? citations : citations.slice(0, COLLAPSE_AFTER);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        Sources
      </span>
      {visible.map((citation, i) => (
        <CitationPill
          key={citation.chunkId ?? citation.targetId ?? `${citation.kind}-${i}`}
          citation={citation}
          index={i + 1}
          onOpen={onOpen}
        />
      ))}
      {overflow > 0 && !expanded && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className={cn(pillClass, "px-2 font-medium")}
        >
          +{overflow}
        </button>
      )}
    </div>
  );
}
