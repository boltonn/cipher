"use client";
import { messagesService } from "@/features/messages/api";
import { generateMockInfiniteData } from "@/features/messages/data";
import type {
  BaseMessageTextSearchParameters,
  PaginatedConversationChunksResponse,
  ScoredConversationChunk,
} from "@/features/messages/types";
import { PaginationModeType } from "@/types/common";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { UUID } from "crypto";
import { useCallback, useMemo, useState } from "react";

export type MessageSearchFilters = Omit<
  BaseMessageTextSearchParameters,
  "page" | "query"
>;

export type SearchMode = "text" | "semantic" | "hybrid";

type MessageSearchKey = [
  string,
  string,
  {
    query: string | null;
    searchMode: SearchMode;
  } & MessageSearchFilters,
];

type MessageSearchKeyPaginated = [
  string,
  string,
  "paginated",
  number,
  {
    query: string | null;
    searchMode: SearchMode;
  } & MessageSearchFilters,
];

type CachedPages = { pages: { data: ScoredConversationChunk[] }[] };

export const useMessageSearchController = (
  mode: PaginationModeType = "infinite"
) => {
  const queryClient = useQueryClient();

  const [query, setQuery] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState<SearchMode>("text");
  const [page, setPage] = useState(1);

  const [filters, setFilters] = useState<MessageSearchFilters>({
    sortOrder: "desc",
    limit: 10,
    filters: {},
  });

  const buildQueryFn = (
    pageParam: number
  ): Promise<PaginatedConversationChunksResponse> => {
    const params: BaseMessageTextSearchParameters = {
      ...filters,
      page: pageParam,
      query: query ?? "",
      returnMessages: false,
    };

    if (searchMode === "semantic")
      return messagesService.searchBySemantic(params);
    if (searchMode === "text") return messagesService.searchByText(params);
    return messagesService.searchByHybrid(params);
  };

  const queryKeyCore = { query, searchMode, ...filters };

  const {
    data: infiniteData,
    isPending: infiniteIsPending,
    isLoading: infiniteIsLoading,
    isFetching: infiniteIsFetching,
    fetchNextPage,
    fetchPreviousPage,
    hasNextPage,
    hasPreviousPage,
    isFetchingNextPage,
    isFetchingPreviousPage,
    error: infiniteError,
  } = useInfiniteQuery<
    PaginatedConversationChunksResponse,
    Error,
    InfiniteData<PaginatedConversationChunksResponse>,
    MessageSearchKey,
    number
  >({
    queryKey: ["messages", "search", queryKeyCore],
    queryFn: ({ pageParam = 1 }) => buildQueryFn(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.total > lastPage.page * lastPage.limit
        ? lastPage.page + 1
        : undefined,
    getPreviousPageParam: (firstPage) =>
      firstPage.page > 1 ? firstPage.page - 1 : undefined,
    enabled: mode === "infinite" && !!query,
  });

  const {
    data: paginatedData,
    isPending: paginatedIsPending,
    isLoading: paginatedIsLoading,
    isFetching: paginatedIsFetching,
    error: paginatedError,
  } = useQuery<PaginatedConversationChunksResponse, Error>({
    queryKey: [
      "messages",
      "search",
      "paginated",
      page,
      queryKeyCore,
    ] as MessageSearchKeyPaginated,
    queryFn: () => buildQueryFn(page),
    enabled: mode === "normal" && !!query,
  });

  const currentPage = useMemo(() => {
    if (mode === "infinite") {
      if (!infiniteData) return 1;
      return infiniteData.pageParams[infiniteData.pageParams.length - 1] as number;
    }
    return page;
  }, [mode, infiniteData, page]);

  const handleSearch = useCallback((newQuery: string, newMode?: SearchMode) => {
    setQuery(newQuery);
    if (newMode) setSearchMode(newMode);
    setPage(1);
  }, []);

  const handleSearchModeChange = useCallback((newMode: SearchMode) => {
    setSearchMode(newMode);
    setPage(1);
  }, []);

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
  }, []);

  const actions = {
    handleSearch,
    handleSearchModeChange,
    handlePageChange,
    handleToggleTag: (chunkId: UUID, tag: string, isHardNegative: boolean) => {
      // TODO: call backend — messagesService.toggleTag({ chunkId, tag, isHardNegative })
      // on error: queryClient.invalidateQueries({ queryKey: ["messages", "search"] })

      queryClient.setQueriesData<CachedPages>(
        { queryKey: ["messages", "search"] },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              data: page.data.map((c) => {
                if (c.id !== chunkId) return c;

                const inTags = c.tags.includes(tag);
                const inHardNegatives = c.hardNegativeTags.includes(tag);

                if (inTags) {
                  return { ...c, tags: c.tags.filter((t) => t !== tag) };
                }
                if (inHardNegatives) {
                  return {
                    ...c,
                    hardNegativeTags: c.hardNegativeTags.filter(
                      (t) => t !== tag
                    ),
                  };
                }
                if (isHardNegative) {
                  return {
                    ...c,
                    hardNegativeTags: [...c.hardNegativeTags, tag],
                  };
                }
                return { ...c, tags: [...c.tags, tag] };
              }),
            })),
          };
        }
      );
    },
    handleRelevance: (
      chunkId: UUID,
      currentQuery: string,
      relevant: boolean
    ) => {
      // TODO: messagesService.submitRelevance({ chunkId, query: currentQuery, relevant })
      console.log("Relevance feedback:", {
        chunkId,
        query: currentQuery,
        relevant,
      });
    },
  };

  const devMockData =
    process.env.NODE_ENV === "development" && !query
      ? generateMockInfiniteData()
      : undefined;

  return {
    data: mode === "infinite" ? (infiniteData ?? devMockData) : undefined,
    paginatedData: mode === "normal" ? paginatedData : undefined,

    isPending: mode === "infinite" ? infiniteIsPending : paginatedIsPending,
    isLoading: mode === "infinite" ? infiniteIsLoading : paginatedIsLoading,
    isFetching: mode === "infinite" ? infiniteIsFetching : paginatedIsFetching,

    fetchNextPage,
    fetchPreviousPage,
    hasNextPage,
    hasPreviousPage,
    isFetchingNextPage,
    isFetchingPreviousPage,

    error: mode === "infinite" ? infiniteError : paginatedError,

    actions,
    currentPage,
    filters,
    setFilters,
    searchMode,
    query,
    mode,
  };
};
