import type {
  FileBrowserRequest,
  FileBrowserResponse,
  FileRecord,
  FileTables,
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
  /** Browser-displayable JPEG (HEIC transcoded server-side); no Image pipeline row needed. */
  getPreviewUrl: (id: string, maxDim = 1600) => `${baseURL}/files/${id}/preview?max=${maxDim}`,
  // A 404 here just means "not extracted/indexed yet" -- not an error worth toasting.
  getFileText: async (id: string): Promise<FileText> => {
    const { data } = await apiClient.get<FileText>(`/files/${id}/text`, {
      suppressErrorToast: true,
    });
    return data;
  },
  // A 404 here just means "not extracted yet, or nothing tabular in this file" -- not an error worth toasting.
  getFileTable: async (id: string): Promise<FileTables> => {
    const { data } = await apiClient.get<FileTables>(`/files/${id}/table`, {
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

/** A 404 (not yet extracted, or nothing tabular) resolves as `isError`, not a thrown/toasted error. */
export function useFileTable(fileId: string | undefined) {
  return useQuery({
    queryKey: ["files", fileId, "table"],
    queryFn: () => filesService.getFileTable(fileId as string),
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
