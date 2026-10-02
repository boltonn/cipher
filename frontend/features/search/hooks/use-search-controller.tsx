"use client";
import { searchService, toGroupedFileResult } from "@/features/search/api";
import type { ChunkTextSearchRequest, SearchFilters, SearchMode } from "@/features/search/types";
import type { PaginationModeType } from "@/types/common";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

const DEFAULT_LIMIT = 20;

const toDay = (iso: string | undefined) => (iso ? format(new Date(iso), "yyyy-MM-dd") : undefined);

export const useSearchController = (paginationMode: PaginationModeType = "infinite") => {
  // Deep links (e.g. from an entity's selectors) seed the field and type
  // filter once: /search?q=<value>&scope=<document|email>.
  const params = useSearchParams();
  // "" browses the unfiltered/filtered index instead of requiring a typed
  // query first -- only BM25 text search has a sensible match_all fallback,
  // so semantic/hybrid still wait for real input (see `canSearch` below).
  const [query, setQuery] = useState<string>(() => params.get("q") ?? "");
  const [searchMode, setSearchMode] = useState<SearchMode>("text");
  const [filters, setFiltersState] = useState<SearchFilters>(() => {
    // Deep links from an entity/selector page compose an entity filter with an
    // empty-query browse: /search?entityId=<id>&datasetId=<id> (repeat entityId to require all; also &mentionValue=, &selectorType=).
    const next: SearchFilters = {};
    const scope = params.get("scope");
    if (scope === "email" || scope === "document") next.filetypeGroup = scope;
    if (params.get("datasetId")) next.datasetId = params.get("datasetId") ?? undefined;
    if (params.getAll("entityId").length) next.entityIds = params.getAll("entityId");
    if (params.getAll("mentionValue").length) next.mentionValues = params.getAll("mentionValue");
    if (params.get("selectorType")) next.selectorTypes = [params.get("selectorType") as string];
    return next;
  });
  const [minSimilarity, setMinSimilarity] = useState<number | undefined>(undefined);
  const [page, setPage] = useState(1);

  const isInfinite = paginationMode === "infinite";
  const canSearch = searchMode === "text" || !!query;
  const queryKeyCore = { query, searchMode, filters, minSimilarity };

  const search = useCallback(
    (pageParam: number) => {
      const request: ChunkTextSearchRequest = {
        filters: { ...filters, dateFrom: toDay(filters.dateFrom), dateTo: toDay(filters.dateTo) },
        page: pageParam,
        limit: DEFAULT_LIMIT,
        query,
        // BM25 text search ignores this server-side; only wired for semantic/hybrid.
        minSimilarity: searchMode === "text" ? undefined : minSimilarity,
        // Sort is routed server-side: browsing (empty query, text mode) sorts by date, a real query sorts by score.
      };
      if (searchMode === "semantic") return searchService.searchSemantic(request);
      if (searchMode === "hybrid") return searchService.searchHybrid(request);
      return searchService.searchText(request);
    },
    [filters, minSimilarity, query, searchMode]
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
    handlePageChange: useCallback((newPage: number) => setPage(newPage), []),
    setMinSimilarity: useCallback((value: number | undefined) => setMinSimilarity(value), []),
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
    filters,
    setFilters,
    minSimilarity,
  };
};
