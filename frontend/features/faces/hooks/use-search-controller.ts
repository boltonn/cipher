"use client";
import { facesService } from "@/features/faces/api";
import {
  DEFAULT_MIN_SIMILARITY,
  type FaceSimilaritySearchParameters,
  type PaginatedFacesResponse,
  type PaginatedFaceSimilarityResponse,
} from "@/features/faces/types";
import { PaginationModeType } from "@/types/common";
import {
  useInfiniteQuery,
  useQuery,
  type InfiniteData,
} from "@tanstack/react-query";
import { useMemo, useState } from "react";

/** Most faces one bulk action takes (the API's `faceIds` cap). */
export const MAX_BULK_FACES = 1000;
const MAX_PAGE_SIZE = 100;

export type FaceFilters = Omit<FaceSimilaritySearchParameters, "page">;

type FaceSearchKey = [
  string,
  string,
  { queryLabel: string | undefined; similarId: string | null } & FaceFilters,
];

type FaceSearchKeyPaginated = [
  string,
  string,
  "paginated",
  number,
  { queryLabel: string | undefined; similarId: string | null } & FaceFilters,
];

type FaceQueryResponse = PaginatedFacesResponse | PaginatedFaceSimilarityResponse;

export const useSearchController = (mode: PaginationModeType = "infinite") => {
  // A face chosen from an uploaded photo (via /faces/detect, possibly after
  // the caller picked among several detected faces) drives the search by
  // its embedding; queryLabel is just for display (e.g. the filename).
  const [queryEmbedding, setQueryEmbedding] = useState<number[] | null>(null);
  const [queryLabel, setQueryLabel] = useState<string | undefined>(undefined);
  const [similarId, setSimilarId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const [filters, setFilters] = useState<FaceFilters>({
    sortOrder: "desc",
    limit: 24,
    minSimilarity: DEFAULT_MIN_SIMILARITY,
  });

  const isSimilarityMode = !!(queryEmbedding || similarId);

  const runQuery = (currentPage: number, limit = filters.limit) => {
    const currentParams: FaceSimilaritySearchParameters = {
      ...filters,
      limit,
      page: currentPage,
      // minSimilarity only makes sense once there's a query face to rank against
      minSimilarity: isSimilarityMode ? filters.minSimilarity : undefined,
    };
    if (queryEmbedding) return facesService.searchByEmbedding(queryEmbedding, currentParams);
    if (similarId) return facesService.searchById(similarId, currentParams);
    return facesService.search(currentParams);
  };

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
    FaceQueryResponse,
    Error,
    InfiniteData<FaceQueryResponse>,
    FaceSearchKey,
    number
  >({
    queryKey: ["faces", "search", { queryLabel, similarId, ...filters }],
    queryFn: ({ pageParam = 1 }) => runQuery(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.hasMore ? lastPage.page + 1 : undefined),
    getPreviousPageParam: (firstPage) => (firstPage.page > 1 ? firstPage.page - 1 : undefined),
    enabled: mode === "infinite",
  });

  const {
    data: paginatedData,
    isPending: paginatedIsPending,
    isLoading: paginatedIsLoading,
    isFetching: paginatedIsFetching,
    error: paginatedError,
  } = useQuery<FaceQueryResponse, Error>({
    queryKey: [
      "faces",
      "search",
      "paginated",
      page,
      { queryLabel, similarId, ...filters },
    ] as FaceSearchKeyPaginated,
    queryFn: () => runQuery(page),
    enabled: mode === "normal",
  });

  // Every result id of the current search (not just the loaded pages), for "select all".
  const fetchAllIds = async () => {
    const ids: string[] = [];
    for (let p = 1; ids.length < MAX_BULK_FACES; p++) {
      const result = await runQuery(p, MAX_PAGE_SIZE);
      ids.push(...result.data.map((face) => face.id));
      if (!result.hasMore) break;
    }
    return ids.slice(0, MAX_BULK_FACES);
  };

  const currentPage = useMemo(() => {
    if (mode === "infinite") {
      if (!infiniteData) return 1;
      return infiniteData.pageParams[infiniteData.pageParams.length - 1] as number;
    }
    return page;
  }, [mode, infiniteData, page]);

  // Stable identity: these flow down as props to every memoized FaceCard, so a
  // fresh object each render would defeat the memo and re-render the whole grid.
  const actions = useMemo(
    () => ({
      handleEmbeddingSelected: (embedding: number[], label?: string) => {
        setQueryEmbedding(embedding);
        setQueryLabel(label);
        setSimilarId(null);
        setPage(1);
      },
      handleSimilar: (faceId: string) => {
        setSimilarId(faceId);
        setQueryEmbedding(null);
        setQueryLabel(undefined);
        setPage(1);
      },
      clearSimilar: () => {
        setSimilarId(null);
        setQueryEmbedding(null);
        setQueryLabel(undefined);
        setPage(1);
      },
      handlePageChange: (newPage: number) => {
        setPage(newPage);
      },
    }),
    []
  );

  return {
    data: mode === "infinite" ? infiniteData : undefined,
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
    fetchAllIds,
    currentPage,
    filters,
    setFilters,
    similarId,
    queryLabel,
    isSimilarityMode,
    mode,
  };
};
