import { apiClient } from "@/lib/api-client";
import type {
  Entity,
  EntityBreakdown,
  EntityCreatePayload,
  EntityDetail,
  EntityMatch,
  EntityMatchBatchItem,
  EntityProfile,
  EntityRelationship,
  EntitySearchParameters,
  EntitySearchResult,
  EntityUpdatePayload,
  GraphResponse,
  Mention,
  MentionCreatePayload,
  MentionProvenance,
  MentionResolvePayload,
  MentionUpdatePayload,
  Ontology,
  PaginatedEntitiesResponse,
  PaginatedEntityMatchesResponse,
  PaginatedEntityMatchGroupsResponse,
  PaginatedEntityMergeGroupsResponse,
  PaginatedMentionsResponse,
  PaginatedRelatedEntitiesResponse,
  PaginatedRelationshipsResponse,
  PaginatedUnresolvedNamesResponse,
  EntityType,
  RelatedEntitySort,
  RelationshipType,
  ResolveNameGroupPayload,
  SelectorLinkPayload,
  SelectorMention,
  SelectorRegion,
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

  // Entity-layer registry (relationship types, endpoint constraints, roles).
  getOntology: () =>
    apiClient
      .get<Ontology>(`${entitiesBaseURL}/ontology`)
      .then((res) => res.data),

  // Entity / selector counts for a dataset -- the dataset-view breakdown chart.
  getBreakdown: (datasetId?: string) =>
    apiClient
      .get<EntityBreakdown>(`${entitiesBaseURL}/breakdown`, {
        params: { datasetId },
      })
      .then((res) => res.data),

  // ISO-3166-1 alpha-2 regions the phone normalizer accepts (for the selector form).
  listSelectorRegions: () =>
    apiClient
      .get<SelectorRegion[]>(`${entitiesBaseURL}/selector-regions`)
      .then((res) => res.data),

  // Create-or-reuse a selector node for `rawValue` and link it to this entity
  // with a has_selector edge. Returns the selector plus how many mentions already
  // carry its normalized value.
  attachSelector: (id: string, payload: SelectorLinkPayload) =>
    apiClient
      .post<SelectorMention>(`${entitiesBaseURL}/${id}/selectors`, payload)
      .then((res) => res.data),

  // Remove the has_selector edge; the selector node itself is left intact.
  detachSelector: (id: string, selectorId: string) =>
    apiClient
      .delete(`${entitiesBaseURL}/${id}/selectors/${selectorId}`)
      .then((res) => res.data),

  delete: (id: string) =>
    apiClient.delete(`${entitiesBaseURL}/${id}`).then((res) => res.data),

  getMentions: (
    id: string,
    params?: {
      fileId?: string;
      provenance?: MentionProvenance;
      limit?: number;
      page?: number;
    }
  ) =>
    apiClient
      .get<PaginatedMentionsResponse>(`${entitiesBaseURL}/${id}/mentions`, {
        params: {
          file_id: params?.fileId,
          provenance: params?.provenance,
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

  // Paginated neighbours of an entity, each with its connecting edge; sortable
  // by edge weight (emails sent for emailed). Powers the entity
  // dossier's Relationships and Selectors sections.
  getRelated: (
    id: string,
    params?: {
      direction?: TraversalDirection;
      relationshipType?: RelationshipType;
      entityType?: EntityType;
      sort?: RelatedEntitySort;
      limit?: number;
      page?: number;
    }
  ) =>
    apiClient
      .get<PaginatedRelatedEntitiesResponse>(`${entitiesBaseURL}/${id}/related`, {
        params: {
          direction: params?.direction ?? "both",
          relationship_type: params?.relationshipType,
          entity_type: params?.entityType,
          sort: params?.sort ?? "weight",
          limit: params?.limit ?? 25,
          page: params?.page ?? 1,
        },
      })
      .then((res) => res.data),

  getGraph: (
    id: string,
    params?: {
      depth?: number;
      direction?: TraversalDirection;
      types?: RelationshipType[];
      limit?: number;
      minWeight?: number;
    }
  ) =>
    apiClient
      .get<GraphResponse>(`${entitiesBaseURL}/${id}/graph`, {
        params: {
          depth: params?.depth ?? 2,
          direction: params?.direction ?? "both",
          types: params?.types?.length ? params.types.join(",") : undefined,
          limit: params?.limit ?? 500,
          min_weight: params?.minWeight ?? 0,
        },
      })
      .then((res) => res.data),

  createRelationship: (
    srcEntityId: string,
    payload: {
      /** Omit for edges between dataset-agnostic nodes; the backend derives it from the endpoints. */
      datasetId?: string;
      dstEntityId: string;
      relationshipType: RelationshipType;
      attributes?: Record<string, unknown>;
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

  // The grouped resolution review queue: one card per unresolved name, its best
  // candidate plus alternatives, each carrying the per-feature `explanation`.
  listMatchGroups: (params: {
    datasetId: string;
    status?: string;
    minSimilarity?: number;
    sortBy?: "similarity_score" | "date_created";
    limit?: number;
    page?: number;
  }) =>
    apiClient
      .get<PaginatedEntityMatchGroupsResponse>(
        `${entitiesBaseURL}/matches/groups`,
        {
          params: {
            dataset_id: params.datasetId,
            status: params.status ?? "pending",
            min_similarity: params.minSimilarity,
            sort_by: params.sortBy ?? "similarity_score",
            limit: params.limit ?? 25,
            page: params.page ?? 1,
          },
        }
      )
      .then((res) => res.data),

  // Confirm / reject many candidates in one transaction (the bulk-annotation path).
  resolveMatchesBatch: (body: {
    reviewedBy: string;
    decisions: EntityMatchBatchItem[];
  }) =>
    apiClient
      .post<{ confirmed: number; rejected: number; notFound: number }>(
        `${entitiesBaseURL}/matches/resolve-batch`,
        body
      )
      .then((res) => res.data),

  // "None of these" -- reject every pending candidate for a name group.
  dismissMatchNameGroup: (body: {
    datasetId: string;
    normalizedValue: string;
    reviewedBy: string;
    reviewNote?: string;
  }) =>
    apiClient
      .post<{ rejected: number }>(
        `${entitiesBaseURL}/matches/name-group/dismiss`,
        body
      )
      .then((res) => res.data),

  // Entity->entity merge review queue: one card per provisional stub, the
  // canonical entities it may duplicate nested. Populate with `dedupe-entities`.
  listMergeGroups: (params: {
    datasetId: string;
    status?: string;
    limit?: number;
    page?: number;
  }) =>
    apiClient
      .get<PaginatedEntityMergeGroupsResponse>(`${entitiesBaseURL}/merges`, {
        params: {
          dataset_id: params.datasetId,
          status: params.status ?? "pending",
          limit: params.limit ?? 25,
          page: params.page ?? 1,
        },
      })
      .then((res) => res.data),

  // Merge proposals filed against one entity (empty unless it's a provisional stub).
  getEntityMergeCandidates: (entityId: string) =>
    apiClient
      .get<EntityMatch[]>(`${entitiesBaseURL}/${entityId}/merge-candidates`)
      .then((res) => res.data),
};

export const mentionsService = {
  list: (params: {
    fileId?: string;
    datasetId?: string;
    entityId?: string;
    resolved?: boolean;
    mentionedType?: string;
    selectorType?: string;
    normalizedValue?: string;
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

  /** The review queue, one row per distinct unresolved name. */
  listUnresolvedNames: (params: {
    datasetId: string;
    q?: string;
    limit?: number;
    page?: number;
  }) =>
    apiClient
      .get<PaginatedUnresolvedNamesResponse>(
        `${mentionsBaseURL}/unresolved-names`,
        {
          params: { limit: 25, page: 1, ...params },
        }
      )
      .then((res) => res.data),

  resolveNameGroup: (payload: ResolveNameGroupPayload) =>
    apiClient
      .post<{
        entityId: string;
        mentionsAttached: number;
        hasSelectorEdges: number;
      }>(`${mentionsBaseURL}/resolve-names`, payload)
      .then((res) => res.data),

  dismissNameGroup: (payload: { datasetId: string; normalizedValue: string }) =>
    apiClient
      .post<{ deleted: number }>(`${mentionsBaseURL}/dismiss-names`, payload)
      .then((res) => res.data),
};
