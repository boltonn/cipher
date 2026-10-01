import type {
  DatasetRequestConfig,
  DatasetRequestInput,
  DatasetRequestResult,
  EnrichmentRequestInput,
  EnrichmentRequestResult,
} from "@/features/datasets/request-types";
import { apiClient } from "@/lib/api-client";
import { useMutation, useQuery } from "@tanstack/react-query";

/** Target repo + a link to existing open requests. 503s when GitHub isn't configured. */
export function useDatasetRequestConfig() {
  return useQuery({
    queryKey: ["dataset-requests", "config"],
    queryFn: async () => {
      const { data } = await apiClient.get<DatasetRequestConfig>("/datasets/requests", {
        suppressErrorToast: true,
      });
      return data;
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useRequestDataset(onSuccess?: (result: DatasetRequestResult) => void) {
  return useMutation({
    mutationFn: async (payload: DatasetRequestInput) => {
      const { data } = await apiClient.post<DatasetRequestResult>(
        "/datasets/requests",
        payload
      );
      return data;
    },
    onSuccess,
  });
}

/** Render (and, when GitHub is configured, file) a request to run more analytics on a dataset. */
export function useRequestEnrichment() {
  return useMutation({
    mutationFn: async (payload: EnrichmentRequestInput) => {
      const { data } = await apiClient.post<EnrichmentRequestResult>(
        "/datasets/requests/enrichments",
        payload
      );
      return data;
    },
  });
}
