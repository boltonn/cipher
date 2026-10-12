"use client";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import {
  useEntityRelatedInfinite,
  useRelationshipSuggestions,
  useResolveRelationshipSuggestion,
} from "@/features/entities/hooks/use-entities";
import {
  FAMILY_ROLE_INVERSE,
  DERIVED_RELATIONSHIPS,
  RELATIONSHIP_TYPES,
  type RelatedEntitySort,
  type RelationshipSuggestion,
  type RelationshipType,
  type TraversalDirection,
} from "@/features/entities/types";
import { cn, humanize } from "@/lib/utils";
import { Check, Loader2, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const SORTS: { value: RelatedEntitySort; label: string }[] = [
  { value: "weight", label: "Strength" },
  { value: "recent", label: "Recent" },
  { value: "name", label: "Name" },
];

const DIRECTIONS: { value: TraversalDirection; label: string }[] = [
  { value: "both", label: "Both" },
  { value: "out", label: "Out" },
  { value: "in", label: "In" },
];

/**
 * The dossier's Relationships section: every neighbour of an entity, sortable by
 * edge strength (message count) / recency / name, filterable by direction and
 * relationship type, paged with "load more".
 */
export function EntityRelationships({ entityId }: { entityId: string }) {
  const [sort, setSort] = useState<RelatedEntitySort>("weight");
  const [direction, setDirection] = useState<TraversalDirection>("both");
  const [relType, setRelType] = useState<RelationshipType | "all">("all");

  const { data, isPending, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useEntityRelatedInfinite(entityId, {
      sort,
      direction,
      relationshipType: relType === "all" ? undefined : relType,
    });

  const rows = data?.pages.flatMap((p) => p.data) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  if (isPending) {
    return <Loader2 size={16} className="animate-spin text-muted-foreground" />;
  }
  if (total === 0) {
    return (
      <p className="text-[11px] italic text-muted-foreground">
        No relationships recorded yet.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Seg options={SORTS} value={sort} onChange={setSort} />
        <Seg options={DIRECTIONS} value={direction} onChange={setDirection} />
        <Select
          value={relType}
          onValueChange={(v) => setRelType(v as RelationshipType | "all")}
        >
          <SelectTrigger className="h-7 w-36 bg-muted/40 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all" className="text-xs">
              All types
            </SelectItem>
            {RELATIONSHIP_TYPES.filter(
              (t) => !DERIVED_RELATIONSHIPS.includes(t)
            ).map((t) => (
              <SelectItem key={t} value={t} className="text-xs">
                {humanize(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {rows.length} of {total}
        </span>
      </div>

      <ul className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border">
        {rows.map((r, i) => {
          const meta = ENTITY_TYPE_META[r.entity.entityType];
          const rawRole =
            typeof r.attributes?.role === "string" ? r.attributes.role : null;
          const role = rawRole
            ? r.direction === "in"
              ? (FAMILY_ROLE_INVERSE[rawRole] ?? rawRole)
              : rawRole
            : null;
          return (
            <li key={`${r.entity.id}-${i}`}>
              <Link
                href={`/entities/${r.entity.id}`}
                className="flex items-center gap-2.5 px-3 py-2 text-xs transition-colors hover:bg-muted/30"
              >
                <meta.Icon
                  size={13}
                  className={cn("shrink-0", meta.textClass)}
                />
                <span className="min-w-0 flex-1 truncate font-medium text-foreground">
                  {r.entity.displayName}
                </span>
                <span className="shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
                  {r.direction === "in" ? "← " : ""}
                  {role ?? humanize(r.relationshipType)}
                </span>
                {typeof r.weight === "number" && (
                  <span
                    className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] font-semibold text-muted-foreground"
                    title="messages exchanged"
                  >
                    {r.weight.toLocaleString()}
                  </span>
                )}
                {typeof r.mentionCount === "number" &&
                  r.entity.entityType === "selector" && (
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {r.mentionCount.toLocaleString()} mentions
                    </span>
                  )}
              </Link>
            </li>
          );
        })}
      </ul>

      {hasNextPage && (
        <div className="flex justify-center">
          <Button
            variant="ghost"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="text-xs text-primary"
          >
            {isFetchingNextPage && (
              <Loader2 size={12} className="mr-2 animate-spin" />
            )}
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}

function Seg<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex overflow-hidden rounded-md border border-border">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            "px-2 py-1 text-xs font-medium transition-colors",
            value === o.value
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** "parent of Ivan Petrovich Sidorov", read from `entityId`'s side of the suggested edge. */
function suggestionPhrase(s: RelationshipSuggestion, entityId: string) {
  const outgoing = s.srcEntityId === entityId;
  const role = s.attributes?.role;
  const relation =
    s.relationshipType === "familyOf" && role
      ? (outgoing ? role : (FAMILY_ROLE_INVERSE[role] ?? role)).replace(
          "_",
          " / "
        )
      : humanize(s.relationshipType).toLowerCase();
  return {
    relation,
    otherId: outgoing ? s.dstEntityId : s.srcEntityId,
    otherName: (outgoing ? s.dstName : s.srcName) ?? "unknown",
  };
}

/** Suggested edges for this entity (e.g. a parent read from a patronymic): accept makes them real. */
export function RelationshipSuggestions({ entityId }: { entityId: string }) {
  const { data } = useRelationshipSuggestions(entityId);
  const resolve = useResolveRelationshipSuggestion();
  const suggestions = data?.data ?? [];
  if (suggestions.length === 0) return null;
  return (
    <div className="mb-3 rounded-lg border border-annotation/30 bg-annotation/[0.04] p-3">
      <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium">
        <Sparkles size={12} className="text-annotation" /> Suggested
        relationships
      </p>
      <ul className="space-y-1">
        {suggestions.map((s) => {
          const { relation, otherId, otherName } = suggestionPhrase(
            s,
            entityId
          );
          return (
            <li
              key={s.id}
              className="flex flex-wrap items-center gap-2 text-xs"
            >
              <span className="text-muted-foreground">{relation} of</span>
              <Link
                href={`/entities/${otherId}`}
                className="font-medium text-foreground hover:underline"
              >
                {otherName}
              </Link>
              {s.explanation?.reason && (
                <span className="truncate rounded-full border border-annotation/40 px-1.5 text-[11px] text-annotation">
                  {s.explanation.reason}
                </span>
              )}
              <span className="ml-auto flex items-center gap-1">
                <Button
                  size="sm"
                  disabled={resolve.isPending}
                  className="h-6 gap-1 px-2 text-[11px]"
                  onClick={() =>
                    resolve.mutate({ id: s.id, status: "confirmed" })
                  }
                >
                  <Check size={11} /> Accept
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={resolve.isPending}
                  className="h-6 gap-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
                  onClick={() =>
                    resolve.mutate({ id: s.id, status: "rejected" })
                  }
                >
                  <X size={11} /> Reject
                </Button>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
