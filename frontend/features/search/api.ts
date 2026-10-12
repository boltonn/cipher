// @/features/search/api.ts
import { apiClient } from "@/lib/api-client";
import type {
  ChunkTextSearchRequest,
  FileSearchResultRaw,
  GroupedFileResult,
  PaginatedFileSearchResponse,
  SearchChunk,
  SearchChunkRaw,
  SourceFacets,
} from "./types";

export function toSearchChunk(raw: SearchChunkRaw): SearchChunk {
  return {
    id: raw.id,
    fileId: raw.fileId,
    filetypeGroup: raw.filetypeGroup,
    displayName: raw.filetypeGroup === "document" ? raw.filename : (raw.title ?? "(no subject)"),
    isSummary: raw.isSummary ?? false,
    chunkIndex: raw.chunkIndex,
    startOffset: raw.startOffset,
    endOffset: raw.endOffset,
    text: raw.text,
    score: raw.score,
    tags: raw.tags,
    dateCreated: raw.dateCreated,
    highlights: raw.highlights ?? [],
    mentionSpans: raw.mentionSpans ?? [],
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
    tags: raw.tags ?? [],
    sourceTags: raw.sourceTags ?? [],
    messageStates: raw.messageStates ?? [],
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

  // GET /search/source-facets -- tags and message states that came with the data, with file counts
  sourceFacets: (datasetIds?: string[]): Promise<SourceFacets> =>
    apiClient.get<SourceFacets>(`${searchBaseURL}/source-facets`, { params: { datasetIds } }).then((res) => res.data),

  // POST /search/hybrid
  searchHybrid: (payload: ChunkTextSearchRequest): Promise<PaginatedFileSearchResponse> =>
    apiClient.post<PaginatedFileSearchResponse>(`${searchBaseURL}/hybrid`, payload).then((res) => res.data),
};
