// @/features/messages/types.ts
import { PaginatedResponse } from "@/types/common";
import { UUID } from "crypto";

// ─── Enums ────────────────────────────────────────────────────────────────────

export type MessageStatus = "inbox" | "sent" | "draft" | "deleted";

export type ChunkSortField = "date" | "_score" | "_knnScore";

export type SortOrder = "asc" | "desc";

// ─── Core Models ──────────────────────────────────────────────────────────────

export interface MessageBase {
  conversationId: string;
  dateSent?: string;
  dateReceived?: string;
  messageId?: string;
  messageStatus?: MessageStatus;
  recipient?: string;
  recipientType?: string;
  sender?: string;
  senderType?: string;
  text?: string;
  meaningfulHash?: string;
}

export interface Message extends MessageBase {
  id: UUID;
  fileId?: string;
  deviceId?: UUID;
}

export interface ConversationChunkPublic {
  id: UUID;
  messages: Message[];
  conversationId: string;
  date: string;
  tags: string[];
  hardNegativeTags: string[];
}

export interface ScoredConversationChunk extends ConversationChunkPublic {
  score: number;
}

export interface ScoredMessage extends Message {
  score: number;
}

// ─── Filters ──────────────────────────────────────────────────────────────────

export interface MessageFilters {
  deviceId?: UUID;
  conversationId?: string;
  sender?: string;
  recipient?: string;
  messageStatus?: MessageStatus;
  sourceType?: string;
  language?: string;
  isRead?: boolean;
  isLocked?: boolean;
  dateSentFrom?: string;
  dateSentTo?: string;
  dateReceivedFrom?: string;
  dateReceivedTo?: string;
}

export type PaginatedConversationChunksResponse =
  PaginatedResponse<ScoredConversationChunk>;

export type PaginatedMessagesResponse = PaginatedResponse<Message>;

// ─── Request Parameters ───────────────────────────────────────────────────────

export interface BaseMessageSearchParameters {
  filters?: MessageFilters;
  limit?: number;
  page?: number;
  returnMessages?: boolean;
  sortBy?: ChunkSortField;
  sortOrder?: SortOrder;
}

export interface BaseMessageTextSearchParameters extends BaseMessageSearchParameters {
  query: string;
  sortBy?: ChunkSortField;
}

export interface TextSearchRequest extends BaseMessageTextSearchParameters {
  returnMessages?: boolean;
}

export interface ConversationChunkByChunkIdRequest extends BaseMessageSearchParameters {
  minSimilarity?: number;
  numCandidates?: number;
}

export interface ChunkContextRequestParams {
  limit?: number;
  cursor: string;
  isAfter?: boolean;
}

export type AnnotationMode = "tag" | "relevance" | null;
