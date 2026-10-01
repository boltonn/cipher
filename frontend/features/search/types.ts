// @/features/search/types.ts
import type { MentionProvenance } from "@/features/entities/types";
import { PaginatedResponse } from "@/types/common";

export type SearchFiletypeGroup = "document" | "email";

export type SearchMode = "text" | "semantic" | "hybrid";

export type ChunkSortField = "dateCreated" | "score";

export type SortOrder = "asc" | "desc";

// ─── Filters / Requests ─────────────────────────────────────────────────────

export interface SearchFilters {
  datasetId?: string;
  fileId?: string;
  tags?: string[];
  filetypeGroup?: SearchFiletypeGroup;
  filetype?: string;
  /** Passages that mention every one of these entities -- composes with any search mode. */
  entityIds?: string[];
  /** Files with a mention of every one of these values (`normalizedValue`, resolved or not) -- an IP, a name group. */
  mentionValues?: string[];
  /** Where a `mentionValues` hit must be found -- body text vs email headers vs other metadata fields; omit for anywhere. */
  mentionProvenance?: MentionProvenance[];
  /** Email header filters (entity ids -- a person/org or an address selector); any-of. */
  sentFrom?: string[];
  sentTo?: string[];
  /** Picker ISO timestamps; sent as `yyyy-MM-dd` days (inclusive). */
  dateFrom?: string;
  dateTo?: string;
  entityTypes?: string[];
  selectorTypes?: string[];
  selectorSubtypes?: string[];
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

/** Where a filtered entity or mention value occurs, in extracted-text offsets. */
export interface MentionSpan {
  entityId?: string | null;
  normalizedValue?: string | null;
  startOffset: number;
  endOffset: number;
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
  mentionSpans?: MentionSpan[];
}

export interface DocumentTextChunkRaw extends TextChunkRawBase {
  filetypeGroup: "document";
  filename: string;
  pageNumber?: number;
  headingPath?: string[];
}

export interface EmailTextChunkRaw extends TextChunkRawBase {
  filetypeGroup: "email";
}

export type SearchChunkRaw = DocumentTextChunkRaw | EmailTextChunkRaw;

/** One file's search hit, as the `/search/*` endpoints actually return it --
 * grouped by file via an Elasticsearch `collapse` in the query itself, not
 * reassembled client-side from a flat chunk list. */
export interface FileSearchResultRaw {
  fileId: string;
  topScore: number;
  topChunkId: string;
  /** Total matching chunks in this file; may exceed `chunks.length` if capped server-side. */
  matchCount: number;
  /** Matching chunks, in reading order. */
  chunks: SearchChunkRaw[];
}

export type PaginatedFileSearchResponse = PaginatedResponse<FileSearchResultRaw> & {
  /** False for semantic / hybrid: `total` only counts the ranked candidate pool's files, not every match. */
  totalIsExact: boolean;
};

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
  /** Mentions of the filtered entities inside this chunk (file-level offsets). */
  mentionSpans: MentionSpan[];
  /** Document-only: page this chunk's text came from, if known. */
  pageNumber?: number;
  /** Document-only: section heading hierarchy this chunk falls under. */
  headingPath?: string[];
}

export interface GroupedFileResult {
  fileId: string;
  displayName: string;
  filetypeGroup: SearchFiletypeGroup;
  /** Matching chunks for this file, in document reading order (server-capped, see `matchCount`). */
  chunks: SearchChunk[];
  topScore: number;
  /** id of the chunk that scored `topScore` -- the snippet shown for this group and the default selection on click. */
  topChunkId: string;
  /** Total matching chunks in this file; may exceed `chunks.length` if capped server-side. */
  matchCount: number;
}

/** Selecting a search result always includes its matched `chunkId`; `chunkId` stays optional for a plain file-browser-style selection with no match to highlight. */
export interface SearchSelection {
  fileId: string;
  chunkId?: string;
}
