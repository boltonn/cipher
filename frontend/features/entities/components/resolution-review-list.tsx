"use client";

import { Pagination } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Checkbox } from "@/components/ui/checkbox";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { EntityMergeList } from "@/features/entities/components/entity-merge-list";
import { FeatureChip } from "@/features/entities/components/resolution-feature-chip";
import {
  useDismissMatchNameGroup,
  useMatchGroups,
  useResolveMatch,
  useResolveMatchesBatch,
} from "@/features/entities/hooks/use-entity-matches";
import type {
  EntityMatch,
  EntityMatchGroup,
  EntityMatchStatus,
  EntityType,
} from "@/features/entities/types";
import { useMe } from "@/features/users/hooks/use-me";
import { cn } from "@/lib/utils";
import { Check, HelpCircle, Loader2, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

const PAGE_SIZE = 25;
const CLEAN_MIN = 0.95;
const GUIDE_HREF = "/entities/resolution-guide";

type SortBy = "similarity_score" | "date_created";

function isClean(g: EntityMatchGroup): boolean {
  return (
    g.top.similarityScore >= CLEAN_MIN &&
    !(g.top.explanation?.features ?? []).some((f) => f.level === "conflict")
  );
}

export function ResolutionReviewList({ datasetId }: { datasetId: string }) {
  const me = useMe().data;
  const reviewedBy = me?.name ?? me?.id ?? "analyst";

  const [status, setStatus] = useState<EntityMatchStatus>("pending");
  const [sortBy, setSortBy] = useState<SortBy>("similarity_score");
  const [minSimilarity, setMinSimilarity] = useState<number | undefined>(
    undefined
  );
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data, isPending, isFetching } = useMatchGroups({
    datasetId,
    status,
    sortBy,
    minSimilarity,
    page,
  });
  const groups = useMemo(() => data?.data ?? [], [data]);
  const total = data?.total ?? 0;

  const batch = useResolveMatchesBatch(() => setSelected(new Set()));

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectClean = () =>
    setSelected(new Set(groups.filter(isClean).map((g) => g.top.id)));

  const submitBatch = (decision: EntityMatchStatus) =>
    batch.mutate({
      reviewedBy,
      decisions: [...selected].map((matchId) => ({
        matchId,
        status: decision,
      })),
    });

  const setFilter = (fn: () => void) => {
    fn();
    setPage(1);
    setSelected(new Set());
  };

  return (
    <TooltipProvider delayDuration={150}>
      <div className="space-y-3">
        <div className="rounded-lg border border-border/60 bg-muted/30 p-3 text-[11px] leading-relaxed text-muted-foreground">
          <p>
            The resolver found existing <b>entities</b> that each of these{" "}
            <b>names</b> might be, and scored them. The name in the{" "}
            <span className="rounded bg-annotation/15 px-1 font-mono text-foreground">
              amber box
            </span>{" "}
            is an unmatched name (every mention of it counted together); the rows
            beneath it are entities that already exist. Chips explain{" "}
            <span className="text-annotation">why</span> — a red chip is a
            conflict that ruled a look-alike out.{" "}
            <b>Confirm</b> attaches every mention of that name to the entity;{" "}
            <b>None of these</b> rejects them all and sends the name to the
            Review tab for manual classification.
          </p>
          <Link
            href={GUIDE_HREF}
            className="mt-1.5 inline-flex items-center gap-1 font-medium text-foreground hover:underline"
          >
            <HelpCircle size={12} />
            How resolution works
          </Link>
        </div>

        <EntityMergeList datasetId={datasetId} reviewedBy={reviewedBy} />

        <div className="flex flex-wrap items-center gap-2">
          <ButtonGroup>
            {(["pending", "confirmed", "rejected"] as const).map((s) => (
              <Button
                key={s}
                size="sm"
                variant={status === s ? "default" : "outline"}
                className="h-7 text-[11px] capitalize"
                onClick={() => setFilter(() => setStatus(s))}
              >
                {s}
              </Button>
            ))}
          </ButtonGroup>

          <ButtonGroup>
            <Button
              size="sm"
              variant={sortBy === "similarity_score" ? "default" : "outline"}
              className="h-7 text-[11px]"
              onClick={() => setFilter(() => setSortBy("similarity_score"))}
            >
              Confidence
            </Button>
            <Button
              size="sm"
              variant={sortBy === "date_created" ? "default" : "outline"}
              className="h-7 text-[11px]"
              onClick={() => setFilter(() => setSortBy("date_created"))}
            >
              Most mentions
            </Button>
          </ButtonGroup>

          <ButtonGroup>
            {[
              { label: "All", v: undefined },
              { label: "≥ 0.90", v: 0.9 },
              { label: "≥ 0.95", v: 0.95 },
            ].map(({ label, v }) => (
              <Button
                key={label}
                size="sm"
                variant={minSimilarity === v ? "default" : "outline"}
                className="h-7 text-[11px]"
                onClick={() => setFilter(() => setMinSimilarity(v))}
              >
                {label}
              </Button>
            ))}
          </ButtonGroup>

          {status === "pending" && groups.some(isClean) && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-[11px] text-annotation hover:text-annotation"
              onClick={selectClean}
            >
              Select clean ({groups.filter(isClean).length})
            </Button>
          )}
        </div>

        {isPending ? (
          <div className="flex items-center gap-2 py-10 text-xs text-muted-foreground">
            <Loader2 size={14} className="animate-spin" /> Loading candidates…
          </div>
        ) : groups.length === 0 ? (
          <p className="py-10 text-center text-xs italic text-muted-foreground">
            {status === "pending"
              ? "Nothing to review — no scored candidates are pending."
              : `No ${status} name groups.`}
          </p>
        ) : (
          <>
            <ul className="space-y-2">
              {groups.map((g) => (
                <GroupCard
                  key={g.normalizedValue}
                  group={g}
                  datasetId={datasetId}
                  reviewedBy={reviewedBy}
                  checked={selected.has(g.top.id)}
                  onToggle={() => toggle(g.top.id)}
                />
              ))}
            </ul>
            <Pagination
              currentPage={page}
              totalItems={total}
              itemsPerPage={PAGE_SIZE}
              onPageChange={setPage}
              isLoading={isFetching}
            />
          </>
        )}

        {selected.size > 0 && (
          <div className="sticky bottom-3 z-10 mx-auto flex w-fit items-center gap-2 rounded-full border border-border bg-popover px-3 py-1.5 shadow-lg">
            <span className="text-[11px] text-muted-foreground">
              {selected.size} selected
            </span>
            <Button
              size="sm"
              className="h-7 gap-1 text-[11px]"
              disabled={batch.isPending}
              onClick={() => submitBatch("confirmed")}
            >
              {batch.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Check size={12} />
              )}
              Confirm all
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-[11px]"
              disabled={batch.isPending}
              onClick={() => submitBatch("rejected")}
            >
              <X size={12} />
              Reject all
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-[11px] text-muted-foreground"
              onClick={() => setSelected(new Set())}
            >
              Clear
            </Button>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}

function GroupCard({
  group,
  datasetId,
  reviewedBy,
  checked,
  onToggle,
}: {
  group: EntityMatchGroup;
  datasetId: string;
  reviewedBy: string;
  checked: boolean;
  onToggle: () => void;
}) {
  const resolve = useResolveMatch();
  const dismiss = useDismissMatchNameGroup();
  const busy = resolve.isPending || dismiss.isPending;
  const candidates = [group.top, ...group.alternatives];
  const pending = group.status === "pending";

  return (
    <li className="rounded-xl border border-border p-3">
      <div className="flex items-start gap-2">
        {pending && (
          <Checkbox
            checked={checked}
            onCheckedChange={onToggle}
            aria-label={`Select ${group.surface}`}
            className="mt-0.5"
          />
        )}
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <span className="text-[9px] uppercase tracking-widest text-muted-foreground/70">
              name
            </span>
            <span className="rounded bg-annotation/15 px-1 font-mono text-foreground">
              {group.surface}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {group.mentionCount.toLocaleString()} mention
              {group.mentionCount === 1 ? "" : "s"} ·{" "}
              {group.fileCount.toLocaleString()} file
              {group.fileCount === 1 ? "" : "s"}
            </span>
            {!pending && (
              <span
                className={cn(
                  "rounded-full border px-1.5 py-0.5 text-[9px] uppercase tracking-widest",
                  group.status === "confirmed"
                    ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
                    : "border-destructive/40 text-destructive"
                )}
              >
                {group.status}
              </span>
            )}
          </p>

          <ul className="mt-2 space-y-1.5">
            {candidates.map((c, i) => (
              <CandidateRow
                key={c.id}
                match={c}
                primary={i === 0}
                disabled={busy || !pending}
                onConfirm={() =>
                  resolve.mutate({
                    matchId: c.id,
                    status: "confirmed",
                    reviewedBy,
                  })
                }
                onReject={() =>
                  resolve.mutate({
                    matchId: c.id,
                    status: "rejected",
                    reviewedBy,
                  })
                }
              />
            ))}
          </ul>

          {pending && (
            <div className="mt-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() =>
                  dismiss.mutate({
                    datasetId,
                    normalizedValue: group.normalizedValue,
                    reviewedBy,
                  })
                }
                className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
              >
                <X size={12} />
                None of these
              </Button>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function CandidateRow({
  match,
  primary,
  disabled,
  onConfirm,
  onReject,
}: {
  match: EntityMatch;
  primary: boolean;
  disabled?: boolean;
  onConfirm: () => void;
  onReject: () => void;
}) {
  const pct = Math.round(match.similarityScore * 100);
  const features = (match.explanation?.features ?? [])
    .filter((f) => f.level !== "none")
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  const meta = match.entityType
    ? ENTITY_TYPE_META[match.entityType as EntityType]
    : undefined;
  const Icon = meta?.Icon;
  const auto = match.decisionSource === "system_auto";
  // A person entity with an explicit null personId is provisional -- the resolver
  // minted it on an earlier pass; no Persons-tab entry / face gallery yet.
  // `undefined` means the API didn't send the field (older backend) -- don't guess.
  const provisional =
    match.entityType === "person" && match.entityPersonId === null;
  const href =
    match.entityType === "person" && match.entityPersonId
      ? `/persons/${match.entityPersonId}`
      : `/entities/${match.entityId}`;

  return (
    <li
      className={cn(
        "rounded-lg border p-2",
        primary ? "border-border bg-muted/40" : "border-border/50"
      )}
    >
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs">
            {Icon && (
              <Icon
                size={13}
                className={cn("shrink-0", meta?.textClass)}
                aria-hidden
              />
            )}
            <Link
              href={href}
              className="truncate font-medium text-foreground hover:underline"
              title="Open this entity"
            >
              {match.entityName ?? match.entityId.slice(0, 8)}
            </Link>
            {meta && (
              <span className="shrink-0 text-[9px] uppercase tracking-widest text-muted-foreground/70">
                {provisional ? "provisional" : meta.label}
              </span>
            )}
            {provisional && (
              <span
                className="shrink-0 rounded-full border border-border px-1 text-[9px] text-muted-foreground"
                title="Created by the resolver — no Persons entry or faces yet. Confirming will merge these mentions into it."
              >
                no person page
              </span>
            )}
            {auto && (
              <span className="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-annotation/40 px-1 text-[9px] text-annotation">
                <Sparkles size={9} /> auto
              </span>
            )}
            <span className="ml-auto shrink-0 text-[10px] tabular-nums text-muted-foreground">
              {match.similarityScore.toFixed(2)}
            </span>
          </div>
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-border">
            <div
              className={cn(
                "h-full rounded-full",
                pct >= 92 ? "bg-annotation" : "bg-muted-foreground/50"
              )}
              style={{ width: `${Math.max(pct, 4)}%` }}
            />
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            disabled={disabled}
            onClick={onConfirm}
            className="h-6 gap-1 px-2 text-[10px]"
          >
            <Check size={11} /> Confirm
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={disabled}
            onClick={onReject}
            className="h-6 gap-1 px-2 text-[10px] text-muted-foreground hover:text-destructive"
          >
            <X size={11} />
          </Button>
        </div>
      </div>

      {features.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {features.map((f) => (
            <FeatureChip key={f.name} feature={f} />
          ))}
        </div>
      )}
    </li>
  );
}
