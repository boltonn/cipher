import { apiClient } from "@/lib/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

const SELECTED_KEY = ["users", "me", "selected-datasets"] as const;
const NONE: string[] = [];

const selectedDatasetsService = {
  get: async (): Promise<string[]> => (await apiClient.get<string[]>("/users/me/selected-datasets")).data,
  set: async (datasetIds: string[]): Promise<string[]> =>
    (await apiClient.put<string[]>("/users/me/selected-datasets", { datasetIds })).data,
};

/**
 * The datasets the user is working in, shared by Entities, Events, Search and Graph and kept on
 * the user (server-side) -- the API only ever returns datasets that exist and the user can access.
 */
export function useSelectedDatasets() {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({ queryKey: SELECTED_KEY, queryFn: selectedDatasetsService.get });
  const save = useMutation({
    mutationFn: selectedDatasetsService.set,
    onMutate: (datasetIds) => queryClient.setQueryData(SELECTED_KEY, datasetIds),
    onSuccess: (stored) => queryClient.setQueryData(SELECTED_KEY, stored),
    onError: () => queryClient.invalidateQueries({ queryKey: SELECTED_KEY }),
  });
  return { datasetIds: data ?? NONE, isPending, setDatasetIds: save.mutate };
}

/**
 * The selection, unless a deep link (`?datasetId=`) asked for specific datasets: those apply to
 * this view only until the picker is changed, which saves the new selection.
 */
export function useDatasetScope(linkedDatasetIds?: string[]) {
  const selected = useSelectedDatasets();
  const [linked, setLinked] = useState(linkedDatasetIds?.length ? linkedDatasetIds : undefined);
  const setDatasetIds = (datasetIds: string[]) => {
    setLinked(undefined);
    selected.setDatasetIds(datasetIds);
  };
  return {
    datasetIds: linked ?? selected.datasetIds,
    isPending: !linked && selected.isPending,
    setDatasetIds,
  };
}
