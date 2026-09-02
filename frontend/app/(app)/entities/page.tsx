"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
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
import { MentionReviewList } from "@/features/entities/components/mention-review-list";
import {
  useEntityList,
  useEntitySearch,
} from "@/features/entities/hooks/use-entities";
import { useUnresolvedNameGroups } from "@/features/entities/hooks/use-mentions";
import { ENTITY_TYPES, type EntityType } from "@/features/entities/types";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";
import {
  ChevronsUpDown,
  ClipboardCheck,
  Database,
  Network,
  Search,
  Shapes,
  Table2,
} from "lucide-react";
import { useState } from "react";

const LIMIT = 15;
const ALL_TYPES = "__all__";

export default function EntitiesPage() {
  const [datasetId, setDatasetId] = useLocalStorageState<string | undefined>(
    "entities:datasetId",
    undefined
  );
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<EntityFilters>(EMPTY_ENTITY_FILTERS);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{
    by: "display_name" | "date_updated";
    order: "asc" | "desc";
  }>({ by: "display_name", order: "asc" });

  const listQuery = useEntityList({
    datasetId,
    query: query || undefined,
    entityType: filters.entityType,
    selectorKind: filters.selectorKind,
    country: filters.country,
    orgType: filters.orgType,
    dateOfBirthFrom: filters.dobFrom?.slice(0, 10),
    dateOfBirthTo: filters.dobTo?.slice(0, 10),
    sortBy: sort.by,
    sortOrder: sort.order,
    limit: LIMIT,
    page,
  });

  const changeSort = (by: "display_name" | "date_updated") => {
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

  const unresolved = useUnresolvedNameGroups(datasetId, "", 1);
  const reviewCount = unresolved.data?.total ?? 0;

  const entities = listQuery.data?.data ?? [];
  const total = listQuery.data?.total ?? 0;

  const resetPage = () => setPage(1);

  const changeType = (raw: string) => {
    const entityType = raw === ALL_TYPES ? undefined : (raw as EntityType);
    setFilters({
      ...filters,
      entityType,
      selectorKind: undefined,
      country: undefined,
      orgType: undefined,
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
    <div className="relative mx-auto max-w-400 px-6 pb-20">
      <PageHeader
        eyebrow="Entities"
        value={datasetId ? `${total.toLocaleString()} entities` : "no dataset"}
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
        <div className="mt-4 space-y-4">
          <SearchBarShell
            isActive={listQuery.isFetching}
            icon={<Search size={18} strokeWidth={1.5} />}
          >
            <div className="mr-1 flex shrink-0 items-center border-r border-border/50 pr-2 pl-1">
              <Select
                value={filters.entityType ?? ALL_TYPES}
                onValueChange={changeType}
              >
                <SelectTrigger
                  aria-label="Entity type"
                  className="h-8 w-auto gap-1.5 border-0 bg-transparent px-1.5 text-xs font-semibold shadow-none hover:bg-muted/50 focus-visible:ring-0 [&_svg]:opacity-100"
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

          <Tabs defaultValue="table" className="gap-4">
            <TabsList className="h-9">
              <TabsTrigger value="table" className="gap-1.5 px-3 text-xs">
                <Table2 size={13} />
                Table
              </TabsTrigger>
              <TabsTrigger value="graph" className="gap-1.5 px-3 text-xs">
                <Network size={13} />
                Graph
              </TabsTrigger>
              <TabsTrigger value="review" className="gap-1.5 px-3 text-xs">
                <ClipboardCheck size={13} />
                Review
                {reviewCount > 0 && (
                  <Badge className="h-4 min-w-4 bg-annotation/20 px-1 text-[9px] text-annotation">
                    {reviewCount}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="table">
              {listQuery.isPending ? (
                <PageLoading className="py-24" label="Loading entities…" />
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
                  <EntitiesTable
                    entities={entities}
                    sortBy={sort.by}
                    sortOrder={sort.order}
                    onSortChange={changeSort}
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

            <TabsContent value="review">
              <MentionReviewList datasetId={datasetId} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}

function GraphExplorer({ datasetId }: { datasetId: string }) {
  const [focus, setFocus] = useState<{ id: string; name: string } | null>(null);
  const [depth, setDepth] = useState(2);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const { data: results, isFetching } = useEntitySearch({ datasetId, q });

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
