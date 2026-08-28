import { apiClient } from "@/lib/api-client";
import type {
  Entity,
  EntityCreatePayload,
  EntityDetail,
  EntityMatch,
  EntityProfile,
  EntityRelationship,
  EntitySearchParameters,
  EntitySearchResult,
  EntityUpdatePayload,
  GraphResponse,
  Mention,
  MentionCreatePayload,
  MentionResolvePayload,
  MentionUpdatePayload,
  PaginatedEntitiesResponse,
  PaginatedEntityMatchesResponse,
  PaginatedMentionsResponse,
  PaginatedRelationshipsResponse,
  RelationshipType,
  TraversalDirection,
} from "@/features/entities/types";

const entitiesBaseURL = "/entities";
const mentionsBaseURL = "/mentions";

export const entitiesService = {
  list: (params: EntitySearchParameters) =>
    apiClient
      .get<PaginatedEntitiesResponse>(entitiesBaseURL, { params })
      .then((res) => res.data),

  // GET /entities/search takes plain (snake_case) query params, not a model.
  search: (opts: {
    datasetId: string;
    q?: string;
    selector?: string;
    limit?: number;
  }) =>
    apiClient
      .get<EntitySearchResult[]>(`${entitiesBaseURL}/search`, {
        params: {
          dataset_id: opts.datasetId,
          q: opts.q,
          selector: opts.selector,
          limit: opts.limit ?? 8,
        },
      })
      .then((res) => res.data),

  getById: (id: string) =>
    apiClient.get<Entity>(`${entitiesBaseURL}/${id}`).then((res) => res.data),

  // A 404 just means "no knowledge-graph node for this id yet" (e.g. a person
  // page opened before its bridge entity exists) -- not an error worth toasting.
  getProfile: (id: string) =>
    apiClient
      .get<EntityProfile>(`${entitiesBaseURL}/${id}/profile`, {
        suppressErrorToast: true,
      })
      .then((res) => res.data),

  create: (payload: EntityCreatePayload) =>
    apiClient.post<Entity>(entitiesBaseURL, payload).then((res) => res.data),

  update: (id: string, payload: EntityUpdatePayload) =>
    apiClient
      .patch<Entity>(`${entitiesBaseURL}/${id}`, payload)
      .then((res) => res.data),

  updateDetail: (id: string, detail: Record<string, unknown>) =>
    apiClient
      .patch<EntityDetail>(`${entitiesBaseURL}/${id}/detail`, detail)
      .then((res) => res.data),

  delete: (id: string) =>
    apiClient.delete(`${entitiesBaseURL}/${id}`).then((res) => res.data),

  getMentions: (
    id: string,
    params?: { fileId?: string; limit?: number; page?: number }
  ) =>
    apiClient
      .get<PaginatedMentionsResponse>(`${entitiesBaseURL}/${id}/mentions`, {
        params: {
          file_id: params?.fileId,
          limit: params?.limit ?? 50,
          page: params?.page ?? 1,
        },
      })
      .then((res) => res.data),

  getRelationships: (
    id: string,
    params?: {
      direction?: TraversalDirection;
      relationshipType?: RelationshipType;
      limit?: number;
    }
  ) =>
    apiClient
      .get<PaginatedRelationshipsResponse>(
        `${entitiesBaseURL}/${id}/relationships`,
        {
          params: {
            direction: params?.direction ?? "both",
            relationship_type: params?.relationshipType,
            limit: params?.limit ?? 100,
          },
        }
      )
      .then((res) => res.data),

  getGraph: (
    id: string,
    params?: {
      depth?: number;
      direction?: TraversalDirection;
      types?: RelationshipType[];
      limit?: number;
    }
  ) =>
    apiClient
      .get<GraphResponse>(`${entitiesBaseURL}/${id}/graph`, {
        params: {
          depth: params?.depth ?? 2,
          direction: params?.direction ?? "both",
          types: params?.types?.length ? params.types.join(",") : undefined,
          limit: params?.limit ?? 150,
        },
      })
      .then((res) => res.data),

  createRelationship: (
    srcEntityId: string,
    payload: {
      datasetId: string;
      dstEntityId: string;
      relationshipType: RelationshipType;
      source?: string;
    }
  ) =>
    apiClient
      .post<EntityRelationship>(
        `${entitiesBaseURL}/${srcEntityId}/relationships`,
        {
          ...payload,
          srcEntityId,
          source: payload.source ?? "manual",
        }
      )
      .then((res) => res.data),

  listMatches: (params: {
    datasetId?: string;
    entityId?: string;
    status?: string;
    limit?: number;
    page?: number;
  }) =>
    apiClient
      .get<PaginatedEntityMatchesResponse>(`${entitiesBaseURL}/matches`, {
        params,
      })
      .then((res) => res.data),

  resolveMatch: (
    matchId: string,
    review: { status: string; reviewedBy: string; reviewNote?: string }
  ) =>
    apiClient
      .post<EntityMatch>(
        `${entitiesBaseURL}/matches/${matchId}/resolve`,
        review
      )
      .then((res) => res.data),
};

export const mentionsService = {
  list: (params: {
    fileId?: string;
    datasetId?: string;
    entityId?: string;
    resolved?: boolean;
    mentionedType?: string;
    limit?: number;
    page?: number;
  }) =>
    apiClient
      .get<PaginatedMentionsResponse>(mentionsBaseURL, {
        params: { limit: 200, page: 1, ...params },
      })
      .then((res) => res.data),

  create: (payload: MentionCreatePayload) =>
    apiClient
      .post<Mention>(mentionsBaseURL, { extractor: "manual", ...payload })
      .then((res) => res.data),

  update: (id: string, payload: MentionUpdatePayload) =>
    apiClient
      .patch<Mention>(`${mentionsBaseURL}/${id}`, payload)
      .then((res) => res.data),

  delete: (id: string) =>
    apiClient.delete(`${mentionsBaseURL}/${id}`).then((res) => res.data),

  resolve: (id: string, payload: MentionResolvePayload) =>
    apiClient
      .post<Mention>(`${mentionsBaseURL}/${id}/resolve`, payload)
      .then((res) => res.data),
};
