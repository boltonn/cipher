"use client";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { cn } from "@/lib/utils";
import {
  CalendarDays,
  ClipboardCheck,
  Database,
  File,
  FileText,
  Image as ImageIcon,
  Mail,
  ThumbsDown,
  ThumbsUp,
  User,
  Waypoints,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { ChatCitation, CitationKind, Relevance } from "../types";
import { citationKey, isNavigableCitation } from "../types";

interface CitationsProps {
  citations: ChatCitation[];
  /** Called for passage citations (document/email) -- opens the file viewer at the span. */
  onOpen: (citation: ChatCitation) => void;
  /** The analyst's judgments so far, by `citationKey`. */
  judgments: Record<string, Relevance>;
  /** Mark a source relevant / not relevant (null clears); sent with the next message. */
  onJudge: (citation: ChatCitation, relevance: Relevance | null) => void;
}

const KIND_ICON: Record<CitationKind, typeof FileText> = {
  document: FileText,
  email: Mail,
  file: File,
  image: ImageIcon,
  event: CalendarDays,
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

const RELEVANCE_PILL: Record<Relevance, string> = {
  relevant: "border-primary/50 text-primary",
  notRelevant: "line-through opacity-60",
};

/** Relevant / not relevant toggles for one source -- the analyst's say on what the answer rests on. */
function RelevanceButtons({
  relevance,
  onJudge,
}: {
  relevance: Relevance | undefined;
  onJudge: (relevance: Relevance | null) => void;
}) {
  const options: { value: Relevance; label: string; Icon: typeof ThumbsUp }[] = [
    { value: "relevant", label: "Relevant", Icon: ThumbsUp },
    { value: "notRelevant", label: "Not relevant", Icon: ThumbsDown },
  ];
  return (
    <div className="mt-2 flex items-center gap-1.5 border-t border-border pt-2">
      {options.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          aria-pressed={relevance === value}
          onClick={() => onJudge(relevance === value ? null : value)}
          className={cn(
            "inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-md border px-2 text-[11px] transition-colors",
            relevance === value
              ? "border-primary/50 bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:text-foreground"
          )}
        >
          <Icon className="size-3" />
          {label}
        </button>
      ))}
      <span className="ml-auto text-right text-[11px] leading-tight text-muted-foreground">
        The assistant
        <br />
        sees this next turn
      </span>
    </div>
  );
}

function CitationPill({
  citation,
  index,
  onOpen,
  relevance,
  onJudge,
}: {
  citation: ChatCitation;
  index: number;
  onOpen: (citation: ChatCitation) => void;
  relevance: Relevance | undefined;
  onJudge: (relevance: Relevance | null) => void;
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
          <Link href={citation.href} className={cn(pillClass, relevance && RELEVANCE_PILL[relevance])}>
            {inner}
          </Link>
        ) : (
          <button
            type="button"
            onClick={() => onOpen(citation)}
            className={cn(pillClass, relevance && RELEVANCE_PILL[relevance])}
          >
            {inner}
          </button>
        )}
      </HoverCardTrigger>
      <HoverCardContent side="top" collisionPadding={16} className="w-80 overflow-hidden p-3">
        <CitationBody citation={citation} />
        <RelevanceButtons relevance={relevance} onJudge={onJudge} />
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
export function Citations({ citations: all, onOpen, judgments, onJudge }: CitationsProps) {
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
              key={citationKey(citation)}
              citation={citation}
              index={i + 1}
              onOpen={onOpen}
              relevance={judgments[citationKey(citation)]}
              onJudge={(relevance) => onJudge(citation, relevance)}
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
