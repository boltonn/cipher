// @/features/search/api.ts
import { apiClient } from "@/lib/api-client";
import type { ChunkTextSearchRequest, PaginatedSearchChunksResponse, SearchChunk, SearchChunkRaw } from "./types";

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
  };
}

const searchBaseURL = "/search";

export const searchService = {
  // POST /search/text -- BM25 across documents and emails together, real server-side pagination
  searchText: (payload: ChunkTextSearchRequest): Promise<PaginatedSearchChunksResponse> =>
    apiClient.post<PaginatedSearchChunksResponse>(`${searchBaseURL}/text`, payload).then((res) => res.data),

  // POST /search/semantic
  searchSemantic: (payload: ChunkTextSearchRequest): Promise<PaginatedSearchChunksResponse> =>
    apiClient.post<PaginatedSearchChunksResponse>(`${searchBaseURL}/semantic`, payload).then((res) => res.data),

  // POST /search/hybrid
  searchHybrid: (payload: ChunkTextSearchRequest): Promise<PaginatedSearchChunksResponse> =>
    apiClient.post<PaginatedSearchChunksResponse>(`${searchBaseURL}/hybrid`, payload).then((res) => res.data),
};
