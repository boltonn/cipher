"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useSuggestionEvidence } from "@/features/organizations/hooks/use-organization";
import {
  METHOD_LABEL,
  explainSuggestion,
} from "@/features/organizations/lib/explain-suggestion";
import type {
  EvidenceSpan,
  OrganizationSuggestion,
  RelationshipEvidence,
} from "@/features/organizations/types";
import { Check, ExternalLink, Mail, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { humanize } from "@/lib/utils";
import { textOffsets } from "@/lib/text-offsets";

/**
 * Why a suggestion exists and every source behind it: each email signature (both names
 * marked in the text), or for an email-domain suggestion the numbers plus the sender's mail --
 * so Accept / Reject is decided on the evidence.
 */
export function SuggestionEvidenceDialog({
  suggestion,
  isResolving,
  onResolve,
  onOpenChange,
}: {
  suggestion: OrganizationSuggestion | null;
  isResolving: boolean;
  onResolve: (status: "confirmed" | "rejected") => void;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: evidence, isPending } = useSuggestionEvidence(
    suggestion?.candidateId
  );

  return (
    <Dialog open={!!suggestion} onOpenChange={onOpenChange}>
      <DialogContent className="border-border bg-card sm:max-w-2xl">
        {suggestion && (
          <>
            <DialogHeader>
              <DialogTitle className="text-sm font-semibold">
                {suggestion.entity.displayName}
                <span className="font-normal text-muted-foreground">
                  {" "}
                  {humanize(suggestion.relationshipType)}{" "}
                </span>
                {suggestion.unit.displayName}
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                {suggestion.role ? `${suggestion.role} · ` : ""}
                via {METHOD_LABEL[suggestion.method]} ·{" "}
                <span className="text-annotation">
                  {Math.round(suggestion.confidence * 100)}% confidence
                </span>
                {evidence &&
                  ` · ${evidence.length} ${evidence.length === 1 ? "source" : "sources"}`}
              </DialogDescription>
            </DialogHeader>

            <Why suggestion={suggestion} />

            <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-1">
              {isPending ? (
                <Skeleton className="h-32 w-full" />
              ) : !evidence?.length ? (
                <p className="py-8 text-center text-xs italic text-muted-foreground">
                  No source passages recorded — this suggestion was entered
                  without mention evidence.
                </p>
              ) : (
                evidence.map((item, i) => (
                  <EvidenceCard
                    key={item.mentionRelationshipId ?? i}
                    evidence={item}
                  />
                ))
              )}
            </div>

            <DialogFooter className="gap-2 sm:justify-between">
              <Legend />
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isResolving}
                  onClick={() => onResolve("rejected")}
                  className="h-8 gap-1 text-xs"
                >
                  <X size={13} /> Reject
                </Button>
                <Button
                  size="sm"
                  disabled={isResolving}
                  onClick={() => onResolve("confirmed")}
                  className="h-8 gap-1 text-xs"
                >
                  <Check size={13} /> Accept
                </Button>
              </div>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function EvidenceCard({ evidence }: { evidence: RelationshipEvidence }) {
  const pathname = usePathname();
  const focus = evidence.src?.startOffset;
  const href =
    evidence.fileId &&
    `/files/${evidence.fileId}?${new URLSearchParams({
      ...(focus != null ? { focus: String(focus) } : {}),
      from: pathname,
    })}`;

  return (
    <article className="rounded-lg border border-border">
      <header className="flex items-center gap-2 border-b border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground">
        <Mail size={12} className="shrink-0" />
        <span className="truncate font-medium text-foreground">
          {evidence.subject ?? "Untitled"}
        </span>
        {evidence.sender && <span className="truncate">{evidence.sender}</span>}
        {evidence.dateSent && (
          <span className="shrink-0 tabular-nums">
            {new Date(evidence.dateSent).toLocaleDateString()}
          </span>
        )}
        <span className="ml-auto shrink-0">
          {evidence.extractor ?? "extractor"}
        </span>
        {href && (
          <Link
            href={href}
            className="inline-flex shrink-0 items-center gap-1 text-primary hover:underline"
          >
            Open <ExternalLink size={11} />
          </Link>
        )}
      </header>
      <pre className="whitespace-pre-wrap break-words px-3 py-2 font-sans text-xs leading-relaxed text-foreground">
        {markSpans(evidence.snippet, evidence.snippetOffset, [
          {
            span: evidence.src,
            className: "bg-annotation/25 ring-1 ring-annotation/50",
          },
          {
            span: evidence.dst,
            className:
              "bg-annotation/25 underline decoration-annotation decoration-2 underline-offset-2",
          },
        ])}
        {!evidence.src && evidence.snippet.length >= 480 && (
          <span className="text-muted-foreground"> …</span>
        )}
      </pre>
    </article>
  );
}

/** The rule behind the suggestion, spelled out -- for an email-domain one, the numbers it rests on. */
function Why({ suggestion }: { suggestion: OrganizationSuggestion }) {
  const e = suggestion.explanation;
  return (
    <div className="rounded-lg border border-annotation/40 bg-annotation/5 px-3 py-2 text-xs">
      <p className="text-foreground">{explainSuggestion(suggestion)}</p>
      {suggestion.method === "emailDomain" && e && (
        <ul className="mt-1.5 space-y-0.5 text-[11px] text-muted-foreground">
          <li>
            Addresses:{" "}
            <span className="text-foreground">{e.addresses.join(", ")}</span>
          </li>
          <li>
            Signatures from @{e.domain}:{" "}
            <span className="text-foreground">{e.organizationSignatures}</span>{" "}
            name {e.organization}
            {e.otherOrganizations
              .map((o) => `, ${o.signatures} name ${o.name}`)
              .join("")}{" "}
            — out of {e.domainSignatures}
          </li>
          {e.colleagues.length > 0 && (
            <li>
              Colleagues who sign that way:{" "}
              <span className="text-foreground">{e.colleagues.join(", ")}</span>
            </li>
          )}
          <li>
            The rule: a domain maps to an organization when most of its
            signatures name it. Sources below are emails sent from these
            addresses.
          </li>
        </ul>
      )}
    </div>
  );
}

export function Legend() {
  return (
    <p className="flex items-center gap-3 text-[11px] text-muted-foreground">
      <span className="rounded-sm bg-annotation/25 px-1 ring-1 ring-annotation/50">
        person
      </span>
      <span className="rounded-sm bg-annotation/25 px-1 underline decoration-annotation decoration-2 underline-offset-2">
        organization
      </span>
    </p>
  );
}

/** The snippet with each span (absolute offsets) wrapped in a mark; spans outside the snippet are skipped. */
function markSpans(
  snippet: string,
  offset: number,
  marks: { span: EvidenceSpan | null; className: string }[]
): ReactNode[] {
  const offsets = textOffsets(snippet); // span offsets count code points; the snippet indexes UTF-16
  const ranges = marks
    .flatMap(({ span, className }) =>
      span?.startOffset != null && span.endOffset != null
        ? [
            {
              start: offsets.toUtf16(span.startOffset - offset),
              end: offsets.toUtf16(span.endOffset - offset),
              className,
            },
          ]
        : []
    )
    .filter((r) => r.start >= 0 && r.end <= snippet.length && r.start < r.end)
    .sort((a, b) => a.start - b.start);
  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const r of ranges) {
    if (r.start < cursor) continue;
    parts.push(snippet.slice(cursor, r.start));
    parts.push(
      <mark
        key={r.start}
        className={`rounded-sm px-0.5 text-foreground ${r.className}`}
      >
        {snippet.slice(r.start, r.end)}
      </mark>
    );
    cursor = r.end;
  }
  parts.push(snippet.slice(cursor));
  return parts;
}
