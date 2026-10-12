import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types/common";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import type { DatasetBrief, OverviewRequest, OverviewResponse, SearchAssist, SearchRecord } from "./types";

const overviewKey = (searchId: string) => ["search-overview", searchId] as const;

const globalSearchService = {
  /** Runs every lane and records the search; the response carries its `searchId`. */
  run: async (request: OverviewRequest): Promise<OverviewResponse> => {
    const { data } = await apiClient.post<OverviewResponse>("/search/overview", request);
    return data;
  },
  /** Re-runs a stored search (Back, reload) without recording it again. */
  rerun: async (searchId: string): Promise<OverviewResponse> => {
    const { data } = await apiClient.post<OverviewResponse>(`/search/history/${searchId}/overview`);
    return data;
  },
  assist: async (searchId: string): Promise<SearchAssist> => {
    const { data } = await apiClient.post<SearchAssist>(`/search/history/${searchId}/assist`, undefined, {
      suppressErrorToast: true,
    });
    return data;
  },
  brief: async (datasetIds: string[]): Promise<DatasetBrief> => {
    const { data } = await apiClient.get<DatasetBrief>("/datasets/profile/brief", {
      params: { datasetIds },
      suppressErrorToast: true,
    });
    return data;
  },
  regenerateBrief: async (datasetIds: string[]): Promise<DatasetBrief> => {
    const { data } = await apiClient.post<DatasetBrief>("/datasets/profile/brief", undefined, {
      params: { datasetIds },
    });
    return data;
  },
  history: async (limit: number, saved?: boolean): Promise<PaginatedResponse<SearchRecord>> => {
    const { data } = await apiClient.get<PaginatedResponse<SearchRecord>>("/search/history", {
      params: { limit, saved },
    });
    return data;
  },
  record: async (searchId: string): Promise<SearchRecord> => {
    const { data } = await apiClient.get<SearchRecord>(`/search/history/${searchId}`);
    return data;
  },
  setSaved: async ({ searchId, saved, name }: { searchId: string; saved: boolean; name?: string | null }) => {
    const url = `/search/history/${searchId}/saved`;
    const { data } = saved
      ? await apiClient.put<SearchRecord>(url, { name: name ?? null })
      : await apiClient.delete<SearchRecord>(url);
    return data;
  },
};

/** Run a search and open its results page; the page renders from the cache, no second request. */
export function useRunSearch() {
  const queryClient = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: globalSearchService.run,
    onSuccess: (overview) => {
      queryClient.setQueryData(overviewKey(overview.searchId), overview);
      queryClient.invalidateQueries({ queryKey: ["search-history"] });
      router.push(`/search/${overview.searchId}`);
    },
  });
}

/** One search's results page, by id: from the cache when just run, else re-run server-side. */
export function useSearchOverview(searchId: string) {
  return useQuery({
    queryKey: overviewKey(searchId),
    queryFn: () => globalSearchService.rerun(searchId),
    staleTime: 10 * 60_000,
    gcTime: 30 * 60_000,
  });
}

/** Your searches, most recently run first; `saved` narrows to saved (true) or unsaved (false) ones. */
export function useSearchHistory(limit = 8, enabled = true, saved?: boolean) {
  return useQuery({
    queryKey: ["search-history", limit, saved],
    queryFn: () => globalSearchService.history(limit, saved),
    enabled,
  });
}

/** One stored search -- its saved state and name. */
export function useSearchRecord(searchId: string) {
  return useQuery({
    queryKey: ["search-history", "record", searchId],
    queryFn: () => globalSearchService.record(searchId),
  });
}

/** Save (optionally named) or unsave a search. */
export function useSetSearchSaved() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: globalSearchService.setSaved,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["search-history"] }),
  });
}

/** The AI answer / suggested narrower search for a search; asked only after the results are on screen. */
export function useSearchAssist(searchId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["search-assist", searchId],
    queryFn: () => globalSearchService.assist(searchId),
    enabled,
    staleTime: Infinity,
    retry: false,
  });
}

const briefKey = (datasetIds: string[]) => ["datasets", "profile", "brief", datasetIds] as const;

/** AI summary of the selected datasets plus starting searches (saved server-side until regenerated). */
export function useDatasetBrief(datasetIds: string[], enabled: boolean) {
  return useQuery({
    queryKey: briefKey(datasetIds),
    queryFn: () => globalSearchService.brief(datasetIds),
    enabled,
    staleTime: Infinity,
    retry: false,
  });
}

/** Replace the saved summary with a fresh one from the current profile. */
export function useRegenerateBrief(datasetIds: string[]) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => globalSearchService.regenerateBrief(datasetIds),
    onSuccess: (brief) => queryClient.setQueryData(briefKey(datasetIds), brief),
  });
}
