// @/features/chat/types.ts

/** A retrieved passage the chat agent grounded its answer in -- returned as the
 * `search_documents` tool's output (see backend/src/cipher/api/routes/chat.py). */
export interface ChatCitation {
  chunkId: string;
  fileId: string;
  /** Filename for documents; subject line for emails. */
  displayName: string;
  filetypeGroup: "document" | "email";
  /** Document-only: page this passage came from, if known. */
  pageNumber?: number;
  /** Document-only: section heading hierarchy this passage falls under. */
  headingPath?: string[];
  startOffset: number;
  endOffset: number;
  snippet: string;
  score: number;
}
