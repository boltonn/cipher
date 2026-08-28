import type { Dataset, DatasetCreate } from "@/features/datasets/types";
import { apiClient } from "@/lib/api-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function useCreateDataset(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: DatasetCreate) =>
      apiClient.post<Dataset>("/datasets", payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      onSuccess?.();
    },
  });
}
