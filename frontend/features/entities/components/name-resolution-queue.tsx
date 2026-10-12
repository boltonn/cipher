"use client";

import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Checkbox } from "@/components/ui/checkbox";
import { CorrespondentBadge } from "./correspondent-badge";
import { SourceTagsToggle } from "./source-tags-toggle";
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
  useDismissNameGroups,
  useResolveNameGroup,
  useResolveNameGroups,
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
import { DatasetName } from "@/features/datasets/components/dataset-name";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

const PAGE_SIZE = 25;
const CLEAN_MIN = 0.95;
const SNIPPET_RADIUS = 90;
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

const groupKey = (group: UnresolvedNameGroup) =>
  `${group.datasetId}:${group.normalizedValue}`;

const escapeRegExp = (value: string) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The snippet cut around the first place the name is written in it (as a whole word), so the highlight is always visible. */
function snippetAround(context: string, names: (string | null | undefined)[]) {
  for (const name of names) {
    if (!name?.trim()) continue;
    const match = new RegExp(
      `(?<![\\p{L}\\p{N}])${escapeRegExp(name.trim())}(?![\\p{L}\\p{N}])`,
      "iu"
    ).exec(context);
    if (!match) continue;
    const at = match.index;
    const end = at + match[0].length;
    const from = Math.max(0, at - SNIPPET_RADIUS);
    const to = Math.min(context.length, end + SNIPPET_RADIUS);
    return {
      before: `${from > 0 ? "…" : ""}${context.slice(from, at)}`,
      name: match[0],
      after: `${context.slice(end, to)}${to < context.length ? "…" : ""}`,
    };
  }
  return null;
}

/**
 * The Resolve queue -- one card per name group (every unresolved mention of one name).
 * For each, decide which entity the name refers to: accept or reject a suggested
 * resolution, resolve it to another existing entity, create a new entity, or mark it
 * "not an entity". Every decision applies to all of the group's mentions at once.
 */
export function NameResolutionQueue({
  datasetIds,
  focus,
  onClearFocus,
}: {
  datasetIds: string[];
  /** narrow to names with a pending resolution to this entity (its "N to resolve" badge) */
  focus?: { id: string; name: string } | null;
  onClearFocus?: () => void;
}) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<QueueFilter>("all");
  const [excludeSourceTags, setExcludeSourceTags] = useState<string[]>();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Map<string, UnresolvedNameGroup>>(
    new Map()
  );
  const clearSelection = () => setSelected(new Map());
  const toggle = (group: UnresolvedNameGroup, checked: boolean) =>
    setSelected((current) => {
      const next = new Map(current);
      if (checked) next.set(groupKey(group), group);
      else next.delete(groupKey(group));
      return next;
    });
  const { data, isPending, isFetching } = useUnresolvedNameGroups({
    datasetIds,
    q,
    excludeSourceTags,
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
                clearSelection();
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
                  clearSelection();
                }}
              >
                {f.label}
              </Button>
            ))}
          </ButtonGroup>
          <SourceTagsToggle
            datasetIds={datasetIds}
            value={excludeSourceTags}
            onChange={(value) => {
              setExcludeSourceTags(value);
              setPage(1);
              clearSelection();
            }}
          />
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
            <SelectionBar
              groups={groups}
              selected={selected}
              onSelectAll={(checked) =>
                setSelected(
                  checked
                    ? new Map(groups.map((g) => [groupKey(g), g]))
                    : new Map()
                )
              }
              onDone={clearSelection}
            />
            <ul className="space-y-2">
              {groups.map((g) => (
                <NameGroupCard
                  key={groupKey(g)}
                  group={g}
                  showDataset={datasetIds.length > 1}
                  onDecided={onLastDecided}
                  isSelected={selected.has(groupKey(g))}
                  onSelect={(checked) => toggle(g, checked)}
                />
              ))}
            </ul>
            <Pagination
              currentPage={page}
              totalItems={total}
              itemsPerPage={PAGE_SIZE}
              onPageChange={(next) => {
                setPage(next);
                clearSelection();
              }}
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
  showDataset,
  onDecided,
  isSelected,
  onSelect,
}: {
  group: UnresolvedNameGroup;
  /** label the card with its dataset (several datasets selected) */
  showDataset: boolean;
  /** called after any decision on this card succeeds */
  onDecided?: () => void;
  isSelected: boolean;
  onSelect: (checked: boolean) => void;
}) {
  const done = { onSuccess: onDecided };
  const datasetId = group.datasetId;
  const decide = useResolveMatch();
  const create = useResolveNameGroup();
  const dismiss = useDismissNameGroup();
  const busy = decide.isPending || create.isPending || dismiss.isPending;
  const suggestedType =
    (group.resolutions[0]?.entityType as EntityType | undefined) ??
    group.suggestedType;

  return (
    <li
      className={cn(
        "rounded-lg border bg-card p-3",
        isSelected ? "border-primary/60" : "border-border"
      )}
    >
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <Checkbox
          checked={isSelected}
          onCheckedChange={(checked) => onSelect(checked === true)}
          aria-label={`Select ${group.surface}`}
        />
        <span className="rounded bg-annotation/15 px-1 font-mono text-foreground">
          {group.surface}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {group.mentionCount.toLocaleString()} mention
          {group.mentionCount === 1 ? "" : "s"} ·{" "}
          {group.fileCount.toLocaleString()} file
          {group.fileCount === 1 ? "" : "s"}
        </span>
        {group.isCorrespondent && <CorrespondentBadge />}
        {showDataset && <DatasetName datasetId={datasetId} />}
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
        <SampleContext
          context={group.sampleContext}
          names={[group.sampleSurface, group.surface]}
        />
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
  label = "Another entity…",
  onPick,
}: {
  /** the name group's dataset -- resolution runs per dataset */
  datasetId: string;
  surface: string;
  disabled?: boolean;
  label?: string;
  onPick: (entityId: string, entityType: EntityType) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(surface.trim().slice(0, 80));
  const debouncedQuery = useDebounce(query, 250);
  const { data: results, isFetching } = useEntitySearch(
    { datasetIds: [datasetId], q: debouncedQuery },
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
          {label}
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

function SampleContext({
  context,
  names,
}: {
  context: string;
  names: (string | null | undefined)[];
}) {
  const snippet = snippetAround(context, names);
  return (
    <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground [overflow-wrap:anywhere]">
      {snippet ? (
        <>
          {snippet.before}
          <mark className="rounded-sm bg-annotation/25 px-0.5 font-medium text-foreground box-decoration-clone">
            {snippet.name}
          </mark>
          {snippet.after}
        </>
      ) : (
        context
      )}
    </p>
  );
}

/** Select names on this page and decide them together: each to its own new entity, all to one entity, or not entities. */
function SelectionBar({
  groups,
  selected,
  onSelectAll,
  onDone,
}: {
  groups: UnresolvedNameGroup[];
  selected: Map<string, UnresolvedNameGroup>;
  onSelectAll: (checked: boolean) => void;
  onDone: () => void;
}) {
  const resolve = useResolveNameGroups();
  const dismiss = useDismissNameGroups();
  const accept = useResolveMatchesBatch();
  const busy = resolve.isPending || dismiss.isPending || accept.isPending;
  const chosen = [...selected.values()];
  const keys = chosen.map((g) => ({
    datasetId: g.datasetId,
    normalizedValue: g.normalizedValue,
    displayName: g.surface,
  }));
  const suggested = chosen.filter((g) => g.resolutions.length > 0);
  const datasetIds = new Set(chosen.map((g) => g.datasetId));
  const allChecked = groups.length > 0 && selected.size === groups.length;
  const done = { onSuccess: onDone };
  const names = (n: number) => `${n} name${n === 1 ? "" : "s"}`;

  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 shadow-sm">
      <Checkbox
        checked={
          allChecked ? true : selected.size > 0 ? "indeterminate" : false
        }
        onCheckedChange={(checked) => onSelectAll(checked === true)}
        aria-label="Select every name on this page"
      />
      <span className="text-[11px] text-muted-foreground">
        {selected.size
          ? `${names(selected.size)} selected`
          : "Select names to decide them together"}
      </span>
      {selected.size > 0 && (
        <>
          {suggested.length > 0 && (
            <Button
              size="sm"
              disabled={busy}
              className="h-7 gap-1 text-[11px]"
              title="Accept each selected name's top suggested entity"
              onClick={() =>
                accept.mutate(
                  {
                    decisions: suggested.map((g) => ({
                      matchId: g.resolutions[0].id,
                      status: "confirmed",
                    })),
                  },
                  done
                )
              }
            >
              <Check size={12} /> Accept {suggested.length} suggestion
              {suggested.length === 1 ? "" : "s"}
            </Button>
          )}
          <span className="ml-1 text-[11px] text-muted-foreground">
            New entity for each:
          </span>
          {CREATE_TYPES.map(({ type, label, Icon }) => (
            <Button
              key={type}
              size="sm"
              variant="outline"
              disabled={busy}
              className="h-7 gap-1 text-[11px]"
              onClick={() =>
                resolve.mutate({ groups: keys, entityType: type }, done)
              }
            >
              <Icon size={12} />
              {label}
            </Button>
          ))}
          {datasetIds.size === 1 && (
            <ResolveToExisting
              datasetId={chosen[0].datasetId}
              surface={chosen[0].surface}
              disabled={busy}
              label="All to one entity…"
              onPick={(entityId, entityType) =>
                resolve.mutate({ groups: keys, entityType, entityId }, done)
              }
            />
          )}
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
            onClick={() => dismiss.mutate(keys, done)}
          >
            <X size={12} /> Not entities
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            className="ml-auto h-7 px-2 text-[11px] text-muted-foreground"
            onClick={onDone}
          >
            Clear selection
          </Button>
        </>
      )}
    </div>
  );
}
