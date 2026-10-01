"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { EntitiesTable } from "@/features/entities/components/entities-table";
import { EntityGraph } from "@/features/entities/components/entity-graph";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import {
  EMPTY_ENTITY_FILTERS,
  EntitySearchFilters,
  entityRefinementsActive,
  type EntityFilters,
} from "@/features/entities/components/entity-search-filters";
import { EntityVerifyList } from "@/features/entities/components/entity-verify-list";
import { NameResolutionQueue } from "@/features/entities/components/name-resolution-queue";
import {
  useEntityBreakdown,
  useEntityList,
  useEntitySearch,
} from "@/features/entities/hooks/use-entities";
import { useUnresolvedNameGroups } from "@/features/entities/hooks/use-mentions";
import {
  ENTITY_TYPES,
  type EntitySortKey,
  type EntityType,
} from "@/features/entities/types";
import { cn, formatCompactNumber } from "@/lib/utils";
import { useDebounce } from "@/hooks/use-debounce";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";
import {
  ChevronsUpDown,
  ClipboardCheck,
  Database,
  GitMerge,
  HelpCircle,
  Info,
  Network,
  Search,
  Shapes,
  Share2,
  Table2,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

const LIMIT = 15;
const ALL_TYPES = "__all__";

export default function EntitiesPage() {
  // A deep link from the dataset breakdown (?datasetId=&entityType=&selectorType=&selectorSubtype=)
  // seeds the initial view; after mount it behaves like any other filter (not URL-synced).
  const initialParams = useSearchParams();
  const linkedDatasetId = initialParams.get("datasetId") ?? undefined;
  const [storedDatasetId, setStoredDatasetId] = useLocalStorageState<
    string | undefined
  >("entities:datasetId", undefined);
  const [datasetOverride, setDatasetOverride] = useState<string | undefined>(
    linkedDatasetId
  );
  const datasetId = datasetOverride ?? storedDatasetId;
  const setDatasetId = (id: string | undefined) => {
    setDatasetOverride(id);
    setStoredDatasetId(id);
  };
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<EntityFilters>(() => {
    const f: EntityFilters = {};
    const et = initialParams.get("entityType");
    const st = initialParams.get("selectorType");
    const ss = initialParams.get("selectorSubtype");
    if (et) f.entityType = et as EntityFilters["entityType"];
    if (st) f.selectorType = st as EntityFilters["selectorType"];
    if (ss) f.selectorSubtype = ss as EntityFilters["selectorSubtype"];
    return f;
  });
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{
    by: EntitySortKey;
    order: "asc" | "desc";
  }>({ by: "mention_count", order: "desc" });
  const [tab, setTab] = useState<EntityTab>("table");
  const [resolveFocus, setResolveFocus] = useState<{
    id: string;
    name: string;
  } | null>(null);

  const listQuery = useEntityList({
    datasetId,
    query: query || undefined,
    entityType: filters.entityType,
    selectorType: filters.selectorType,
    selectorSubtype: filters.selectorSubtype,
    country: filters.country,
    category: filters.category,
    dateOfBirthFrom: filters.dobFrom?.slice(0, 10),
    dateOfBirthTo: filters.dobTo?.slice(0, 10),
    sortBy: sort.by,
    sortOrder: sort.order,
    limit: LIMIT,
    page,
  });

  const changeSort = (by: EntitySortKey) => {
    setSort((prev) =>
      prev.by === by
        ? { by, order: prev.order === "asc" ? "desc" : "asc" }
        : { by, order: by === "display_name" ? "asc" : "desc" }
    );
    setPage(1);
  };

  const clearAll = () => {
    setQuery("");
    setFilters({ ...EMPTY_ENTITY_FILTERS });
    resetPage();
  };

  const unresolved = useUnresolvedNameGroups({ datasetId, page: 1 });
  const resolveCount = unresolved.data?.total ?? 0;
  const autoCreated = useEntityList({ datasetId, provisional: true, limit: 1, page: 1 });
  const verifyCount = autoCreated.data?.total ?? 0;
  const breakdown = useEntityBreakdown(datasetId);

  const entities = listQuery.data?.data ?? [];
  const total = listQuery.data?.total ?? 0;

  const resetPage = () => setPage(1);

  const changeType = (raw: string) => {
    const entityType = raw === ALL_TYPES ? undefined : (raw as EntityType);
    setFilters({
      ...filters,
      entityType,
      selectorType: undefined,
      selectorSubtype: undefined,
      country: undefined,
      category: undefined,
      dobFrom: undefined,
      dobTo: undefined,
    });
    resetPage();
  };

  const typeMeta = filters.entityType
    ? ENTITY_TYPE_META[filters.entityType]
    : null;
  const filtered = entityRefinementsActive(filters) || !!query;

  return (
    <div className="relative mx-auto max-w-400 px-6 pb-20 pt-5">
      <PageHeader
        eyebrow="Entities"
        value={!datasetId ? "No dataset selected" : listQuery.data ? `${total.toLocaleString()} ${total === 1 ? "entity" : "entities"}` : undefined}
        icon={<Network size={13} className="text-primary/70" />}
        actions={
          <DatasetSelect
            datasetId={datasetId}
            onChange={(id) => {
              setDatasetId(id);
              resetPage();
            }}
          />
        }
      />

      {!datasetId ? (
        <EmptyState
          className="mt-6"
          icon={Database}
          title="Choose a dataset"
          body="Entities, mentions, and the relationship graph are scoped to one dataset. Pick one from the selector in the top bar to start exploring."
        />
      ) : (
        <div className="mt-4">
          <Tabs
            value={tab}
            onValueChange={(v) => setTab(v as EntityTab)}
            className="gap-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <TabsList className="h-9">
                <TabsTrigger value="table" className="gap-1.5 px-3 text-xs">
                  <Table2 size={13} />
                  Entities
                </TabsTrigger>
                <TabsTrigger value="graph" className="gap-1.5 px-3 text-xs">
                  <Network size={13} />
                  Graph
                </TabsTrigger>
                <TabsTrigger value="verify" className="gap-1.5 px-3 text-xs">
                  <ClipboardCheck size={13} />
                  Verify
                  {verifyCount > 0 && (
                    <Badge className="h-4 min-w-4 bg-annotation/15 px-1.5 text-[11px] font-medium tabular-nums text-annotation">
                      {formatCompactNumber(verifyCount)}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="resolve" className="gap-1.5 px-3 text-xs">
                  <GitMerge size={13} />
                  Resolve
                  {resolveCount > 0 && (
                    <Badge className="h-4 min-w-4 bg-annotation/15 px-1.5 text-[11px] font-medium tabular-nums text-annotation">
                      {formatCompactNumber(resolveCount)}
                    </Badge>
                  )}
                </TabsTrigger>
              </TabsList>
              <div className="flex items-center gap-3">
                <TabExplainer tab={tab} />
                <Link
                  href="/entities/resolution-guide"
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  <HelpCircle size={12} />
                  How resolution works
                </Link>
              </div>
            </div>

            <TabsContent value="table" className="space-y-4">
              <SearchBarShell
                isActive={listQuery.isFetching}
                icon={<Search size={18} strokeWidth={1.5} />}
              >
                <div className="flex shrink-0 items-center border-r border-border/50 pr-1">
                  <Select
                    value={filters.entityType ?? ALL_TYPES}
                    onValueChange={changeType}
                  >
                    <SelectTrigger
                      aria-label="Entity type"
                      className="h-7 w-auto gap-1.5 border-0 bg-transparent px-1.5 text-xs font-semibold shadow-none hover:bg-muted/50 focus-visible:ring-0 [&_svg]:opacity-100"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL_TYPES} className="text-xs">
                        <span className="flex items-center gap-2">
                          <Shapes size={12} className="text-muted-foreground" />
                          All types
                        </span>
                      </SelectItem>
                      <SelectSeparator />
                      {ENTITY_TYPES.map((t) => {
                        const meta = ENTITY_TYPE_META[t];
                        return (
                          <SelectItem key={t} value={t} className="text-xs">
                            <span className="flex items-center gap-2">
                              <meta.Icon size={12} className={meta.textClass} />
                              {meta.label}
                            </span>
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>

                <SearchInput
                  value={query}
                  onSearch={(q) => {
                    setQuery(q);
                    resetPage();
                  }}
                  ariaLabel="Search entities"
                  placeholder={
                    typeMeta
                      ? `Search ${typeMeta.label.toLowerCase()} names…`
                      : "Search by name…"
                  }
                />
              </SearchBarShell>

              <EntitySearchFilters
                value={filters}
                onChange={(next) => {
                  setFilters(next);
                  resetPage();
                }}
                queryActive={!!query}
                onClear={clearAll}
              />

              {listQuery.isError ? (
                <PageError
                  title="Couldn’t load entities"
                  body="The request for this dataset’s entities failed. This is usually temporary."
                  onRetry={() => listQuery.refetch()}
                />
              ) : listQuery.isPending ? (
                <PageLoading
                  className="py-24"
                  label="Loading entities…"
                  onRetry={() => listQuery.refetch()}
                />
              ) : entities.length === 0 ? (
                <EmptyState
                  icon={Shapes}
                  title={filtered ? "No matches" : "No entities yet"}
                  body={
                    filtered
                      ? "Nothing in this dataset matches the current search and filters."
                      : "This dataset has no entities. Run entity extraction to pull names, selectors, and relationships out of its files."
                  }
                  action={
                    filtered ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        onClick={clearAll}
                      >
                        Clear filters
                      </Button>
                    ) : undefined
                  }
                />
              ) : (
                <>
                  <TypeSummary
                    items={breakdown.data?.byEntityType ?? []}
                    active={filters.entityType}
                    onPick={(t) =>
                      changeType(t === filters.entityType ? ALL_TYPES : t)
                    }
                  />
                  <EntitiesTable
                    entities={entities}
                    sortBy={sort.by}
                    sortOrder={sort.order}
                    onSortChange={changeSort}
                    onOpenResolve={(e) => {
                      setResolveFocus({ id: e.id, name: e.displayName });
                      setTab("resolve");
                    }}
                  />
                  <Pagination
                    currentPage={page}
                    totalItems={total}
                    itemsPerPage={LIMIT}
                    onPageChange={setPage}
                    isLoading={listQuery.isFetching}
                  />
                </>
              )}
            </TabsContent>

            <TabsContent value="graph">
              <GraphExplorer datasetId={datasetId} />
            </TabsContent>

            <TabsContent value="verify">
              <EntityVerifyList datasetId={datasetId} />
            </TabsContent>

            <TabsContent value="resolve">
              <NameResolutionQueue
                key={resolveFocus?.id ?? "all"}
                datasetId={datasetId}
                focus={resolveFocus}
                onClearFocus={() => setResolveFocus(null)}
              />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}

type EntityTab = "table" | "graph" | "verify" | "resolve";

const TAB_EXPLAINERS: Record<EntityTab, { question: string; body: string }> = {
  table: {
    question: "What do we know?",
    body: "Every entity — one record per real person, organization, location or identifier — ranked by its mentions. Amber “to resolve” means name groups have a pending resolution to it; ⊘ marks one invalid.",
  },
  graph: {
    question: "How is it connected?",
    body: "The relationship neighbourhood around one entity.",
  },
  verify: {
    question: "Are these entities real?",
    body: "Entities the resolver auto-created for names that matched nothing. Verify the big ones (keep, rename, or merge a duplicate) before resolving more names to them.",
  },
  resolve: {
    question: "Which entity is this name?",
    body: "Each card is a name group — every unresolved mention of one name. Accept or reject a suggested resolution, resolve it to another entity, create a new entity, or mark it not an entity. The decision applies to all of its mentions.",
  },
};

function TabExplainer({ tab }: { tab: EntityTab }) {
  const { question, body } = TAB_EXPLAINERS[tab];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={question}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <Info size={12} />
          {question}
        </button>
      </TooltipTrigger>
      <TooltipContent align="end" className="max-w-72 text-xs leading-relaxed">
        {body}
      </TooltipContent>
    </Tooltip>
  );
}

function TypeSummary({
  items,
  active,
  onPick,
}: {
  items: { key: string; count: number }[];
  active?: EntityType;
  onPick: (type: EntityType) => void;
}) {
  const known = items.filter((i): i is { key: EntityType; count: number } =>
    (ENTITY_TYPES as readonly string[]).includes(i.key)
  );
  if (known.length === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {known.map(({ key, count }) => {
        const meta = ENTITY_TYPE_META[key];
        return (
          <button
            key={key}
            type="button"
            aria-pressed={active === key}
            onClick={() => onPick(key)}
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3 py-1.5 text-left transition-colors",
              active === key
                ? "border-primary/50 bg-primary/5"
                : "border-border hover:bg-muted/40"
            )}
          >
            <meta.Icon size={13} className={meta.textClass} />
            <span className="text-sm font-semibold tabular-nums text-foreground">
              {count.toLocaleString()}
            </span>
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
              {meta.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function GraphExplorer({ datasetId }: { datasetId: string }) {
  const [focus, setFocus] = useState<{ id: string; name: string } | null>(null);
  const [depth, setDepth] = useState(2);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const debouncedQ = useDebounce(q, 250);
  const { data: results, isFetching } = useEntitySearch({ datasetId, q: debouncedQ });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              className="h-9 w-64 justify-between border-border bg-muted/40 text-xs"
            >
              <span className="truncate">
                {focus?.name ?? "Pick a focus entity…"}
              </span>
              <ChevronsUpDown size={13} className="text-muted-foreground" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72 border-border bg-popover p-0">
            <Command shouldFilter={false}>
              <CommandInput
                value={q}
                onValueChange={setQ}
                placeholder="Search entities…"
                className="text-xs"
              />
              <CommandList>
                {!isFetching && (results?.length ?? 0) === 0 && (
                  <CommandEmpty className="py-4 text-xs text-muted-foreground">
                    Type to search.
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
                          setFocus({ id: r.id, name: r.displayName });
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

        <Select
          value={String(depth)}
          onValueChange={(v) => setDepth(Number(v))}
        >
          <SelectTrigger className="h-9 w-28 bg-muted/40 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[1, 2, 3].map((d) => (
              <SelectItem key={d} value={String(d)} className="text-xs">
                Depth {d}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          asChild
          variant="ghost"
          size="sm"
          className="ml-auto h-9 gap-1.5 text-xs font-medium text-muted-foreground hover:text-primary"
        >
          <Link
            href={
              focus
                ? `/graph?dataset=${datasetId}&seed=${focus.id}`
                : `/graph?dataset=${datasetId}`
            }
          >
            <Share2 size={13} />
            Full graph viewer
          </Link>
        </Button>
      </div>

      {focus ? (
        <EntityGraph focusEntityId={focus.id} depth={depth} />
      ) : (
        <EmptyState
          icon={Network}
          title="Pick a focus entity"
          body="Choose an entity above to render its neighbourhood — related people, organizations, locations, and shared selectors."
        />
      )}
    </div>
  );
}
