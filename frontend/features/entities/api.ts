import { apiClient, humanErrorMessage } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types/common";
import { isAxiosError } from "axios";
import { toast } from "sonner";
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
  MentionResolution,
  MentionResolvePayload,
  MentionUpdatePayload,
  NameGroupKey,
  Ontology,
  PaginatedEntitiesResponse,
  PaginatedEntityMatchesResponse,
  PaginatedEntityMatchGroupsResponse,
  PaginatedMentionsResponse,
  PaginatedRelatedEntitiesResponse,
  PaginatedRelationshipsResponse,
  PaginatedUnresolvedNamesResponse,
  EntityType,
  RelatedEntitySort,
  RelationshipSuggestion,
  RelationshipType,
  ResolveNameGroupPayload,
  ResolveNameGroupsPayload,
  OrganizationStructure,
  ResolvedName,
  SelectorEvidence,
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
    datasetIds: string[];
    q?: string;
    selector?: string;
    limit?: number;
  }) =>
    apiClient
      .get<EntitySearchResult[]>(`${entitiesBaseURL}/search`, {
        params: {
          datasetIds: opts.datasetIds,
          q: opts.q,
          selector: opts.selector,
          limit: opts.limit ?? 8,
        },
      })
      .then((res) => res.data),

  getById: (id: string) =>
    apiClient.get<Entity>(`${entitiesBaseURL}/${id}`).then((res) => res.data),

  // Pending relationship suggestions with this entity at either end (family from patronymics, …).
  listRelationshipSuggestions: (entityId: string) =>
    apiClient
      .get<
        PaginatedResponse<RelationshipSuggestion>
      >(`${entitiesBaseURL}/relationship-candidates`, { params: { entityId, status: "pending", limit: 50 } })
      .then((res) => res.data),

  // Accept (becomes a real edge) or reject; the reviewer comes from the session.
  resolveRelationshipSuggestion: (
    id: string,
    status: "confirmed" | "rejected"
  ) =>
    apiClient
      .post(`${entitiesBaseURL}/relationship-candidates/${id}/resolve`, {
        status,
      })
      .then((res) => res.data),

  // A 404 can mean "no knowledge-graph node for this id yet" (e.g. a person page opened
  // before its bridge entity exists), so callers decide; other failures surface as usual.
  getProfile: (id: string) =>
    apiClient
      .get<EntityProfile>(`${entitiesBaseURL}/${id}/profile`, {
        expectNotFound: true,
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
  getBreakdown: (datasetIds: string[]) =>
    apiClient
      .get<EntityBreakdown>(`${entitiesBaseURL}/breakdown`, {
        params: { datasetIds },
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

  /** Names resolved to an entity, most mentions first, each flagged if it's a curated alias. */
  getStructure: (id: string) =>
    apiClient
      .get<OrganizationStructure>(`${entitiesBaseURL}/${id}/structure`)
      .then((res) => res.data),

  getNames: (id: string) =>
    apiClient
      .get<ResolvedName[]>(`${entitiesBaseURL}/${id}/names`)
      .then((res) => res.data),

  /** Header usage + current owners of candidate selectors -- the evidence for a proposed link. */
  getSelectorEvidence: (id: string, selectorIds: string[]) =>
    apiClient
      .get<
        SelectorEvidence[]
      >(`${entitiesBaseURL}/${id}/selector-evidence`, { params: { ids: selectorIds } })
      .then((res) => res.data),

  /** Manual has_selector edge to an existing selector node (the one its mentions point at). */
  linkSelector: (id: string, selectorId: string) =>
    apiClient
      .post(`${entitiesBaseURL}/${id}/selectors/${selectorId}`)
      .then((res) => res.data),

  // Remove the has_selector edge; the selector node itself is left intact.
  detachSelector: (
    id: string,
    selectorId: string,
    opts?: { ignoreMissing?: boolean }
  ) =>
    apiClient
      .delete(`${entitiesBaseURL}/${id}/selectors/${selectorId}`, {
        suppressErrorToast: opts?.ignoreMissing,
      })
      .then((res) => res.data)
      // `ignoreMissing`: an edge that's already gone is the outcome we wanted, not an error.
      .catch((error) => {
        if (!opts?.ignoreMissing || !isAxiosError(error)) throw error;
        if (error.response?.status === 404) return null;
        toast.error(humanErrorMessage(error));
        throw error;
      }),

  /** `discardMentions` deletes its mentions too ("not an entity"); otherwise they go back to Review unresolved. */
  delete: (id: string, opts?: { discardMentions?: boolean }) =>
    apiClient
      .delete<{
        deleted: boolean;
        mentionsDeleted: number;
      }>(`${entitiesBaseURL}/${id}`, {
        params: { discardMentions: opts?.discardMentions },
      })
      .then((res) => res.data),

  /** Keep a provisional entity as a new canonical one (a person gets its own person page). */
  promote: (id: string) =>
    apiClient
      .post<Entity>(`${entitiesBaseURL}/${id}/promote`)
      .then((res) => res.data),

  /** Bulk Verify -- keep each auto-created entity as a real one. */
  promoteBatch: (entityIds: string[]) =>
    apiClient
      .post<{
        promoted: number;
      }>(`${entitiesBaseURL}/promote-batch`, { entityIds })
      .then((res) => res.data),

  /** Person / organization / location for auto-created entities; their name mentions follow, known places merge in. */
  retype: (entityIds: string[], entityType: EntityType) =>
    apiClient
      .post<{
        retyped: number;
        mentions: number;
        edgesRemoved: number;
        placesMatched: number;
      }>(`${entitiesBaseURL}/retype`, {
        entityIds,
        entityType,
      })
      .then((res) => res.data),

  /** Fold auto-created duplicates into `id`; their names become its aliases. */
  merge: (id: string, sourceIds: string[]) =>
    apiClient
      .post<{ merged: number }>(`${entitiesBaseURL}/${id}/merge`, { sourceIds })
      .then((res) => res.data),

  /** Send a resolved name group back to the Resolve queue (aliases untouched). */
  unresolveName: (id: string, normalizedValue: string) =>
    apiClient
      .post<{
        detached: number;
      }>(`${entitiesBaseURL}/${id}/names/unresolve`, { normalizedValue })
      .then((res) => res.data),

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
          fileId: params?.fileId,
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
            relationshipType: params?.relationshipType,
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
      .get<PaginatedRelatedEntitiesResponse>(
        `${entitiesBaseURL}/${id}/related`,
        {
          params: {
            direction: params?.direction ?? "both",
            relationshipType: params?.relationshipType,
            entityType: params?.entityType,
            sort: params?.sort ?? "weight",
            limit: params?.limit ?? 25,
            page: params?.page ?? 1,
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
      minWeight?: number;
    }
  ) =>
    apiClient
      .get<GraphResponse>(`${entitiesBaseURL}/${id}/graph`, {
        // canvas seeds are remembered ids; a deleted entity just drops off the graph
        expectNotFound: true,
        params: {
          depth: params?.depth ?? 2,
          direction: params?.direction ?? "both",
          types: params?.types?.length ? params.types.join(",") : undefined,
          limit: params?.limit ?? 500,
          minWeight: params?.minWeight ?? 0,
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
    datasetIds?: string[];
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
    review: { status: string; reviewNote?: string }
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
    datasetIds: string[];
    entityId?: string;
    status?: string;
    minSimilarity?: number;
    includeProvisionalEntities?: boolean;
    sortBy?: "similarityScore" | "dateCreated";
    limit?: number;
    page?: number;
  }) =>
    apiClient
      .get<PaginatedEntityMatchGroupsResponse>(
        `${entitiesBaseURL}/matches/groups`,
        {
          params: {
            datasetIds: params.datasetIds,
            entityId: params.entityId,
            status: params.status ?? "pending",
            minSimilarity: params.minSimilarity,
            includeProvisionalEntities: params.includeProvisionalEntities,
            sortBy: params.sortBy ?? "similarityScore",
            limit: params.limit ?? 25,
            page: params.page ?? 1,
          },
        }
      )
      .then((res) => res.data),

  // Confirm / reject many candidates in one transaction (the bulk-annotation path).
  resolveMatchesBatch: (body: { decisions: EntityMatchBatchItem[] }) =>
    apiClient
      .post<{
        confirmed: number;
        rejected: number;
        notFound: number;
      }>(`${entitiesBaseURL}/matches/resolve-batch`, body)
      .then((res) => res.data),

  // "None of these" -- reject every pending candidate for a name group.
  dismissMatchNameGroup: (body: {
    datasetId: string;
    normalizedValue: string;
    reviewNote?: string;
  }) =>
    apiClient
      .post<{
        rejected: number;
      }>(`${entitiesBaseURL}/matches/name-group/dismiss`, body)
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

  getResolution: (id: string) =>
    apiClient
      .get<MentionResolution>(`${mentionsBaseURL}/${id}/resolution`, {
        suppressErrorToast: true,
      })
      .then((res) => res.data),

  resolve: (id: string, payload: MentionResolvePayload) =>
    apiClient
      .post<Mention>(`${mentionsBaseURL}/${id}/resolve`, payload)
      .then((res) => res.data),

  /** The review queue, one row per distinct unresolved name. */
  listUnresolvedNames: (params: {
    datasetIds: string[];
    q?: string;
    /** true: only names with a suggested resolution; false: only names needing a new entity */
    hasResolution?: boolean;
    /** only names with a pending resolution to this entity */
    entityId?: string;
    /** count only mentions in files carrying none of these source tags */
    excludeSourceTags?: string[];
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

  resolveNameGroups: (payload: ResolveNameGroupsPayload) =>
    apiClient
      .post<{
        entityIds: string[];
        mentionsAttached: number;
      }>(`${mentionsBaseURL}/resolve-names/batch`, payload)
      .then((res) => res.data),

  dismissNameGroups: (groups: NameGroupKey[]) =>
    apiClient
      .post<{ deleted: number }>(`${mentionsBaseURL}/dismiss-names/batch`, {
        groups,
      })
      .then((res) => res.data),
};
