"use client";
import { readHandoff, type SearchHandoff } from "@/features/global-search/handoff";
import { searchService, toGroupedFileResult } from "@/features/search/api";
import type { ChunkTextSearchRequest, GraphExpand, SearchFilters, SearchMode } from "@/features/search/types";
import type { PaginationModeType } from "@/types/common";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { useDatasetScope } from "@/features/datasets/hooks/use-selected-datasets";
import { useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

const DEFAULT_LIMIT = 20;

/** Global-search filters in this page's shape (dates as local midnight, one `filetypeGroup` at most). */
function handoffFilters(handoff: SearchHandoff): SearchFilters {
  const next: SearchFilters = {};
  const groups = (handoff.filters?.filetypeGroups ?? []).filter((group) => group === "email" || group === "document");
  if (handoff.filters?.entityIds.length) next.entityIds = handoff.filters.entityIds;
  if (groups.length === 1) next.filetypeGroup = groups[0] as "email" | "document";
  if (handoff.filters?.dateFrom) next.dateFrom = `${handoff.filters.dateFrom}T00:00:00`;
  if (handoff.filters?.dateTo) next.dateTo = `${handoff.filters.dateTo}T00:00:00`;
  return next;
}

/** The chat assistant's exact search, with its YYYY-MM-DD dates as this page's local midnights. */
function chunkSearchFilters(filters: SearchFilters): SearchFilters {
  return {
    ...filters,
    dateFrom: filters.dateFrom ? `${filters.dateFrom.slice(0, 10)}T00:00:00` : undefined,
    dateTo: filters.dateTo ? `${filters.dateTo.slice(0, 10)}T00:00:00` : undefined,
  };
}

/** "Megan Flick or their addresses", "... or anyone within 1 hop" -- what the person filter keeps. */
function graphExpandLabel(graphExpand: GraphExpand, label: string | null | undefined): string {
  const hops = graphExpand.maxDepth - 1;
  const reach = hops > 0 ? `, or anyone within ${hops} hop${hops > 1 ? "s" : ""}` : " or their addresses";
  return `${label ?? "a person"}${reach}`;
}

const MODE_FROM_RETRIEVAL: Record<string, SearchMode> = { keyword: "text", semantic: "semantic", hybrid: "hybrid" };

const toDay = (iso: string | undefined) => (iso ? format(new Date(iso), "yyyy-MM-dd") : undefined);

export const useSearchController = (paginationMode: PaginationModeType = "infinite") => {
  // Deep links (e.g. from an entity's selectors) seed the field and type
  // filter once: /search?q=<value>&scope=<document|email>.
  const params = useSearchParams();
  // "See all" from global search hands its query + filters over without the URL (hybrid, like the overview).
  const [handoff] = useState(() => readHandoff("text"));
  // "" browses the unfiltered/filtered index instead of requiring a typed
  // query first -- only BM25 text search has a sensible match_all fallback,
  // so semantic/hybrid still wait for real input (see `canSearch` below).
  const [query, setQuery] = useState<string>(() => params.get("q") ?? handoff?.query ?? "");
  const [searchMode, setSearchMode] = useState<SearchMode>(() =>
    handoff?.chunkSearch && handoff.query
      ? MODE_FROM_RETRIEVAL[handoff.chunkSearch.mode]
      : handoff?.query
        ? "hybrid"
        : "text"
  );
  const [filters, setFiltersState] = useState<SearchFilters>(() => {
    if (handoff?.chunkSearch) return chunkSearchFilters(handoff.chunkSearch.filters);
    if (handoff) return handoffFilters(handoff);
    // Deep links from an entity/selector page compose an entity filter with an
    // empty-query browse: /search?entityId=<id>&datasetId=<id> (repeat entityId to require all; also &mentionValue=, &selectorType=).
    const next: SearchFilters = {};
    const scope = params.get("scope");
    if (scope === "email" || scope === "document") next.filetypeGroup = scope;
    if (params.getAll("entityId").length) next.entityIds = params.getAll("entityId");
    if (params.getAll("mentionValue").length) next.mentionValues = params.getAll("mentionValue");
    if (params.get("selectorType")) next.selectorTypes = [params.get("selectorType") as string];
    return next;
  });
  // The chat assistant's person filter: a person and what they link to (addresses), shown as a chip.
  const [graphExpand, setGraphExpand] = useState<{ value: GraphExpand; label: string } | undefined>(() =>
    handoff?.chunkSearch?.graphExpand
      ? {
          value: handoff.chunkSearch.graphExpand,
          label: graphExpandLabel(handoff.chunkSearch.graphExpand, handoff.chunkSearch.graphExpandLabel),
        }
      : undefined
  );
  // A deep link / handoff naming datasets scopes this view; otherwise the saved selection.
  const linkedDatasetId = handoff?.datasetId ?? params.get("datasetId");
  const scope = useDatasetScope(
    handoff?.chunkSearch?.datasetIds ?? (linkedDatasetId ? [linkedDatasetId] : undefined)
  );
  const [minSimilarity, setMinSimilarity] = useState<number | undefined>(undefined);
  const [exactMatch, setExactMatch] = useState(() => !!handoff?.filters?.exactMatch);
  const [page, setPage] = useState(1);

  const isInfinite = paginationMode === "infinite";
  const canSearch = searchMode === "text" || !!query;
  const datasetIds = scope.datasetIds;
  const queryKeyCore = { query, searchMode, filters, datasetIds, minSimilarity, exactMatch, graphExpand };

  const search = useCallback(
    (pageParam: number) => {
      const request: ChunkTextSearchRequest = {
        filters: {
          ...filters,
          datasetIds: datasetIds.length ? datasetIds : undefined,
          dateFrom: toDay(filters.dateFrom),
          dateTo: toDay(filters.dateTo),
        },
        page: pageParam,
        limit: DEFAULT_LIMIT,
        query,
        graphExpand: graphExpand?.value,
        exactMatch: exactMatch || undefined,
        // BM25 text search ignores this server-side; only wired for semantic/hybrid.
        minSimilarity: searchMode === "text" ? undefined : minSimilarity,
        // Sort is routed server-side: browsing (empty query, text mode) sorts by date, a real query sorts by score.
      };
      if (exactMatch) return searchService.searchText(request);
      if (searchMode === "semantic") return searchService.searchSemantic(request);
      if (searchMode === "hybrid") return searchService.searchHybrid(request);
      return searchService.searchText(request);
    },
    [datasetIds, exactMatch, filters, graphExpand, minSimilarity, query, searchMode]
  );

  // Single query against the unified /search/* router -- documents and emails
  // share one Elasticsearch index, so this is one real paginated result set
  // (accurate `hasMore`), not an approximation stitched from two separate
  // per-type paginated sources.
  const infinite = useInfiniteQuery({
    queryKey: ["search", "infinite", queryKeyCore],
    queryFn: ({ pageParam = 1 }) => search(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.hasMore ? lastPage.page + 1 : undefined),
    enabled: canSearch && isInfinite,
  });

  const paginated = useQuery({
    queryKey: ["search", "paginated", queryKeyCore, page],
    queryFn: () => search(page),
    placeholderData: keepPreviousData,
    enabled: canSearch && !isInfinite,
  });

  // Grouped by file server-side (via an Elasticsearch `collapse`, not a
  // client-side re-aggregation) -- a page is always exactly `limit` files,
  // never a chunk-dependent count that then collapses down to fewer.
  const groupedResults = useMemo(() => {
    if (isInfinite) return infinite.data?.pages.flatMap((p) => p.data.map(toGroupedFileResult)) ?? [];
    return paginated.data?.data.map(toGroupedFileResult) ?? [];
  }, [isInfinite, infinite.data, paginated.data]);

  // Server-side total across the whole result set (not just loaded pages): an exact
  // distinct-file count for browse / keyword; semantic / hybrid have no natural
  // cut-off, so their total only sizes pagination and isn't shown as a count.
  const lastPage = isInfinite ? infinite.data?.pages.at(-1) : paginated.data;
  const total = lastPage?.total ?? 0;
  const totalIsExact = lastPage?.totalIsExact ?? true;

  const setFilters = useCallback((next: SearchFilters) => {
    setFiltersState(next);
    setPage(1);
  }, []);

  const actions = {
    handleSearch: useCallback((newQuery: string, newMode?: SearchMode) => {
      setQuery(newQuery);
      if (newMode) setSearchMode(newMode);
      setPage(1);
    }, []),
    handleSearchModeChange: useCallback((newMode: SearchMode) => {
      setSearchMode(newMode);
      setPage(1);
    }, []),
    setExactMatch: useCallback((value: boolean) => {
      setExactMatch(value);
      setPage(1);
    }, []),
    handlePageChange: useCallback((newPage: number) => setPage(newPage), []),
    setDatasetIds: (ids: string[]) => {
      scope.setDatasetIds(ids);
      setPage(1);
    },
    setMinSimilarity: useCallback((value: number | undefined) => setMinSimilarity(value), []),
    clearGraphExpand: useCallback(() => {
      setGraphExpand(undefined);
      setPage(1);
    }, []),
  };

  return {
    groupedResults,
    total,
    totalIsExact,
    isPending: canSearch && (isInfinite ? infinite.isPending : paginated.isPending),
    isFetching: isInfinite ? infinite.isFetching : paginated.isFetching,
    error: isInfinite ? infinite.error : paginated.error,
    hasMore: !!infinite.hasNextPage,
    loadMore: infinite.fetchNextPage,
    currentPage: page,
    limit: DEFAULT_LIMIT,
    actions,
    query,
    canSearch,
    searchMode,
    exactMatch,
    filters,
    setFilters,
    datasetIds,
    minSimilarity,
    graphExpandLabel: graphExpand?.label,
  };
};
