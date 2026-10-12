"use client";
import { imagesService } from "@/features/images/api";
import type {
  ImageSimilaritySearchParameters,
  PaginatedImagesResponse,
  PaginatedImageSimilarityResponse,
} from "@/features/images/types";
import { PaginationModeType } from "@/types/common";
import {
  useInfiniteQuery,
  useQuery,
  type InfiniteData,
} from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { readHandoff } from "@/features/global-search/handoff";

export type ImageFilters = Omit<ImageSimilaritySearchParameters, "page">;

type ImageQueryResponse = PaginatedImagesResponse | PaginatedImageSimilarityResponse;

type ImageSearchKey = [
  string,
  string,
  {
    file: string | undefined;
    id: string | null;
    text: string | null;
  } & ImageFilters,
];

type ImageSearchKeyPaginated = [
  string,
  string,
  "paginated",
  number,
  {
    file: string | undefined;
    id: string | null;
    text: string | null;
  } & ImageFilters,
];

/** Predictions are reviewed most-confident first; everything else keeps the default sort. */
const withSort = (filters: ImageFilters): ImageFilters =>
  filters.predictedTags?.length ? { ...filters, sortBy: "tagScore" }
    : filters;

export const useSearchController = (mode: PaginationModeType = "infinite") => {
  // "See all" / an image clicked on global search: similar-to-that-image, or the text query.
  const [handoff] = useState(() => readHandoff("images"));
  const [file, setFile] = useState<File | null>(null);
  const [id, setId] = useState<string | null>(() => handoff?.imageId ?? null);
  const [text, setText] = useState<string | null>(() => (handoff && !handoff.imageId && handoff.query) || null);
  const [page, setPage] = useState(1);

  const [filters, setFilters] = useState<ImageFilters>(() => ({
    sortOrder: "desc",
    minSimilarity: 0,
    limit: 20,
    ...(handoff?.datasetId ? { datasets: [handoff.datasetId] } : {}),
  }));

  // Infinite query for infinite scroll mode
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
    ImageQueryResponse,
    Error,
    InfiniteData<ImageQueryResponse>,
    ImageSearchKey,
    number
  >({
    queryKey: ["images", "search", { file: file?.name, id, text, ...filters }],
    queryFn: ({ pageParam = 1 }) => {
      const currentParams: ImageSimilaritySearchParameters = {
        ...withSort(filters),
        page: pageParam,
      };

      if (file) return imagesService.searchByUpload(file, currentParams);
      if (id) return imagesService.searchById(id, currentParams);
      if (text)
        return imagesService.searchByText({ query: text, ...currentParams });
      return imagesService.searchGeneral(currentParams);
    },
    initialPageParam: 1,
    getNextPageParam: (lastPage: ImageQueryResponse) => {
      if (lastPage.hasMore) {
        return lastPage.page + 1;
      }
      return undefined;
    },
    getPreviousPageParam: (firstPage: ImageQueryResponse) => {
      return firstPage.page > 1 ? firstPage.page - 1 : undefined;
    },
    enabled: mode === "infinite",
  });

  // Regular query for paginated mode
  const {
    data: paginatedData,
    isPending: paginatedIsPending,
    isLoading: paginatedIsLoading,
    isFetching: paginatedIsFetching,
    error: paginatedError,
  } = useQuery<ImageQueryResponse, Error>({
    queryKey: [
      "images",
      "search",
      "paginated",
      page,
      { file: file?.name, id, text, ...filters },
    ] as ImageSearchKeyPaginated,
    queryFn: () => {
      const currentParams: ImageSimilaritySearchParameters = {
        ...withSort(filters),
        page,
      };

      if (file) return imagesService.searchByUpload(file, currentParams);
      if (id) return imagesService.searchById(id, currentParams);
      if (text)
        return imagesService.searchByText({ query: text, ...currentParams });
      return imagesService.searchGeneral(currentParams);
    },
    enabled: mode === "normal",
  });

  const isSimilarityMode = !!(file || id || text);

  const queryLabel = text ?? (file ? file.name : id ? "Similar to image" : undefined);

  const currentPage = useMemo(() => {
    if (mode === "infinite") {
      if (!infiniteData) return 1;
      return infiniteData.pageParams[infiniteData.pageParams.length - 1] as number;
    }
    return page;
  }, [mode, infiniteData, page]);

  const actions = {
    handleUpload: (newFile: File) => {
      setFile(newFile);
      setId(null);
      setText(null);
      setPage(1);
    },
    handleText: (query: string) => {
      setText(query);
      setFile(null);
      setId(null);
      setPage(1);
    },
    handleSimilar: (imageId: string) => {
      setId(imageId);
      setFile(null);
      setText(null);
      setPage(1);
    },
    clearSearch: () => {
      setFile(null);
      setId(null);
      setText(null);
      setPage(1);
    },
    handlePageChange: (newPage: number) => {
      setPage(newPage);
    },
  };

  // Return unified interface
  return {
    // Data
    data: mode === "infinite" ? infiniteData : undefined,
    paginatedData: mode === "normal" ? paginatedData : undefined,

    // Loading states
    isPending: mode === "infinite" ? infiniteIsPending : paginatedIsPending,
    isLoading: mode === "infinite" ? infiniteIsLoading : paginatedIsLoading,
    isFetching: mode === "infinite" ? infiniteIsFetching : paginatedIsFetching,

    // Infinite query specific
    fetchNextPage,
    fetchPreviousPage,
    hasNextPage,
    hasPreviousPage,
    isFetchingNextPage,
    isFetchingPreviousPage,

    // Error
    error: mode === "infinite" ? infiniteError : paginatedError,

    // Common
    actions,
    currentPage,
    filters,
    setFilters,
    mode,
    isSimilarityMode,
    queryLabel,
    textQuery: text,
  };
};
