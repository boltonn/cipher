"use client";

import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { FeatureChip } from "@/features/entities/components/resolution-feature-chip";
import { useEntitySearch } from "@/features/entities/hooks/use-entities";
import {
  useResolveMatch,
  useResolveMatchesBatch,
} from "@/features/entities/hooks/use-entity-matches";
import {
  useDismissNameGroup,
  useResolveNameGroup,
  useUnresolvedNameGroups,
} from "@/features/entities/hooks/use-mentions";
import type {
  EntityMatch,
  EntityType,
  UnresolvedNameGroup,
} from "@/features/entities/types";
import { mentionSearchHref } from "@/features/search/links";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import {
  Building2,
  Check,
  HelpCircle,
  Loader2,
  MapPin,
  Search,
  Sparkles,
  TriangleAlert,
  User,
  X,
  TextSearch,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

const PAGE_SIZE = 25;
const CLEAN_MIN = 0.95;
const GUIDE_HREF = "/entities/resolution-guide";

type QueueFilter = "all" | "suggested" | "new";

const FILTERS: {
  value: QueueFilter;
  label: string;
  hasResolution?: boolean;
}[] = [
  { value: "all", label: "All names" },
  { value: "suggested", label: "Has a suggested entity", hasResolution: true },
  { value: "new", label: "No entity yet", hasResolution: false },
];

const CREATE_TYPES: { type: EntityType; label: string; Icon: typeof User }[] = [
  { type: "person", label: "Person", Icon: User },
  { type: "organization", label: "Organization", Icon: Building2 },
  { type: "location", label: "Location", Icon: MapPin },
];

/** A suggestion safe to accept in bulk: high score, no conflicting feature, a verified entity. */
function isClean(group: UnresolvedNameGroup): boolean {
  const top = group.resolutions[0];
  return (
    !!top &&
    top.similarityScore >= CLEAN_MIN &&
    !top.entityIsProvisional &&
    !(top.explanation?.features ?? []).some((f) => f.level === "conflict")
  );
}

/**
 * The Resolve queue -- one card per name group (every unresolved mention of one name).
 * For each, decide which entity the name refers to: accept or reject a suggested
 * resolution, resolve it to another existing entity, create a new entity, or mark it
 * "not an entity". Every decision applies to all of the group's mentions at once.
 */
export function NameResolutionQueue({
  datasetId,
  focus,
  onClearFocus,
}: {
  datasetId: string;
  /** narrow to names with a pending resolution to this entity (its "N to resolve" badge) */
  focus?: { id: string; name: string } | null;
  onClearFocus?: () => void;
}) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<QueueFilter>("all");
  const [page, setPage] = useState(1);
  const { data, isPending, isFetching } = useUnresolvedNameGroups({
    datasetId,
    q,
    hasResolution: FILTERS.find((f) => f.value === filter)?.hasResolution,
    entityId: focus?.id,
    page,
  });
  const groups = data?.data ?? [];
  const total = data?.total ?? 0;
  const clean = groups.filter(isClean);
  const batch = useResolveMatchesBatch();
  const returnToAll = () => {
    toast.success(`Every name suggested for ${focus?.name} is resolved`);
    onClearFocus?.();
  };
  const onLastDecided = focus && total <= 1 ? returnToAll : undefined;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="space-y-3">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Each card is a <b>name group</b> — every unresolved mention of one
          name. Decide which <b>entity</b> it refers to: <b>Accept</b> a
          suggested resolution, <b>Reject</b> it, resolve to{" "}
          <b>another entity</b>, <b>create a new entity</b>, or mark it{" "}
          <b>not an entity</b>. The decision applies to all of the group&apos;s
          mentions.{" "}
          <Link
            href={GUIDE_HREF}
            className="inline-flex items-center gap-0.5 text-primary hover:underline"
          >
            <HelpCircle size={11} /> How resolution works
          </Link>
        </p>

        {focus && (
          <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-1.5 text-[11px]">
            Names suggested for <b className="text-foreground">{focus.name}</b>
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto h-6 px-2 text-[11px]"
              onClick={onClearFocus}
            >
              Show all names
            </Button>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <SearchBarShell
            isActive={isFetching}
            icon={<Search size={16} strokeWidth={1.5} />}
            className="w-auto min-w-64 flex-1"
          >
            <SearchInput
              value={q}
              onSearch={(value) => {
                setQ(value);
                setPage(1);
              }}
              ariaLabel="Search names"
              placeholder="Search names…"
            />
          </SearchBarShell>
          <ButtonGroup>
            {FILTERS.map((f) => (
              <Button
                key={f.value}
                size="sm"
                variant={filter === f.value ? "default" : "outline"}
                className="h-7 text-[11px]"
                onClick={() => {
                  setFilter(f.value);
                  setPage(1);
                }}
              >
                {f.label}
              </Button>
            ))}
          </ButtonGroup>
          {clean.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              disabled={batch.isPending}
              className="ml-auto h-7 gap-1 border-annotation/40 text-[11px] text-annotation hover:text-annotation"
              onClick={() =>
                batch.mutate(
                  {
                    decisions: clean.map((g) => ({
                      matchId: g.resolutions[0].id,
                      status: "confirmed",
                    })),
                  },
                  {
                    onSuccess:
                      focus && clean.length >= total ? returnToAll : undefined,
                  }
                )
              }
              title="Accept the top suggestion on this page where it scores ≥ 0.95, has no conflict, and is a verified entity"
            >
              <Check size={12} /> Accept {clean.length} clear match
              {clean.length === 1 ? "" : "es"}
            </Button>
          )}
        </div>

        {isPending ? (
          <div className="flex items-center gap-2 py-10 text-xs text-muted-foreground">
            <Loader2 size={14} className="animate-spin" /> Loading names…
          </div>
        ) : groups.length === 0 ? (
          <div className="py-10 text-center text-xs italic text-muted-foreground">
            {focus && !q && filter === "all" ? (
              <>
                Nothing left to resolve for {focus.name}.{" "}
                <Button
                  size="sm"
                  variant="link"
                  className="h-auto p-0 text-xs"
                  onClick={onClearFocus}
                >
                  Show all names
                </Button>
              </>
            ) : q || filter !== "all" || focus ? (
              "No names match."
            ) : (
              "Nothing to resolve — every name is resolved."
            )}
          </div>
        ) : (
          <>
            <ul className="space-y-2">
              {groups.map((g) => (
                <NameGroupCard
                  key={g.normalizedValue}
                  group={g}
                  datasetId={datasetId}
                  onDecided={onLastDecided}
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
      </div>
    </TooltipProvider>
  );
}

function NameGroupCard({
  group,
  datasetId,
  onDecided,
}: {
  group: UnresolvedNameGroup;
  datasetId: string;
  /** called after any decision on this card succeeds */
  onDecided?: () => void;
}) {
  const done = { onSuccess: onDecided };
  const decide = useResolveMatch();
  const create = useResolveNameGroup();
  const dismiss = useDismissNameGroup();
  const busy = decide.isPending || create.isPending || dismiss.isPending;
  const suggestedType =
    (group.resolutions[0]?.entityType as EntityType | undefined) ??
    group.suggestedType;

  return (
    <li className="rounded-lg border border-border bg-card p-3">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="rounded bg-annotation/15 px-1 font-mono text-foreground">
          {group.surface}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {group.mentionCount.toLocaleString()} mention
          {group.mentionCount === 1 ? "" : "s"} ·{" "}
          {group.fileCount.toLocaleString()} file
          {group.fileCount === 1 ? "" : "s"}
        </span>
        {group.suggestedType && (
          <span className="rounded-full border border-border/60 px-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
            looks like {group.suggestedType}
          </span>
        )}
        <Link
          href={mentionSearchHref(group.normalizedValue, datasetId)}
          className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          title="Open every mention of this name in its text -- fix spans or resolve one by one"
        >
          <TextSearch size={11} /> Review in text
        </Link>
      </p>
      {group.sampleContext && (
        <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground [overflow-wrap:anywhere]">
          …{group.sampleContext}…
        </p>
      )}

      {group.resolutions.length > 0 && (
        <>
          <p className="mt-2 text-[11px] font-medium text-muted-foreground">
            Suggested resolution
          </p>
          <ul className="mt-1 space-y-1.5">
            {group.resolutions.map((r, index) => (
              <ResolutionRow
                key={r.id}
                resolution={r}
                primary={index === 0}
                disabled={busy}
                onAccept={() =>
                  decide.mutate({ matchId: r.id, status: "confirmed" }, done)
                }
                onReject={() =>
                  decide.mutate({ matchId: r.id, status: "rejected" }, done)
                }
              />
            ))}
          </ul>
        </>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-border/60 pt-2">
        <span className="text-[11px] text-muted-foreground">
          {group.resolutions.length ? "Or create a new" : "Create a new"}
        </span>
        {CREATE_TYPES.map(({ type, label, Icon }) => (
          <Button
            key={type}
            size="sm"
            variant={
              !group.resolutions.length && suggestedType === type
                ? "default"
                : "outline"
            }
            disabled={busy}
            onClick={() =>
              create.mutate(
                {
                  datasetId,
                  normalizedValue: group.normalizedValue,
                  entityType: type,
                  displayName: group.surface,
                },
                done
              )
            }
            className="h-7 gap-1 text-[11px]"
          >
            <Icon size={12} />
            {label}
          </Button>
        ))}
        <ResolveToExisting
          datasetId={datasetId}
          surface={group.surface}
          disabled={busy}
          onPick={(entityId, entityType) =>
            create.mutate(
              {
                datasetId,
                normalizedValue: group.normalizedValue,
                entityType,
                entityId,
              },
              done
            )
          }
        />
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() =>
            dismiss.mutate(
              { datasetId, normalizedValue: group.normalizedValue },
              done
            )
          }
          className="ml-auto h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
        >
          <X size={12} /> Not an entity
        </Button>
      </div>
    </li>
  );
}

function ResolutionRow({
  resolution,
  primary,
  disabled,
  onAccept,
  onReject,
}: {
  resolution: EntityMatch;
  primary: boolean;
  disabled?: boolean;
  onAccept: () => void;
  onReject: () => void;
}) {
  const meta = resolution.entityType
    ? ENTITY_TYPE_META[resolution.entityType as EntityType]
    : undefined;
  const features = (resolution.explanation?.features ?? [])
    .filter((f) => f.level !== "none")
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  const autoCreated = resolution.entityIsProvisional === true;
  const pendingMerges = resolution.entityPendingMergeCount ?? 0;
  const pct = Math.round(resolution.similarityScore * 100);

  return (
    <li
      className={cn(
        "rounded-md border p-2",
        primary ? "border-border bg-muted/40" : "border-border/50"
      )}
    >
      <div className="flex items-center gap-2 text-xs">
        {meta?.Icon && (
          <meta.Icon
            size={13}
            className={cn("shrink-0", meta.textClass)}
            aria-hidden
          />
        )}
        <Link
          href={`/entities/${resolution.entityId}`}
          className="truncate font-medium text-foreground hover:underline"
          title="Open this entity"
        >
          {resolution.entityName ?? resolution.entityId.slice(0, 8)}
        </Link>
        {meta && (
          <span className="shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground/70">
            {meta.label}
          </span>
        )}
        {autoCreated && (
          <span
            className="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-annotation/40 px-1 text-[11px] text-annotation"
            title="Auto-created by the resolver and not verified yet — check it on the Verify tab"
          >
            <Sparkles size={9} /> auto-created
          </span>
        )}
        <span className="ml-auto shrink-0 text-[11px] tabular-nums text-muted-foreground">
          {pct}%
        </span>
        <Button
          size="sm"
          variant={primary && pct >= 90 ? "default" : "outline"}
          disabled={disabled}
          onClick={onAccept}
          className="h-6 gap-1 px-2 text-[11px]"
        >
          <Check size={11} /> Accept
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={onReject}
          className="h-6 gap-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
        >
          <X size={11} /> Reject
        </Button>
      </div>
      {features.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {features.map((f) => (
            <FeatureChip key={f.name} feature={f} />
          ))}
        </div>
      )}
      {autoCreated && pendingMerges > 0 && (
        <p className="mt-1.5 flex items-center gap-1 text-[11px] text-annotation">
          <TriangleAlert size={11} className="shrink-0" />
          This entity may duplicate {pendingMerges} other
          {pendingMerges === 1 ? "" : "s"} —{" "}
          <Link
            href={`/entities/${resolution.entityId}`}
            className="font-medium hover:underline"
          >
            review the merge first
          </Link>
        </p>
      )}
    </li>
  );
}

function ResolveToExisting({
  datasetId,
  surface,
  disabled,
  onPick,
}: {
  datasetId: string;
  surface: string;
  disabled?: boolean;
  onPick: (entityId: string, entityType: EntityType) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(surface.trim().slice(0, 80));
  const debouncedQuery = useDebounce(query, 250);
  const { data: results, isFetching } = useEntitySearch(
    { datasetId, q: debouncedQuery },
    open
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled}
          className="h-7 text-[11px]"
        >
          Another entity…
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 border-border bg-popover p-0" align="end">
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Find an existing entity…"
            className="text-xs"
          />
          <CommandList className="max-h-48">
            {isFetching && (
              <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-muted-foreground">
                <Loader2 size={12} className="animate-spin" /> Searching…
              </div>
            )}
            {!isFetching && (results?.length ?? 0) === 0 && (
              <CommandEmpty className="py-3 text-[11px] text-muted-foreground">
                No matches.
              </CommandEmpty>
            )}
            <CommandGroup>
              {results?.map((r) => {
                const meta = ENTITY_TYPE_META[r.entityType];
                return (
                  <CommandItem
                    key={r.id}
                    value={r.id}
                    onSelect={() => {
                      onPick(r.id, r.entityType);
                      setOpen(false);
                    }}
                    className="gap-2 text-xs"
                  >
                    <meta.Icon size={12} className={meta.textClass} />
                    <span className="flex-1 truncate">{r.displayName}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
