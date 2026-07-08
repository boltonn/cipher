"use client";
import { searchService, toSearchChunk } from "@/features/search/api";
import type { ChunkTextSearchRequest, GroupedFileResult, SearchChunk, SearchFilters, SearchMode } from "@/features/search/types";
import type { PaginationModeType } from "@/types/common";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

const DEFAULT_LIMIT = 20;

function groupByFileId(chunks: SearchChunk[]): GroupedFileResult[] {
  const groups = new Map<string, GroupedFileResult>();

  for (const chunk of chunks) {
    const existing = groups.get(chunk.fileId);
    if (existing) {
      existing.chunks.push(chunk);
      existing.topScore = Math.max(existing.topScore, chunk.score);
    } else {
      groups.set(chunk.fileId, {
        fileId: chunk.fileId,
        displayName: chunk.displayName,
        filetypeGroup: chunk.filetypeGroup,
        chunks: [chunk],
        topScore: chunk.score,
      });
    }
  }

  return Array.from(groups.values()).sort((a, b) => b.topScore - a.topScore);
}

export const useSearchController = (paginationMode: PaginationModeType = "infinite") => {
  const [query, setQuery] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState<SearchMode>("text");
  const [groupByFile, setGroupByFile] = useState(true);
  const [filters, setFiltersState] = useState<SearchFilters>({});
  const [minSimilarity, setMinSimilarity] = useState<number | undefined>(undefined);
  const [page, setPage] = useState(1);

  const isInfinite = paginationMode === "infinite";
  const queryKeyCore = { query, searchMode, filters, minSimilarity };

  const search = useCallback(
    (pageParam: number) => {
      const request: ChunkTextSearchRequest = {
        filters,
        page: pageParam,
        limit: DEFAULT_LIMIT,
        query: query ?? "",
        // BM25 text search ignores this server-side; only wired for semantic/hybrid.
        minSimilarity: searchMode === "text" ? undefined : minSimilarity,
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
    enabled: !!query && isInfinite,
  });

  const paginated = useQuery({
    queryKey: ["search", "paginated", queryKeyCore, page],
    queryFn: () => search(page),
    placeholderData: keepPreviousData,
    enabled: !!query && !isInfinite,
  });

  const chunks = useMemo(() => {
    if (isInfinite) return infinite.data?.pages.flatMap((p) => p.data.map(toSearchChunk)) ?? [];
    return paginated.data?.data.map(toSearchChunk) ?? [];
  }, [isInfinite, infinite.data, paginated.data]);

  const groupedResults = useMemo(() => groupByFileId(chunks), [chunks]);

  // Server-side total across the whole result set (not just loaded pages) --
  // kNN totals are capped by its candidate pool, so this is exact for
  // text/hybrid and a floor for semantic.
  const total = (isInfinite ? infinite.data?.pages.at(-1)?.total : paginated.data?.total) ?? 0;

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
    toggleGroupByFile: useCallback(() => setGroupByFile((current) => !current), []),
    setMinSimilarity: useCallback((value: number | undefined) => setMinSimilarity(value), []),
  };

  return {
    chunks,
    groupedResults,
    total,
    isPending: !!query && (isInfinite ? infinite.isPending : paginated.isPending),
    isFetching: isInfinite ? infinite.isFetching : paginated.isFetching,
    error: isInfinite ? infinite.error : paginated.error,
    hasMore: !!infinite.hasNextPage,
    loadMore: infinite.fetchNextPage,
    currentPage: page,
    limit: DEFAULT_LIMIT,
    actions,
    query,
    searchMode,
    groupByFile,
    filters,
    setFilters,
    minSimilarity,
  };
};
