// @/features/search/api.ts
import { apiClient } from "@/lib/api-client";
import type {
  ChunkTextSearchRequest,
  FileSearchResultRaw,
  GroupedFileResult,
  PaginatedFileSearchResponse,
  SearchChunk,
  SearchChunkRaw,
} from "./types";

export function toSearchChunk(raw: SearchChunkRaw): SearchChunk {
  return {
    id: raw.id,
    fileId: raw.fileId,
    filetypeGroup: raw.filetypeGroup,
    displayName: raw.filetypeGroup === "document" ? raw.filename : (raw.title ?? "(no subject)"),
    chunkIndex: raw.chunkIndex,
    startOffset: raw.startOffset,
    endOffset: raw.endOffset,
    text: raw.text,
    score: raw.score,
    tags: raw.tags,
    dateCreated: raw.dateCreated,
    highlights: raw.highlights ?? [],
    pageNumber: raw.filetypeGroup === "document" ? raw.pageNumber : undefined,
    headingPath: raw.filetypeGroup === "document" ? raw.headingPath : undefined,
  };
}

export function toGroupedFileResult(raw: FileSearchResultRaw): GroupedFileResult {
  const chunks = raw.chunks.map(toSearchChunk);
  const topChunk = chunks.find((c) => c.id === raw.topChunkId) ?? chunks[0];
  return {
    fileId: raw.fileId,
    displayName: topChunk.displayName,
    filetypeGroup: topChunk.filetypeGroup,
    chunks,
    topScore: raw.topScore,
    topChunkId: raw.topChunkId,
    matchCount: raw.matchCount,
  };
}

const searchBaseURL = "/search";

export const searchService = {
  // POST /search/text -- BM25 across documents and emails together, grouped by file server-side
  searchText: (payload: ChunkTextSearchRequest): Promise<PaginatedFileSearchResponse> =>
    apiClient.post<PaginatedFileSearchResponse>(`${searchBaseURL}/text`, payload).then((res) => res.data),

  // POST /search/semantic
  searchSemantic: (payload: ChunkTextSearchRequest): Promise<PaginatedFileSearchResponse> =>
    apiClient.post<PaginatedFileSearchResponse>(`${searchBaseURL}/semantic`, payload).then((res) => res.data),

  // POST /search/hybrid
  searchHybrid: (payload: ChunkTextSearchRequest): Promise<PaginatedFileSearchResponse> =>
    apiClient.post<PaginatedFileSearchResponse>(`${searchBaseURL}/hybrid`, payload).then((res) => res.data),
};
