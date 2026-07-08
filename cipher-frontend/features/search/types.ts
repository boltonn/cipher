// @/features/search/types.ts
import { PaginatedResponse } from "@/types/common";

export type SearchFiletypeGroup = "document" | "email";

export type SearchMode = "text" | "semantic" | "hybrid";

export type ChunkSortField = "date" | "_score" | "_knnScore";

export type SortOrder = "asc" | "desc";

// ─── Filters / Requests ─────────────────────────────────────────────────────

export interface SearchFilters {
  datasetId?: string;
  fileId?: string;
  tags?: string[];
  filetypeGroup?: SearchFiletypeGroup;
  filetype?: string;
}

export interface BaseChunkSearchParameters {
  filters?: SearchFilters;
  limit?: number;
  page?: number;
  sortBy?: ChunkSortField;
  sortOrder?: SortOrder;
}

export interface ChunkTextSearchRequest extends BaseChunkSearchParameters {
  query: string;
  /** Only applied by the semantic/hybrid endpoints -- ignored for BM25 text search, which has no equivalent bounded score to threshold on. */
  minSimilarity?: number;
}

// ─── Raw backend shapes (unified /search/{text,semantic,hybrid} router) ───────

interface TextChunkRawBase {
  id: string;
  fileId: string;
  chunkIndex: number;
  startOffset: number;
  endOffset: number;
  text: string;
  tags: string[];
  dateCreated: string;
  title?: string;
  score: number;
  /** Matched words/phrases from Elasticsearch highlighting; empty for pure kNN (semantic) results. */
  highlights?: string[];
}

export interface DocumentTextChunkRaw extends TextChunkRawBase {
  filetypeGroup: "document";
  filename: string;
}

export interface EmailTextChunkRaw extends TextChunkRawBase {
  filetypeGroup: "email";
}

export type SearchChunkRaw = DocumentTextChunkRaw | EmailTextChunkRaw;

export type PaginatedSearchChunksResponse = PaginatedResponse<SearchChunkRaw>;

// ─── Normalized UI shapes ───────────────────────────────────────────────────

/** Common row shape the search UI works with, merging document + email chunks. */
export interface SearchChunk {
  id: string;
  fileId: string;
  filetypeGroup: SearchFiletypeGroup;
  /** Filename for documents; subject line for emails -- the real filename is
   * resolved separately via `useFile` once a file is actually opened, since
   * `EmailTextChunk` carries no filename field of its own. */
  displayName: string;
  chunkIndex: number;
  startOffset: number;
  endOffset: number;
  text: string;
  score: number;
  tags: string[];
  dateCreated: string;
  /** Matched words/phrases from Elasticsearch highlighting; empty for pure kNN (semantic) results. */
  highlights: string[];
}

export interface GroupedFileResult {
  fileId: string;
  displayName: string;
  filetypeGroup: SearchFiletypeGroup;
  chunks: SearchChunk[];
  topScore: number;
}

/** `{ fileId, chunkId }` previews the highlighted chunk in extracted text; `{ fileId }` alone previews the rendered file. */
export interface SearchSelection {
  fileId: string;
  chunkId?: string;
}
