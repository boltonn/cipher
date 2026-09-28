"use client";

import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { FeatureChip } from "@/features/entities/components/resolution-feature-chip";
import {
  useEntityMergeCandidates,
  useMergeGroups,
  useResolveMatch,
} from "@/features/entities/hooks/use-entity-matches";
import type { EntityMatch, EntityMergeGroup, EntityType } from "@/features/entities/types";
import { useMe } from "@/features/users/hooks/use-me";
import { cn } from "@/lib/utils";
import { ArrowRight, GitMerge, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

/**
 * Entity->entity merge review, shown at the top of the Resolve tab. Each card is
 * a provisional entity the resolver minted (a stub with no Persons entry) next
 * to the canonical entities it may actually be. Merge folds the stub in; Keep
 * separate records that they're different.
 */
export function EntityMergeList({
  datasetId,
  reviewedBy,
}: {
  datasetId: string;
  reviewedBy: string;
}) {
  const [page, setPage] = useState(1);
  const { data, isPending } = useMergeGroups({
    datasetId,
    status: "pending",
    page,
  });
  const groups = data?.data ?? [];
  const total = data?.total ?? 0;

  if (isPending || groups.length === 0) return null;

  return (
    <details open className="rounded-lg border border-annotation/30 bg-annotation/[0.04]">
      <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-xs font-medium">
        <GitMerge size={13} className="text-annotation" />
        Possible duplicate entities
        <span className="rounded-full bg-annotation/20 px-1.5 text-[10px] text-annotation">
          {total}
        </span>
        <span className="font-normal text-muted-foreground">
          — resolver-made stubs that may already exist as a real entity
        </span>
      </summary>

      <div className="space-y-2 px-3 pb-3">
        {groups.map((g) => (
          <MergeCard
            key={g.provisionalEntityId}
            group={g}
            reviewedBy={reviewedBy}
          />
        ))}
        {total > groups.length && (
          <div className="flex items-center justify-end gap-2 pt-1 text-[11px]">
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[11px]"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Prev
            </Button>
            <span className="text-muted-foreground">page {page}</span>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[11px]"
              disabled={page * 25 >= total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </details>
  );
}

/**
 * "Possible duplicates" panel for a single entity's dossier page. Renders
 * nothing unless `dedupe-entities` filed merge proposals against this entity
 * (i.e. it's a provisional stub).
 */
export function EntityMergePanel({ entityId }: { entityId: string }) {
  const me = useMe().data;
  const reviewedBy = me?.name ?? me?.id ?? "analyst";
  const { data: candidates, isPending } = useEntityMergeCandidates(entityId);
  const resolve = useResolveMatch();
  const pending = (candidates ?? []).filter((c) => c.status === "pending");

  if (isPending || pending.length === 0) return null;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="rounded-lg border border-annotation/30 bg-annotation/[0.04] p-3">
        <p className="flex items-center gap-2 text-xs font-medium">
          <GitMerge size={13} className="text-annotation" />
          This looks like an existing entity
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          The resolver created this entity because no canonical match was found at
          the time. Merge it into the real one, or keep them separate.
        </p>
        <ul className="mt-2 space-y-1.5">
          {pending.map((c) => (
            <MergeCandidateRow
              key={c.id}
              match={c}
              disabled={resolve.isPending}
              onMerge={() =>
                resolve.mutate({
                  matchId: c.id,
                  status: "confirmed",
                  reviewedBy,
                })
              }
              onKeep={() =>
                resolve.mutate({
                  matchId: c.id,
                  status: "rejected",
                  reviewedBy,
                })
              }
            />
          ))}
        </ul>
      </div>
    </TooltipProvider>
  );
}

function MergeCard({
  group,
  reviewedBy,
}: {
  group: EntityMergeGroup;
  reviewedBy: string;
}) {
  const resolve = useResolveMatch();
  const busy = resolve.isPending;
  const stubMeta = ENTITY_TYPE_META[group.provisionalEntityType as EntityType];

  return (
    <div className="rounded-lg border border-border bg-card p-2.5">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        {stubMeta?.Icon && (
          <stubMeta.Icon size={13} className={cn("shrink-0", stubMeta.textClass)} />
        )}
        <Link
          href={`/entities/${group.provisionalEntityId}`}
          className="font-medium hover:underline"
        >
          {group.provisionalName}
        </Link>
        <span className="rounded-full border border-border px-1 text-[9px] text-muted-foreground">
          provisional · {group.mentionCount.toLocaleString()} mentions
        </span>
      </p>

      <ul className="mt-2 space-y-1.5">
        {group.candidates.map((c) => (
          <MergeCandidateRow
            key={c.id}
            match={c}
            disabled={busy}
            onMerge={() =>
              resolve.mutate({
                matchId: c.id,
                status: "confirmed",
                reviewedBy,
              })
            }
            onKeep={() =>
              resolve.mutate({
                matchId: c.id,
                status: "rejected",
                reviewedBy,
              })
            }
          />
        ))}
      </ul>
    </div>
  );
}

function MergeCandidateRow({
  match,
  disabled,
  onMerge,
  onKeep,
}: {
  match: EntityMatch;
  disabled?: boolean;
  onMerge: () => void;
  onKeep: () => void;
}) {
  const meta = match.entityType
    ? ENTITY_TYPE_META[match.entityType as EntityType]
    : undefined;
  const Icon = meta?.Icon;
  const href =
    match.entityType === "person" && match.entityPersonId
      ? `/persons/${match.entityPersonId}`
      : `/entities/${match.entityId}`;
  const features = (match.explanation?.features ?? [])
    .filter((f) => f.level !== "none")
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));

  return (
    <li className="rounded-md border border-border/60 bg-muted/30 p-2">
      <div className="flex items-center gap-2 text-xs">
        <ArrowRight size={12} className="shrink-0 text-muted-foreground" />
        {Icon && <Icon size={13} className={cn("shrink-0", meta?.textClass)} />}
        <Link href={href} className="truncate font-medium hover:underline" title="Open this entity">
          {match.entityName ?? match.entityId.slice(0, 8)}
        </Link>
        <span className="shrink-0 text-[9px] uppercase tracking-widest text-muted-foreground/70">
          {meta?.label ?? "entity"}
        </span>
        <span className="ml-auto shrink-0 text-[10px] tabular-nums text-muted-foreground">
          {match.similarityScore.toFixed(2)}
        </span>
      </div>

      {features.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {features.map((f) => (
            <FeatureChip key={f.name} feature={f} />
          ))}
        </div>
      )}

      <div className="mt-2 flex items-center gap-1.5">
        <Button
          size="sm"
          disabled={disabled}
          onClick={onMerge}
          className="h-6 gap-1 px-2 text-[10px]"
        >
          <GitMerge size={11} /> Merge into this
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={onKeep}
          className="h-6 gap-1 px-2 text-[10px] text-muted-foreground hover:text-foreground"
        >
          <X size={11} /> Keep separate
        </Button>
      </div>
    </li>
  );
}
