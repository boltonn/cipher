import { apiClient } from "@/lib/api-client";
import { useQuery } from "@tanstack/react-query";
import type { DatabaseMetrics, DatasetDatabaseUsage } from "./types";

/** Admin only. */
export function useDatabaseMetrics() {
  return useQuery({
    queryKey: ["admin", "database"],
    queryFn: async () => {
      const { data } = await apiClient.get<DatabaseMetrics>("/admin/database");
      return data;
    },
  });
}

/** Admin only. */
export function useDatasetDatabaseUsage(datasetId: string) {
  return useQuery({
    queryKey: ["admin", "database", "datasets", datasetId],
    queryFn: async () => {
      const { data } = await apiClient.get<DatasetDatabaseUsage>(
        `/admin/database/datasets/${datasetId}`
      );
      return data;
    },
  });
}
