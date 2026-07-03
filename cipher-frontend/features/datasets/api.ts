import type { Dataset, DatasetRequest } from "@/features/datasets/types";
import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types/common";
import { useInfiniteQuery } from "@tanstack/react-query";

const queryKeys = {
  datasets: (filters?: DatasetRequest) => ["datasets", filters] as const,
} as const;

// High-level service using Axios
const datasetService = {
  searchDatasets: async (
    filters?: DatasetRequest,
    page: number = 1
  ): Promise<PaginatedResponse<Dataset>> => {
    // Axios handles the serialization of the params object automatically
    // It will even handle array types correctly if filters contains them
    const { data } = await apiClient.get<PaginatedResponse<Dataset>>(
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
};

export function useDatasets(filters: DatasetRequest) {
  return useInfiniteQuery({
    // Spreading filters into the key ensures primitive comparison
    queryKey: ["datasets", { ...filters }],
    queryFn: ({ pageParam = 1 }) =>
      datasetService.searchDatasets(filters, pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.hasMore ? lastPage.page + 1 : undefined,
    // Add a staleTime so it doesn't refetch on every tiny click
    staleTime: 2000,
  });
}
