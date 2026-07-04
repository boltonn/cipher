import type {
  Dataset,
  DatasetRequest,
  DatasetStatsRequest,
  DatasetStatsResponse,
  DatasetSummary,
} from "@/features/datasets/types";
import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types/common";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

const queryKeys = {
  datasets: (filters?: DatasetRequest) => ["datasets", filters] as const,
} as const;

// High-level service using Axios
const datasetService = {
  searchDatasets: async (
    filters?: DatasetRequest,
    page: number = 1
  ): Promise<PaginatedResponse<DatasetSummary>> => {
    // Axios handles the serialization of the params object automatically
    // It will even handle array types correctly if filters contains them
    const { data } = await apiClient.get<PaginatedResponse<DatasetSummary>>(
      "/datasets",
      {
        params: {
          ...filters,
          page,
        },
      }
    );

    return data;
  },
  getById: async (id: string): Promise<Dataset> => {
    const { data } = await apiClient.get<Dataset>(`/datasets/${id}`);
    return data;
  },
  getStats: async (id: string, params?: DatasetStatsRequest): Promise<DatasetStatsResponse> => {
    const { data } = await apiClient.get<DatasetStatsResponse>(`/datasets/${id}/stats`, { params });
    return data;
  },
};

/** Infinite-scroll variant, used by the dataset multi-select combobox. */
export function useDatasets(filters: DatasetRequest) {
  return useInfiniteQuery({
    // Spreading filters into the key ensures primitive comparison
    queryKey: queryKeys.datasets({ ...filters }),
    queryFn: ({ pageParam = 1 }) =>
      datasetService.searchDatasets(filters, pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.hasMore ? lastPage.page + 1 : undefined,
    // Add a staleTime so it doesn't refetch on every tiny click
    staleTime: 2000,
  });
}

/** Paginated variant for the datasets table/card views (page is part of the request). */
export function useDatasetsList(request: DatasetRequest) {
  return useQuery({
    queryKey: queryKeys.datasets(request),
    queryFn: () => datasetService.searchDatasets(request, request.page ?? 1),
    staleTime: 2000,
  });
}

export function useDataset(id: string | undefined) {
  return useQuery({
    queryKey: ["datasets", id],
    queryFn: () => datasetService.getById(id as string),
    enabled: !!id,
    staleTime: 60_000,
  });
}

export function useDatasetStats(id: string | undefined, params: DatasetStatsRequest) {
  return useQuery({
    queryKey: ["datasets", id, "stats", params],
    queryFn: () => datasetService.getStats(id as string, params),
    enabled: !!id,
    staleTime: 10_000,
  });
}
