"use client";

import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AddRelationshipDialog } from "@/features/email-signatures/components/add-relationship-dialog";
import { RelationshipRow } from "@/features/email-signatures/components/relationship-row";
import {
  useEmailSignature,
  useMentionRelationships,
} from "@/features/email-signatures/hooks/use-email-signatures";
import { EntityMentionText } from "@/features/entities/components/entity-mention-text";
import { useOntology } from "@/features/entities/hooks/use-entities";
import { useFileMentions } from "@/features/entities/hooks/use-mentions";
import type { Mention } from "@/features/entities/types";
import { PenLine, Plus, Waypoints } from "lucide-react";
import { useMemo, useState } from "react";

/**
 * Labels inside the email signature, once each: two extractors labelling one name (the same
 * span, or the same name key overlapping it) count once, the resolved copy first.
 */
function signatureLabels(
  mentions: Mention[],
  start: number,
  end: number
): Mention[] {
  const inside = mentions
    .filter(
      (m) =>
        m.startOffset != null &&
        m.endOffset != null &&
        m.startOffset >= start &&
        m.endOffset <= end
    )
    .sort((a, b) => Number(!!b.entityId) - Number(!!a.entityId));
  const kept: Mention[] = [];
  for (const m of inside) {
    const isTwin = kept.some(
      (k) =>
        (k.startOffset === m.startOffset && k.endOffset === m.endOffset) ||
        ((k.startOffset as number) < (m.endOffset as number) &&
          (m.startOffset as number) < (k.endOffset as number) &&
          !!m.normalizedValue &&
          k.normalizedValue === m.normalizedValue &&
          k.entityType === m.entityType)
    );
    if (!isTwin) kept.push(m);
  }
  return kept.sort((a, b) => (a.startOffset ?? 0) - (b.startOffset ?? 0));
}

const SIGNATURE_HINTS = [
  ["Select text", "to label it"],
  ["Click an icon", "to change the type"],
  ["Click a name", "to resolve it"],
  ["×", "if it isn’t an entity"],
] as const;

/**
 * Review one email signature the way an annotator would: the signature text with every
 * label (relabel, remove, resolve, or select new text to label it), and beside it the
 * relationships proposed between those labels -- correct, accept, reject, or add one.
 */
export function EmailSignatureWorkspace({ fileId }: { fileId: string }) {
  const { data: signature, isPending, isError } = useEmailSignature(fileId);
  const { data: relationships = [] } = useMentionRelationships(fileId);
  const { data: mentionsPage } = useFileMentions(fileId);
  const { data: ontology } = useOntology();
  const [hovered, setHovered] = useState<string[]>();
  const [isAdding, setAdding] = useState(false);

  const labels = useMemo(
    () =>
      signature
        ? signatureLabels(
            mentionsPage?.data ?? [],
            signature.startOffset,
            signature.endOffset
          )
        : [],
    [mentionsPage, signature]
  );
  const inSignature = useMemo(() => {
    if (!signature) return [];
    const within = (m: Mention) =>
      m.startOffset != null &&
      m.startOffset >= signature.startOffset &&
      (m.endOffset ?? 0) <= signature.endOffset;
    return relationships.filter((r) => within(r.src) || within(r.dst));
  }, [relationships, signature]);
  const pending = inSignature.filter((r) => r.dateReviewed == null).length;

  if (isPending) return <Skeleton className="h-64 w-full" />;
  if (isError || !signature) {
    return (
      <EmptyState
        icon={PenLine}
        title="No email signature read here"
        body="The email-signature reader didn’t find the sender’s email signature in this email."
      />
    );
  }

  return (
    <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(20rem,2fr)_minmax(0,3fr)]">
      <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-muted/20">
        <header className="flex shrink-0 items-center gap-2 border-b border-border/60 px-4 py-2 text-xs">
          <PenLine size={13} className="text-muted-foreground" />
          <span className="font-semibold text-foreground">Email signature</span>
          <span className="tabular-nums text-muted-foreground">
            {labels.length} labels
          </span>
        </header>
        <EntityMentionText
          fileId={fileId}
          datasetId={signature.datasetId}
          range={{ start: signature.startOffset, end: signature.endOffset }}
          activeMentionIds={hovered}
          className="min-h-0 flex-1 overflow-auto"
        />
        <footer className="flex shrink-0 flex-wrap gap-x-4 gap-y-1 border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
          {SIGNATURE_HINTS.map(([action, effect]) => (
            <span key={action}>
              <span className="font-medium text-foreground">{action}</span>{" "}
              {effect}
            </span>
          ))}
        </footer>
      </section>

      <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-muted/20">
        <header className="flex shrink-0 items-center gap-2 border-b border-border/60 px-3 py-2 text-xs">
          <Waypoints size={13} className="text-muted-foreground" />
          <span className="font-semibold text-foreground">Relationships</span>
          <span className="tabular-nums text-muted-foreground">
            {pending
              ? `${pending} to review`
              : inSignature.length
                ? "all reviewed"
                : "none yet"}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setAdding(true)}
            disabled={labels.length < 2}
            className="ml-auto h-7 gap-1 px-2 text-xs"
          >
            <Plus size={12} /> Add
          </Button>
        </header>
        {inSignature.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs text-muted-foreground">
            No relationships between these labels yet. Add one — who works
            where, which unit is part of which organization, whose phone or
            email it is.
          </p>
        ) : (
          <ul className="min-h-0 flex-1 divide-y divide-border/60 overflow-y-auto">
            {inSignature.map((r) => (
              <RelationshipRow
                key={r.id}
                relationship={r}
                relationships={ontology?.relationships ?? []}
                onHover={setHovered}
              />
            ))}
          </ul>
        )}
      </section>

      <AddRelationshipDialog
        open={isAdding}
        onOpenChange={setAdding}
        mentions={labels}
        relationships={ontology?.relationships ?? []}
      />
    </div>
  );
}
