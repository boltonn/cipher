"use client";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { cn } from "@/lib/utils";
import { ClipboardCheck, Database, FileText, Mail, User, Waypoints } from "lucide-react";
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
  action: ClipboardCheck,
};

/** An `action` is an AI proposal the analyst confirms on the linked page -- annotation colour, not a source. */
const actionPillClass =
  "inline-flex h-6 max-w-[22rem] items-center gap-1.5 rounded-md border border-annotation/40 bg-annotation/10 px-2 text-[11px] font-medium text-annotation transition-colors hover:bg-annotation/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** How many pills to show before collapsing the rest behind a "+N" toggle. */
const COLLAPSE_AFTER = 6;

const pillClass =
  "inline-flex h-6 max-w-[14rem] items-center gap-1.5 rounded-md border border-border bg-white/[0.02] px-2 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const sentFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function formatSent(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : sentFormat.format(date);
}

function CitationBody({ citation }: { citation: ChatCitation }) {
  const Icon = KIND_ICON[citation.kind] ?? FileText;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="flex w-full items-start gap-2 font-medium text-foreground">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
        <span className="line-clamp-2 [overflow-wrap:anywhere]">{citation.displayName}</span>
        {citation.pageNumber != null && (
          <span className="ml-auto shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
            Page {citation.pageNumber}
          </span>
        )}
      </span>
      {(citation.sentFrom || citation.dateSent) && (
        <span className="block truncate text-[11px] text-muted-foreground">
          {[citation.dateSent && formatSent(citation.dateSent), citation.sentFrom].filter(Boolean).join(" · ")}
        </span>
      )}
      {citation.headingPath && citation.headingPath.length > 0 && (
        <span className="block truncate text-[11px] text-muted-foreground">
          {citation.headingPath.join(" › ")}
        </span>
      )}
      {citation.snippet && (
        <span className="line-clamp-3 text-xs text-muted-foreground [overflow-wrap:anywhere]">
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
      <span className="font-mono text-[11px] text-muted-foreground/70">{index}</span>
      <Icon className="h-3 w-3 shrink-0" />
      <span className="truncate">{citation.displayName}</span>
      {citation.count != null && (
        <span className="shrink-0 rounded bg-primary/15 px-1 font-mono text-[11px] text-primary">
          {citation.count.toLocaleString()}
        </span>
      )}
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
      <HoverCardContent side="top" collisionPadding={16} className="w-80 overflow-hidden p-3">
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
export function Citations({ citations: all, onOpen }: CitationsProps) {
  const [expanded, setExpanded] = useState(false);
  const actions = all.filter((c) => c.kind === "action" && isNavigableCitation(c));
  const citations = all.filter((c) => c.kind !== "action");
  if (all.length === 0) return null;

  const overflow = citations.length - COLLAPSE_AFTER;
  const visible = expanded ? citations : citations.slice(0, COLLAPSE_AFTER);

  return (
    <div className="flex flex-col gap-1.5">
      {actions.map((action) => (
        <HoverCard key={action.href} openDelay={120} closeDelay={0}>
          <HoverCardTrigger asChild>
            <Link href={action.href as string} className={actionPillClass}>
              <ClipboardCheck className="h-3 w-3 shrink-0" />
              <span className="truncate">{action.displayName}</span>
              <span className="shrink-0 opacity-80">· Review &amp; confirm →</span>
            </Link>
          </HoverCardTrigger>
          <HoverCardContent side="top" collisionPadding={16} className="w-80 overflow-hidden p-3">
            <CitationBody citation={action} />
            <p className="mt-2 text-[11px] text-muted-foreground">Nothing changes until you confirm on that page.</p>
          </HoverCardContent>
        </HoverCard>
      ))}
      {citations.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
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
      )}
    </div>
  );
}
