import { isAxiosError } from "axios";
import type {
  FileBrowserRequest,
  FileBrowserResponse,
  FileRecord,
  FileSummary,
  FileTables,
  FileText,
  TextCorrectionRequest,
  TextCorrectionSummary,
} from "@/features/files/types";
import { apiClient, baseURL } from "@/lib/api-client";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

export const filesService = {
  /** Label many files' content with one tag, as the current user. */
  tagMany: async (tag: string, fileIds: string[]): Promise<void> => {
    await apiClient.post("/files/tag", { tag, fileIds });
  },
  getById: async (id: string): Promise<FileRecord> => {
    const { data } = await apiClient.get<FileRecord>(`/files/${id}`);
    return data;
  },
  /** The cached summary, or null when the file hasn't been summarized (404). */
  getSummary: async (id: string): Promise<FileSummary | null> => {
    try {
      const { data } = await apiClient.get<FileSummary>(`/files/${id}/summary`, {
        suppressErrorToast: true,
      });
      return data;
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 404) return null;
      throw error;
    }
  },
  summarize: async (id: string, force = false): Promise<FileSummary> => {
    const { data } = await apiClient.post<FileSummary>(`/files/${id}/summary`, null, {
      params: { force: force || undefined },
    });
    return data;
  },
  setTags: async (id: string, tags: string[]): Promise<FileRecord> => {
    const { data } = await apiClient.put<FileRecord>(`/files/${id}/tags`, {
      tags,
    });
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
  /** Files found inside it: an email's attachments, an archive's members (path order). */
  getChildren: async (id: string): Promise<FileRecord[]> => {
    const { data } = await apiClient.get<FileRecord[]>(`/files/${id}/children`);
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
  /** Replace an OCR'd text on every copy of the file; `dryRun` only reports what would change. */
  correctText: async (id: string, body: TextCorrectionRequest): Promise<TextCorrectionSummary> => {
    const { data } = await apiClient.put<TextCorrectionSummary>(`/files/${id}/text`, body);
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

/** Set a file's tags; the cached file record is replaced with the server's. */
export function useSetFileTags(fileId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tags: string[]) => filesService.setTags(fileId, tags),
    onSuccess: (file) => queryClient.setQueryData(["files", fileId], file),
  });
}

export function useFileSummary(fileId: string) {
  return useQuery({
    queryKey: ["files", fileId, "summary"],
    queryFn: () => filesService.getSummary(fileId),
    staleTime: 60_000,
  });
}

/** Summarize a file with the LLM (slow: ~20s); the result is cached server-side as a summary chunk. */
export function useSummarizeFile(fileId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (force: boolean) => filesService.summarize(fileId, force),
    onSuccess: (summary) => queryClient.setQueryData(["files", fileId, "summary"], summary),
  });
}

export function useFile(fileId: string | undefined) {
  return useQuery({
    queryKey: ["files", fileId],
    queryFn: () => filesService.getById(fileId as string),
    enabled: !!fileId,
    staleTime: 60_000,
  });
}

export function useFileChildren(fileId: string | undefined) {
  return useQuery({
    queryKey: ["files", fileId, "children"],
    queryFn: () => filesService.getChildren(fileId as string),
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

/** Correct a file's OCR text; a saved correction refreshes its text and mentions (every copy shares them). */
export function useCorrectFileText(fileId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TextCorrectionRequest) => filesService.correctText(fileId, body),
    onSuccess: (_, body) => {
      if (body.dryRun) return;
      qc.invalidateQueries({ queryKey: ["files"] });
      qc.invalidateQueries({ queryKey: ["mentions"] });
    },
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

/** Tag many files at once; cached file records are refetched so their tags show. */
export function useTagFiles() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ tag, fileIds }: { tag: string; fileIds: string[] }) => filesService.tagMany(tag, fileIds),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["files"] }),
  });
}
