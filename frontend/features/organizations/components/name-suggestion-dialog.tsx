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
import { EntityPicker } from "@/features/entities/components/entity-picker";
import {
  EvidenceCard,
  Legend,
} from "@/features/organizations/components/suggestion-evidence-dialog";
import {
  useNameSuggestionEvidence,
  useReviewNameSuggestion,
} from "@/features/organizations/hooks/use-organization";
import type {
  NameSuggestion,
  NameSuggestionChoice,
  NameSuggestionSide,
} from "@/features/organizations/types";
import { cn } from "@/lib/utils";
import { Check, Info, X } from "lucide-react";
import { useState } from "react";

/** What the reviewer picked for one name: an existing entity, or a new one. */
type Pick =
  | { entityId: string; label: string }
  | { entityId: null; label: string };

const plural = (n: number, word: string) =>
  `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
const verb = (s: NameSuggestion) =>
  ({ part_of: "is part of", member_of: "is a member of" })[
    s.relationshipType as string
  ] ?? "works at";
const SOURCE_LABEL = {
  signature: "email signature",
  membership: "membership email",
} as const;
/** Why the address owner is offered for the person end. */
const OWNER_REASON = {
  signature: "which this signature was confirmed against",
  membership: "the address the membership email was sent to",
} as const;

/** The pick that needs no decision: already resolved, or the owner of the sending address. */
function initialPick(side: NameSuggestionSide): Pick | null {
  if (side.entity)
    return { entityId: side.entity.id, label: side.entity.displayName };
  if (side.owner)
    return { entityId: side.owner.id, label: side.owner.displayName };
  return null;
}

/**
 * Review a signature relationship whose names are not settled yet: the sources, then who each
 * name is -- the resolver's guess, someone else, or a new entity. Nothing is preselected unless
 * it is already settled or the signature was confirmed against an address that person owns.
 * Accepting settles both names (their entities become confirmed, not provisional) and adds the edge.
 */
export function NameSuggestionDialog({
  suggestion,
  onOpenChange,
}: {
  suggestion: NameSuggestion | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={!!suggestion} onOpenChange={onOpenChange}>
      <DialogContent className="border-border bg-card sm:max-w-2xl">
        {suggestion && (
          <Review
            key={suggestion.mentionRelationshipIds[0]}
            suggestion={suggestion}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function Review({
  suggestion: s,
  onDone,
}: {
  suggestion: NameSuggestion;
  onDone: () => void;
}) {
  const { data: evidence, isPending } = useNameSuggestionEvidence(
    s.mentionRelationshipIds
  );
  const { accept, dismiss } = useReviewNameSuggestion();
  const [source, setSource] = useState<Pick | null>(() =>
    initialPick(s.source)
  );
  const [target, setTarget] = useState<Pick | null>(() =>
    initialPick(s.target)
  );
  const busy = accept.isPending || dismiss.isPending;

  const choice = (
    side: NameSuggestionSide,
    pick: Pick
  ): NameSuggestionChoice => ({
    normalizedValue: side.normalizedValue,
    entityType: side.entityType,
    entityId: pick.entityId,
    displayName: side.name,
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle className="text-sm font-semibold">
          {s.source.name}{" "}
          <span className="font-normal text-muted-foreground">{verb(s)}</span>{" "}
          {s.target.name}
        </DialogTitle>
        <DialogDescription className="text-xs text-muted-foreground">
          {s.role ? `${s.role} · ` : ""}from{" "}
          {plural(s.sightings, SOURCE_LABEL[s.extractor])} · the names are not
          settled yet, so choose who each one is
        </DialogDescription>
      </DialogHeader>

      <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
        <div className="grid gap-3 sm:grid-cols-2">
          <SidePicker
            side={s.source}
            ownerReason={OWNER_REASON[s.extractor]}
            pick={source}
            onPick={setSource}
          />
          <SidePicker side={s.target} pick={target} onPick={setTarget} />
        </div>

        {source && target && (
          <Effects suggestion={s} source={source} target={target} />
        )}

        <section className="space-y-2">
          <h3 className="text-[11px] font-semibold text-muted-foreground">
            Sources
          </h3>
          {isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            evidence?.map((item, i) => (
              <EvidenceCard
                key={item.mentionRelationshipId ?? i}
                evidence={item}
              />
            ))
          )}
        </section>
      </div>

      <DialogFooter className="gap-2 sm:justify-between">
        <Legend />
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => dismiss.mutate(s, { onSuccess: onDone })}
            className="h-8 gap-1 text-xs"
            title="Stop suggesting this; the names stay in the Resolve queue"
          >
            <X size={13} /> Dismiss
          </Button>
          <Button
            size="sm"
            disabled={busy || !source || !target}
            onClick={() =>
              source &&
              target &&
              accept.mutate(
                {
                  suggestion: s,
                  source: choice(s.source, source),
                  target: choice(s.target, target),
                },
                { onSuccess: onDone }
              )
            }
            className="h-8 gap-1 text-xs"
          >
            <Check size={13} /> Accept
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}

function SidePicker({
  side,
  ownerReason,
  pick,
  onPick,
}: {
  side: NameSuggestionSide;
  ownerReason?: string;
  pick: Pick | null;
  onPick: (pick: Pick) => void;
}) {
  const options: { pick: Pick; reason: string }[] = [];
  if (side.owner) {
    options.push({
      pick: { entityId: side.owner.id, label: side.owner.displayName },
      reason: `owns ${side.ownerAddress ?? "the address"}, ${ownerReason}`,
    });
  }
  if (side.guess && side.guess.id !== side.owner?.id) {
    options.push({
      pick: { entityId: side.guess.id, label: side.guess.displayName },
      reason: `the resolver's best guess${side.guessScore != null ? ` (${Math.round(side.guessScore * 100)}%)` : ""}`,
    });
  }
  // a bare address is no name to create someone under -- pick who owns it instead
  if (!side.name.includes("@"))
    options.push({
      pick: { entityId: null, label: side.name },
      reason: `create a new ${side.entityType}`,
    });
  const isChosen = (option: Pick) =>
    pick?.entityId === option.entityId && pick?.label === option.label;

  return (
    <div className="rounded-lg border border-border p-3 text-xs">
      <p className="font-semibold text-foreground">“{side.name}”</p>
      <p className="mb-2 text-[11px] text-muted-foreground">
        {side.entityType} ·{" "}
        {plural(side.unresolvedMentions, "unresolved mention")}
      </p>
      {side.entity ? (
        <p className="rounded-md bg-muted/40 px-2 py-1.5 text-[11px]">
          Already resolved to{" "}
          <span className="font-medium text-foreground">
            {side.entity.displayName}
          </span>
          {side.entityIsProvisional &&
            " (auto-created — accepting confirms it)"}
        </p>
      ) : (
        <div className="space-y-1">
          {options.map(({ pick: option, reason }) => (
            <button
              key={`${option.entityId}-${option.label}`}
              type="button"
              onClick={() => onPick(option)}
              aria-pressed={isChosen(option)}
              className={cn(
                "flex w-full flex-col rounded-md border px-2 py-1.5 text-left transition-colors",
                isChosen(option)
                  ? "border-primary bg-primary/10"
                  : "border-border hover:border-primary/50"
              )}
            >
              <span className="font-medium text-foreground">
                {option.entityId ? option.label : `New: ${option.label}`}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {reason}
              </span>
            </button>
          ))}
          {pick?.entityId && !options.some((o) => isChosen(o.pick)) && (
            <p className="rounded-md border border-primary bg-primary/10 px-2 py-1.5 font-medium">
              {pick.label}
            </p>
          )}
          <EntityPicker
            entityTypes={[side.entityType]}
            placeholder={`Someone else… search ${side.entityType}s`}
            onSelect={(entityId, displayName) =>
              onPick({ entityId, label: displayName ?? "the selected entity" })
            }
            className="w-full"
          />
        </div>
      )}
    </div>
  );
}

/** Everything Accept will change, spelled out -- it settles names, not just the edge. */
function Effects({
  suggestion: s,
  source,
  target,
}: {
  suggestion: NameSuggestion;
  source: Pick;
  target: Pick;
}) {
  const settle = (side: NameSuggestionSide, pick: Pick) => {
    if (side.entity) {
      return side.entityIsProvisional
        ? `confirm the auto-created ${side.entityType} ${side.entity.displayName}`
        : null;
    }
    const mentions = plural(side.unresolvedMentions, "mention");
    return pick.entityId
      ? `resolve “${side.name}” (${mentions}) to ${pick.label} and confirm it`
      : `create ${side.entityType} ${side.name} as a confirmed entity and resolve its ${mentions} to it`;
  };
  const steps = [settle(s.source, source), settle(s.target, target)].filter(
    Boolean
  );
  const edge =
    s.relationshipType === "partOf"
      ? `make ${target.label} the parent of ${source.label}`
      : `add ${source.label} employed by ${target.label}${s.role ? ` (${s.role})` : ""}`;

  return (
    <div className="flex gap-2 rounded-lg border border-annotation/40 bg-annotation/5 px-3 py-2 text-xs">
      <Info size={14} className="mt-0.5 shrink-0 text-annotation" />
      <div>
        <p className="font-medium text-foreground">Accepting will:</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted-foreground">
          {steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
          <li>{edge}</li>
        </ul>
        <p className="mt-1 text-[11px] text-muted-foreground">
          Confirmed entities are no longer provisional. Resolutions can be
          undone from the entity page.
        </p>
      </div>
    </div>
  );
}
