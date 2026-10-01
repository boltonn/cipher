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
import { EntityTypeBadge } from "@/features/entities/components/entity-type-badge";
import {
  useDeleteEntity,
  useEntityProfile,
} from "@/features/entities/hooks/use-entities";
import type { Entity } from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { Ban, Loader2, Undo2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

type Outcome = "discard" | "unlink";

const OUTCOMES: {
  value: Outcome;
  title: string;
  body: string;
  Icon: typeof Ban;
}[] = [
  {
    value: "discard",
    title: "Not an entity",
    body: "Extraction noise — a heading, a newsletter sender, a mis-tagged word. Delete the entity and every mention of it, so it doesn’t come back to the Resolve queue.",
    Icon: Ban,
  },
  {
    value: "unlink",
    title: "Wrong entity",
    body: "The names are real but were grouped or typed wrong. Delete the entity and send its mentions back to the Resolve queue to be resolved again.",
    Icon: Undo2,
  },
];

interface InvalidateEntityDialogProps {
  entity: Pick<Entity, "id" | "displayName" | "entityType"> &
    Partial<Pick<Entity, "selectorType" | "selectorSubtype">>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
}

/** Review an entity's evidence, then delete it -- discarding or unresolving its mentions. */
export function InvalidateEntityDialog({
  entity,
  open,
  onOpenChange,
  onDone,
}: InvalidateEntityDialogProps) {
  const [outcome, setOutcome] = useState<Outcome>("discard");
  const profile = useEntityProfile(open ? entity.id : undefined);
  const remove = useDeleteEntity(() => {
    onOpenChange(false);
    onDone?.();
  });

  const p = profile.data;
  const mentionTotal = Object.values(p?.mentionCounts ?? {}).reduce(
    (sum, n) => sum + (n ?? 0),
    0
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            Mark “{entity.displayName}” invalid?
            <EntityTypeBadge
              type={entity.entityType}
              detail={entity.selectorType}
              subtype={entity.selectorSubtype}
            />
          </DialogTitle>
          <DialogDescription>
            Check its mentions first. Either way the entity, its relationships,
            and any pending Resolve decisions naming it are deleted.
          </DialogDescription>
        </DialogHeader>

        {profile.isPending ? (
          <div className="flex items-center gap-2 py-6 text-xs text-muted-foreground">
            <Loader2 size={14} className="animate-spin" /> Loading mentions…
          </div>
        ) : p ? (
          <div className="space-y-3">
            <dl className="grid grid-cols-3 gap-2 text-center">
              {[
                ["Mentions", mentionTotal],
                ["Files", p.fileCount],
                ["Relationships", p.relatedTotal],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-lg border border-border bg-muted/30 py-2"
                >
                  <dd className="text-base font-semibold tabular-nums text-foreground">
                    {Number(value).toLocaleString()}
                  </dd>
                  <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    {label}
                  </dt>
                </div>
              ))}
            </dl>

            {p.topMentions.length > 0 && (
              <ul className="max-h-40 space-y-1.5 overflow-y-auto rounded-lg border border-border p-2">
                {p.topMentions.slice(0, 5).map((m) => (
                  <li key={m.id} className="text-[11px] leading-snug">
                    <span className="rounded bg-annotation/15 px-1 font-mono text-foreground">
                      {m.surfaceText}
                    </span>
                    {m.context && (
                      <span className="ml-1.5 text-muted-foreground">
                        {m.context.slice(0, 140)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <Link
              href={`/entities/${entity.id}`}
              className="inline-block text-[11px] font-medium text-muted-foreground hover:text-primary"
            >
              Open full dossier →
            </Link>
          </div>
        ) : null}

        <div role="radiogroup" aria-label="What is wrong" className="grid gap-2">
          {OUTCOMES.map(({ value, title, body, Icon }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={outcome === value}
              onClick={() => setOutcome(value)}
              className={cn(
                "flex gap-3 rounded-lg border p-3 text-left transition-colors",
                outcome === value
                  ? "border-destructive/60 bg-destructive/5"
                  : "border-border hover:bg-muted/40"
              )}
            >
              <Icon
                size={15}
                className={cn(
                  "mt-0.5 shrink-0",
                  outcome === value ? "text-destructive" : "text-muted-foreground"
                )}
              />
              <span>
                <span className="block text-xs font-semibold text-foreground">
                  {title}
                </span>
                <span className="block text-[11px] leading-relaxed text-muted-foreground">
                  {body}
                </span>
              </span>
            </button>
          ))}
        </div>

        {remove.isError && (
          <p className="text-[11px] text-destructive">
            Couldn’t delete this entity. Try again.
          </p>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={remove.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            className="gap-2"
            onClick={() =>
              remove.mutate({
                entityId: entity.id,
                discardMentions: outcome === "discard",
              })
            }
          >
            {remove.isPending && <Loader2 size={14} className="animate-spin" />}
            {outcome === "discard"
              ? `Discard entity${mentionTotal ? ` + ${mentionTotal.toLocaleString()} mentions` : ""}`
              : "Delete entity, keep mentions"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
