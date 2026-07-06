import type {
  FileBrowserRequest,
  FileBrowserResponse,
  FileRecord,
  FileText,
} from "@/features/files/types";
import { apiClient, baseURL } from "@/lib/api-client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

export const filesService = {
  getById: async (id: string): Promise<FileRecord> => {
    const { data } = await apiClient.get<FileRecord>(`/files/${id}`);
    return data;
  },
  browseDataset: async (
    datasetId: string,
    params?: FileBrowserRequest
  ): Promise<FileBrowserResponse> => {
    const { data } = await apiClient.get<FileBrowserResponse>(`/datasets/${datasetId}/browse`, {
      params,
    });
    return data;
  },
  getFileUrl: (id: string) => `${baseURL}/files/${id}/view`,
  // A 404 here just means "not extracted/indexed yet" -- not an error worth toasting.
  getFileText: async (id: string): Promise<FileText> => {
    const { data } = await apiClient.get<FileText>(`/files/${id}/text`, {
      suppressErrorToast: true,
    });
    return data;
  },
};

export function useFile(fileId: string | undefined) {
  return useQuery({
    queryKey: ["files", fileId],
    queryFn: () => filesService.getById(fileId as string),
    enabled: !!fileId,
    staleTime: 60_000,
  });
}

/** A 404 (not yet extracted/indexed) resolves as `isError`, not a thrown/toasted error. */
export function useFileText(fileId: string | undefined) {
  return useQuery({
    queryKey: ["files", fileId, "text"],
    queryFn: () => filesService.getFileText(fileId as string),
    enabled: !!fileId,
    staleTime: 60_000,
    retry: false,
  });
}

/**
 * Paginated, path-scoped browser for a dataset's files. The backend caps
 * `limit` at 100 per page regardless of what's requested, so this stays safe
 * even for directories with thousands of entries -- `keepPreviousData` just
 * avoids a loading flash between page/folder navigations.
 */
export function useDatasetFileBrowser(datasetId: string | undefined, params: FileBrowserRequest) {
  return useQuery({
    queryKey: ["datasets", datasetId, "browse", params],
    queryFn: () => filesService.browseDataset(datasetId as string, params),
    enabled: !!datasetId,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}
