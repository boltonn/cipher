// @/features/messages/api.ts
import {
  BaseMessageTextSearchParameters,
  ChunkContextRequestParams,
  ConversationChunkByChunkIdRequest,
  Message,
  PaginatedConversationChunksResponse,
  ScoredConversationChunk,
  TextSearchRequest,
} from "@/features/messages/types";
import { apiClient } from "@/lib/api-client";
import { UUID } from "crypto";

const messagesBaseURL = "/messages";

export const messagesService = {
  // GET /messages/{id}
  getMessageById: (id: string): Promise<Message> =>
    apiClient.get<Message>(`${messagesBaseURL}/${id}`).then((res) => res.data),

  // GET /messages/chunks/{id}
  getChunkById: (id: string): Promise<ScoredConversationChunk> =>
    apiClient
      .get<ScoredConversationChunk>(`${messagesBaseURL}/chunks/${id}`)
      .then((res) => res.data),

  getChunkContext: (
    chunkId: UUID,
    params: ChunkContextRequestParams
  ): Promise<ScoredConversationChunk[]> =>
    apiClient
      .get<
        ScoredConversationChunk[]
      >(`${messagesBaseURL}/chunks/${chunkId}/context`, { params })
      .then((res) => res.data),

  // GET /messages/conversations/{id}
  getConversationChunks: (
    id: string,
    limit?: number
  ): Promise<ScoredConversationChunk[]> =>
    apiClient
      .get<ScoredConversationChunk[]>(
        `${messagesBaseURL}/conversations/${id}`,
        {
          params: { limit },
        }
      )
      .then((res) => res.data),

  // POST /messages/search/text
  searchByText: (
    payload: TextSearchRequest
  ): Promise<PaginatedConversationChunksResponse> =>
    apiClient
      .post<PaginatedConversationChunksResponse>(
        `${messagesBaseURL}/search/text`,
        payload
      )
      .then((res) => res.data),

  // POST /messages/search/semantic
  searchBySemantic: (
    payload: BaseMessageTextSearchParameters
  ): Promise<PaginatedConversationChunksResponse> =>
    apiClient
      .post<PaginatedConversationChunksResponse>(
        `${messagesBaseURL}/search/semantic`,
        payload
      )
      .then((res) => res.data),

  // POST /messages/search/hybrid
  searchByHybrid: (
    payload: BaseMessageTextSearchParameters
  ): Promise<PaginatedConversationChunksResponse> =>
    apiClient
      .post<PaginatedConversationChunksResponse>(
        `${messagesBaseURL}/search/hybrid`,
        payload
      )
      .then((res) => res.data),

  // GET /messages/search/{chunk_id}
  searchByChunkId: (
    chunkId: string,
    params: ConversationChunkByChunkIdRequest
  ): Promise<PaginatedConversationChunksResponse> =>
    apiClient
      .get<PaginatedConversationChunksResponse>(
        `${messagesBaseURL}/search/${chunkId}`,
        { params }
      )
      .then((res) => res.data),

  // PATCH /messages/{message_id}/translation
  translateMessage: (
    messageId: string,
    translation: string
  ): Promise<boolean> =>
    apiClient
      .patch<boolean>(`${messagesBaseURL}/${messageId}/translation`, {
        translation,
      })
      .then((res) => res.data),
};
