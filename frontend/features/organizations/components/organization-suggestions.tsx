"use client";

import { Button } from "@/components/ui/button";
import { NameSuggestionDialog } from "@/features/organizations/components/name-suggestion-dialog";
import { SuggestionEvidenceDialog } from "@/features/organizations/components/suggestion-evidence-dialog";
import {
  useNameSuggestions,
  useOrganizationSuggestions,
  useResolveSuggestion,
} from "@/features/organizations/hooks/use-organization";
import {
  METHOD_LABEL,
  explainSuggestion,
} from "@/features/organizations/lib/explain-suggestion";
import type {
  NameSuggestion,
  NameSuggestionSide,
  OrganizationSuggestion,
} from "@/features/organizations/types";
import {
  Building2,
  Check,
  HelpCircle,
  FileSearch,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

/**
 * What extraction proposed for this unit or anything below it, awaiting review: sub-units
 * (`partOf`, from signature unit chains) and people (from signatures or their email domain).
 * Accepting turns a suggestion into a real edge, so it joins the chart and the table.
 */
export function OrganizationSuggestions({
  unitId,
  onSelectUnit,
}: {
  unitId: string;
  onSelectUnit: (id: string) => void;
}) {
  const { data: suggestions = [] } = useOrganizationSuggestions(unitId);
  const { data: nameSuggestions = [] } = useNameSuggestions(unitId);
  const [reviewingNames, setReviewingNames] = useState<NameSuggestion | null>(
    null
  );
  const resolve = useResolveSuggestion();
  const [reviewing, setReviewing] = useState<OrganizationSuggestion | null>(
    null
  );
  if (suggestions.length === 0 && nameSuggestions.length === 0) return null;

  const units = suggestions.filter((s) => s.relationshipType === "partOf");
  const people = suggestions.filter((s) => s.relationshipType !== "partOf");
  const row = (s: OrganizationSuggestion) => (
    <SuggestionRow
      key={s.candidateId}
      suggestion={s}
      isPending={
        resolve.isPending && resolve.variables?.candidateId === s.candidateId
      }
      onReview={() => setReviewing(s)}
      onResolve={(status) =>
        resolve.mutate({ candidateId: s.candidateId, status })
      }
      onSelectUnit={onSelectUnit}
    />
  );

  return (
    <div className="rounded-xl border border-annotation/40 bg-annotation/5">
      <div className="flex flex-wrap items-center gap-2 border-b border-annotation/30 px-3 py-2 text-xs">
        <Sparkles size={13} className="text-annotation" />
        <span className="font-semibold text-foreground">Suggestions</span>
        <span className="text-muted-foreground">
          found by extraction — check the sources, then accept to add them to
          the structure
        </span>
      </div>
      <div className="max-h-80 overflow-y-auto">
        {units.length > 0 && (
          <Group icon={Building2} title="Sub-units" count={units.length}>
            {units.map(row)}
          </Group>
        )}
        {people.length > 0 && (
          <Group icon={UserRound} title="People" count={people.length}>
            {people.map(row)}
          </Group>
        )}
        {nameSuggestions.length > 0 && (
          <Group
            icon={HelpCircle}
            title="Names not settled yet"
            count={nameSuggestions.length}
          >
            {nameSuggestions.map((n) => (
              <NameSuggestionRow
                key={n.mentionRelationshipIds[0]}
                suggestion={n}
                onReview={() => setReviewingNames(n)}
              />
            ))}
          </Group>
        )}
      </div>
      <NameSuggestionDialog
        suggestion={reviewingNames}
        onOpenChange={(open) => !open && setReviewingNames(null)}
      />
      <SuggestionEvidenceDialog
        suggestion={reviewing}
        isResolving={resolve.isPending}
        onOpenChange={(open) => !open && setReviewing(null)}
        onResolve={(status) =>
          reviewing &&
          resolve.mutate(
            { candidateId: reviewing.candidateId, status },
            { onSuccess: () => setReviewing(null) }
          )
        }
      />
    </div>
  );
}

/** How settled a name is, in a few words. */
export function sideStatus(side: NameSuggestionSide): string {
  if (side.entity)
    return side.entityIsProvisional ? "auto-created" : "resolved";
  if (side.owner) return `owner: ${side.owner.displayName}`;
  if (side.guess) return `guess: ${side.guess.displayName}`;
  return "new name";
}

export function NameSuggestionRow({
  suggestion: n,
  onReview,
}: {
  suggestion: NameSuggestion;
  onReview: () => void;
}) {
  return (
    <li className="flex items-start gap-3 px-3 py-1.5 text-xs">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="font-medium text-foreground">{n.source.name}</span>
          {n.role && <span className="text-muted-foreground">{n.role}</span>}
          <span className="text-muted-foreground">
            {n.relationshipType === "partOf"
              ? "under"
              : n.relationshipType === "memberOf"
                ? "member of"
                : "at"}
          </span>
          <span className="text-foreground">{n.target.name}</span>
          <span className="rounded-sm border border-annotation/40 px-1 text-[11px] text-annotation">
            {n.extractor === "membership"
              ? "membership email"
              : "email signature"}{" "}
            · {n.sightings}×
          </span>
        </div>
        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {n.source.name}: {sideStatus(n.source)} · {n.target.name}:{" "}
          {sideStatus(n.target)} — choose who each is
        </p>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={onReview}
        className="h-7 shrink-0 gap-1 px-2 text-xs"
      >
        <FileSearch size={12} /> Review
      </Button>
    </li>
  );
}

function Group({
  icon: Icon,
  title,
  count,
  children,
}: {
  icon: typeof Building2;
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="flex items-center gap-1.5 px-3 pb-1 pt-2 text-[11px] font-semibold text-muted-foreground">
        <Icon size={12} /> {title} <span className="font-normal">{count}</span>
      </h3>
      <ul className="divide-y divide-annotation/20">{children}</ul>
    </section>
  );
}

function SuggestionRow({
  suggestion: s,
  isPending,
  onReview,
  onResolve,
  onSelectUnit,
}: {
  suggestion: OrganizationSuggestion;
  isPending: boolean;
  onReview: () => void;
  onResolve: (status: "confirmed" | "rejected") => void;
  onSelectUnit: (id: string) => void;
}) {
  const isUnit = s.relationshipType === "partOf";
  return (
    <li className="flex items-start gap-3 px-3 py-1.5 text-xs">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {isUnit ? (
            <button
              type="button"
              onClick={() => onSelectUnit(s.entity.id)}
              className="font-medium text-foreground hover:text-primary"
            >
              {s.entity.displayName}
            </button>
          ) : (
            <Link
              href={`/entities/${s.entity.id}`}
              className="font-medium text-foreground hover:text-primary"
            >
              {s.entity.displayName}
            </Link>
          )}
          {s.role && <span className="text-muted-foreground">{s.role}</span>}
          <span className="text-muted-foreground">
            {isUnit ? "under" : "at"}
          </span>
          <button
            type="button"
            onClick={() => onSelectUnit(s.unit.id)}
            className="text-muted-foreground hover:text-primary hover:underline"
          >
            {s.unit.displayName}
          </button>
          <span className="rounded-sm border border-annotation/40 px-1 text-[11px] text-annotation">
            {METHOD_LABEL[s.method]} · {Math.round(s.confidence * 100)}%
          </span>
        </div>
        <p
          className="mt-0.5 truncate text-[11px] text-muted-foreground"
          title={explainSuggestion(s)}
        >
          {explainSuggestion(s)}
        </p>
      </div>
      <span className="flex shrink-0 gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={onReview}
          className="h-7 gap-1 px-2 text-xs"
        >
          <FileSearch size={12} /> Sources
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={isPending}
          onClick={() => onResolve("confirmed")}
          className="h-7 gap-1 px-2 text-xs"
        >
          <Check size={12} /> Accept
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={isPending}
          onClick={() => onResolve("rejected")}
          className="h-7 gap-1 px-2 text-xs text-muted-foreground"
        >
          <X size={12} /> Reject
        </Button>
      </span>
    </li>
  );
}
