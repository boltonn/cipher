"use client";
import { searchService, toSearchChunk } from "@/features/search/api";
import type { ChunkTextSearchRequest, GroupedFileResult, SearchChunk, SearchFilters, SearchMode } from "@/features/search/types";
import { useInfiniteQuery } from "@tanstack/react-query";
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

export const useSearchController = () => {
  const [query, setQuery] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState<SearchMode>("text");
  const [groupByFile, setGroupByFile] = useState(true);
  const [filters, setFilters] = useState<SearchFilters>({});
  const [minSimilarity, setMinSimilarity] = useState<number | undefined>(undefined);

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
  const {
    data,
    isPending,
    isFetching,
    error,
    hasNextPage,
    fetchNextPage,
  } = useInfiniteQuery({
    queryKey: ["search", queryKeyCore],
    queryFn: ({ pageParam = 1 }) => search(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.hasMore ? lastPage.page + 1 : undefined),
    enabled: !!query,
  });

  const chunks = useMemo(
    () => data?.pages.flatMap((page) => page.data.map(toSearchChunk)) ?? [],
    [data]
  );

  const groupedResults = useMemo(() => groupByFileId(chunks), [chunks]);

  const actions = {
    handleSearch: useCallback((newQuery: string, newMode?: SearchMode) => {
      setQuery(newQuery);
      if (newMode) setSearchMode(newMode);
    }, []),
    handleSearchModeChange: useCallback((newMode: SearchMode) => setSearchMode(newMode), []),
    toggleGroupByFile: useCallback(() => setGroupByFile((current) => !current), []),
    setMinSimilarity: useCallback((value: number | undefined) => setMinSimilarity(value), []),
  };

  return {
    chunks,
    groupedResults,
    isPending: !!query && isPending,
    isFetching,
    error,
    hasMore: !!hasNextPage,
    loadMore: fetchNextPage,
    actions,
    query,
    searchMode,
    groupByFile,
    filters,
    setFilters,
    minSimilarity,
  };
};
