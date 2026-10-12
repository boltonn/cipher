import type {
  Dataset,
  DatasetEnrichmentFailures,
  DatasetProfile,
  DatasetRequest,
  DatasetStatsRequest,
  DatasetStatsResponse,
  DatasetSummary,
  DatasetUpdate,
  EnrichmentProgress,
  SweepRun,
} from "@/features/datasets/types";
import type {
  DatasetEnrichmentEstimates,
  EnrichmentConfig,
} from "@/features/datasets/request-types";
import type { User } from "@/features/users/types";
import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types/common";
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

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
  getStats: async (
    id: string,
    params?: DatasetStatsRequest
  ): Promise<DatasetStatsResponse> => {
    const { data } = await apiClient.get<DatasetStatsResponse>(
      `/datasets/${id}/stats`,
      { params }
    );
    return data;
  },
  update: async (id: string, payload: DatasetUpdate): Promise<Dataset> => {
    const { data } = await apiClient.put<Dataset>(`/datasets/${id}`, payload);
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/datasets/${id}`);
  },
  getProfile: async (datasetIds: string[]): Promise<DatasetProfile> => {
    const { data } = await apiClient.get<DatasetProfile>("/datasets/profile", {
      params: { datasetIds },
    });
    return data;
  },
  getUsers: async (id: string): Promise<User[]> => {
    const { data } = await apiClient.get<User[]>(`/datasets/${id}/users`);
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

/** Users with explicit membership in a dataset (admins can see it without being listed). */
export function useDatasetUsers(id: string | undefined) {
  return useQuery({
    queryKey: ["datasets", id, "users"],
    queryFn: () => datasetService.getUsers(id as string),
    enabled: !!id,
    staleTime: 60_000,
  });
}

export function useDatasetStats(
  id: string | undefined,
  params: DatasetStatsRequest
) {
  return useQuery({
    queryKey: ["datasets", id, "stats", params],
    queryFn: () => datasetService.getStats(id as string, params),
    enabled: !!id,
    staleTime: 10_000,
  });
}

/** Per-analytic enrichment progress for a dataset, in pipeline order. */
export function useEnrichmentProgress(id: string | undefined) {
  return useQuery({
    queryKey: ["datasets", id, "enrichment-progress"],
    queryFn: async () => {
      const { data } = await apiClient.get<EnrichmentProgress[]>(
        "/enrichments/progress/all",
        { params: { datasetId: id }, suppressErrorToast: true }
      );
      return data;
    },
    enabled: !!id,
    staleTime: 15_000,
    // Poll while a worker is on any step so the bars animate; stopped queues don't move.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((p) => p.isRunning) ? 4000 : false,
  });
}

/** The latest entity-resolution run (`cipher resolve-entities`) with its steps; polls while it runs. */
export function useResolutionRun(id: string | undefined) {
  return useQuery({
    queryKey: ["datasets", id, "resolution-run"],
    queryFn: async () => {
      const { data } = await apiClient.get<SweepRun | null>(
        "/enrichments/resolution",
        { params: { datasetId: id }, suppressErrorToast: true }
      );
      return data;
    },
    enabled: !!id,
    staleTime: 15_000,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 3000 : false,
  });
}

/** Rough per-enrichment time estimates for a dataset, each on the device that analytic runs on. */
export function useEnrichmentEstimates(datasetId: string | undefined) {
  return useQuery({
    queryKey: ["datasets", datasetId, "enrichment-estimates"],
    queryFn: async () => {
      const { data } = await apiClient.get<DatasetEnrichmentEstimates>(
        `/datasets/${datasetId}/enrichment-estimates`,
        { suppressErrorToast: true }
      );
      return data;
    },
    enabled: !!datasetId && datasetId.trim().length > 0,
    staleTime: 30_000,
    retry: false,
  });
}

/** Trigger a model-free enrichment (e.g. EXIF location extraction) to run in the background. */
/** Static pipeline metadata (order + hard prerequisites); never changes at runtime. */
export function useEnrichmentConfig() {
  return useQuery({
    queryKey: ["enrichments", "config"],
    queryFn: async () => {
      const { data } = await apiClient.get<EnrichmentConfig>("/enrichments/config");
      return data;
    },
    staleTime: Infinity,
  });
}

export function useRunEnrichment(datasetId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (enrichmentType: string) => {
      const { data } = await apiClient.post<{ status: string; detail: string }>(
        "/enrichments/run",
        {
          datasetId,
          enrichmentType,
        }
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["datasets", datasetId, "enrichment-progress"],
      });
    },
  });
}

/** Failed enrichments for one analytic in a dataset -- grouped reasons plus per-file detail. */
export function useEnrichmentFailures(
  datasetId: string | undefined,
  enrichmentType: string | null,
  page: { limit: number; offset: number }
) {
  return useQuery({
    queryKey: [
      "datasets",
      datasetId,
      "enrichment-failures",
      enrichmentType,
      page,
    ],
    queryFn: async () => {
      const { data } = await apiClient.get<DatasetEnrichmentFailures>(
        "/enrichments/failures",
        {
          params: { datasetId, enrichmentType, ...page },
          suppressErrorToast: true,
        }
      );
      return data;
    },
    enabled: !!datasetId && !!enrichmentType,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useUpdateDataset(id: string, onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: DatasetUpdate) => datasetService.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      onSuccess?.();
    },
  });
}

export function useDeleteDataset(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => datasetService.delete(id),
    onSuccess: (_data, id) => {
      // The detail page (useDataset/useDatasetStats/the file browser, all
      // keyed ["datasets", id, ...]) is still mounted for a beat before the
      // redirect completes. Touching those keys at all here -- invalidating
      // *or* removing -- makes React Query refetch them to satisfy their
      // still-active observers, 404ing against a dataset that's already
      // gone and popping the global error toast, once per query. Since
      // we're navigating away and never need that data again, the fix is to
      // leave the id-scoped subtree alone entirely and only invalidate the
      // list queries (a structurally different key: an object, not this id).
      queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === "datasets" && query.queryKey[1] !== id,
      });
      onSuccess?.();
    },
  });
}

/** Merged profile of `datasetIds` (empty = every accessible dataset): the search briefing. */
export function useDatasetProfile(datasetIds: string[]) {
  return useQuery({
    queryKey: ["datasets", "profile", datasetIds],
    queryFn: () => datasetService.getProfile(datasetIds),
    staleTime: 5 * 60_000,
  });
}
