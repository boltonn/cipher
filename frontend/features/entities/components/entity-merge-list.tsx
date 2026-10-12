"use client";

import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { FeatureChip } from "@/features/entities/components/resolution-feature-chip";
import { InvalidateEntityDialog } from "@/features/entities/components/invalidate-entity-dialog";
import {
  useEntityMergeCandidates,
  usePromoteEntity,
  useResolveMatch,
} from "@/features/entities/hooks/use-entity-matches";
import type {
  Entity,
  EntityMatch,
  EntityType,
} from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { ArrowRight, Ban, BadgeCheck, GitMerge, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

/**
 * "Possible duplicates" panel for a single entity's dossier page. Renders
 * nothing unless `dedupe-entities` filed merge proposals against this entity
 * (i.e. it's a provisional stub).
 */
export function EntityMergePanel({ entity }: { entity: Entity }) {
  const { data: candidates, isPending } = useEntityMergeCandidates(entity.id);
  const resolve = useResolveMatch();
  const pending = (candidates ?? []).filter((c) => c.status === "pending");

  if (!entity.isProvisional || isPending) return null;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="rounded-lg border border-annotation/30 bg-annotation/[0.04] p-3">
        <p className="flex items-center gap-2 text-xs font-medium">
          <GitMerge size={13} className="text-annotation" />
          {pending.length > 0
            ? "This looks like an existing entity"
            : "Auto-created entity"}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          The resolver created this entity because no canonical match was found
          at the time.{" "}
          {pending.length > 0
            ? "Merge it into the existing one (its name becomes an alias), or verify it if it's someone new."
            : "Verify it if it's a real, distinct entity."}
        </p>
        <StubActions entity={entity} className="mt-2" />
        <ul className="mt-2 space-y-1.5 empty:hidden">
          {pending.map((c) => (
            <MergeCandidateRow
              key={c.id}
              match={c}
              disabled={resolve.isPending}
              onMerge={() =>
                resolve.mutate({
                  matchId: c.id,
                  status: "confirmed",
                })
              }
              onKeep={() =>
                resolve.mutate({
                  matchId: c.id,
                  status: "rejected",
                })
              }
            />
          ))}
        </ul>
      </div>
    </TooltipProvider>
  );
}

/** Stub-level decisions: a new canonical entity, or not an entity at all. */
function StubActions({
  entity,
  className,
}: {
  entity: Pick<Entity, "id" | "displayName" | "entityType">;
  className?: string;
}) {
  const promote = usePromoteEntity();
  const [invalidating, setInvalidating] = useState(false);
  const noun = entity.entityType === "person" ? "person" : "entity";

  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <Button
        size="sm"
        variant="outline"
        disabled={promote.isPending}
        onClick={() => promote.mutate(entity.id)}
        className="h-6 gap-1 px-2 text-[11px]"
        title={`None of these — keep it as a new ${noun}`}
      >
        <BadgeCheck size={11} /> Verify as new {noun}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => setInvalidating(true)}
        className="h-6 gap-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
      >
        <Ban size={11} /> Not an entity
      </Button>
      <InvalidateEntityDialog
        entity={entity}
        open={invalidating}
        onOpenChange={setInvalidating}
      />
    </span>
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
        <Link
          href={href}
          className="truncate font-medium hover:underline"
          title="Open this entity"
        >
          {match.entityName ?? match.entityId.slice(0, 8)}
        </Link>
        <span className="shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground/70">
          {meta?.label ?? "entity"}
        </span>
        {match.matchMethod === "assistant" ? (
          <span className="ml-auto shrink-0 rounded-full bg-annotation/15 px-1.5 text-[11px] text-annotation">
            suggested from chat
          </span>
        ) : (
          <span className="ml-auto shrink-0 text-[11px] tabular-nums text-muted-foreground">
            {match.similarityScore.toFixed(2)}
          </span>
        )}
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
          className="h-6 gap-1 px-2 text-[11px]"
        >
          <GitMerge size={11} /> Merge into this
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={onKeep}
          className="h-6 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
        >
          <X size={11} /> Keep separate
        </Button>
      </div>
    </li>
  );
}
