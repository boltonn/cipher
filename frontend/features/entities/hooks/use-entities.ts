"use client";

import { entitiesService, mentionsService } from "@/features/entities/api";
import type {
  EntityCreatePayload,
  EntitySearchParameters,
  EntityType,
  EntityUpdatePayload,
  MentionProvenance,
  PaginatedRelatedEntitiesResponse,
  RelatedEntity,
  RelatedEntitySort,
  RelationshipType,
  SelectorEvidence,
  SelectorLinkPayload,
  SelectorMention,
  TraversalDirection,
} from "@/features/entities/types";
import {
  type InfiniteData,
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

const SELECTOR_MENTIONS_PAGE_SIZE = 25;

export function useEntityList(params: EntitySearchParameters, enabled = true) {
  return useQuery({
    queryKey: ["entities", "list", params],
    queryFn: () => entitiesService.list(params),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useEntitySearch(
  opts: { datasetIds: string[]; q?: string; selector?: string; limit?: number },
  enabled = true
) {
  return useQuery({
    queryKey: ["entities", "search", opts],
    queryFn: () => entitiesService.search(opts),
    enabled:
      enabled && opts.datasetIds.length > 0 && !!(opts.q || opts.selector),
    staleTime: 15_000,
    // Keep the previous matches visible while the next query loads so the
    // dropdown doesn't flash "no matches" between keystrokes.
    placeholderData: keepPreviousData,
  });
}

export function useEntity(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entities", entityId],
    queryFn: () => entitiesService.getById(entityId as string),
    enabled: !!entityId,
    staleTime: 30_000,
  });
}

export function useEntityProfile(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entities", entityId, "profile"],
    queryFn: () => entitiesService.getProfile(entityId as string),
    enabled: !!entityId,
    staleTime: 15_000,
    // A 404 (e.g. a person with no knowledge-graph node yet) is deterministic --
    // don't hammer it, let callers fall back.
    retry: false,
  });
}

export function useEntityGraph(
  entityId: string | undefined,
  params: {
    depth?: number;
    direction?: TraversalDirection;
    types?: RelationshipType[];
    minWeight?: number;
  }
) {
  return useQuery({
    queryKey: ["entities", entityId, "graph", params],
    queryFn: () => entitiesService.getGraph(entityId as string, params),
    enabled: !!entityId,
    staleTime: 15_000,
  });
}

export function useEntityMentions(
  entityId: string | undefined,
  fileId?: string
) {
  return useQuery({
    queryKey: ["entities", entityId, "mentions", fileId ?? null],
    queryFn: () =>
      entitiesService.getMentions(entityId as string, { fileId, limit: 200 }),
    enabled: !!entityId,
  });
}

const MENTIONS_PAGE_SIZE = 40;

/** Mentions of an entity, paged, optionally one evidence class. Feeds the dossier "Files" list. */
export function useEntityMentionsInfinite(
  entityId: string | undefined,
  opts?: { fileId?: string; provenance?: MentionProvenance }
) {
  const { fileId, provenance } = opts ?? {};
  return useInfiniteQuery({
    queryKey: [
      "entities",
      entityId,
      "mentions-infinite",
      fileId ?? null,
      provenance ?? null,
    ],
    enabled: !!entityId,
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      entitiesService.getMentions(entityId as string, {
        fileId,
        provenance,
        limit: MENTIONS_PAGE_SIZE,
        page: pageParam,
      }),
    getNextPageParam: (last) =>
      last.page * last.limit < last.total ? last.page + 1 : undefined,
  });
}

export function useEntityRelationships(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entities", entityId, "relationships"],
    queryFn: () => entitiesService.getRelationships(entityId as string),
    enabled: !!entityId,
  });
}

const RELATED_PAGE_SIZE = 25;

/** Pending relationship suggestions naming this entity, at either end. */
export function useRelationshipSuggestions(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entities", entityId, "relationship-suggestions"],
    queryFn: () =>
      entitiesService.listRelationshipSuggestions(entityId as string),
    enabled: !!entityId,
  });
}

export function useResolveRelationshipSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      status: "confirmed" | "rejected";
    }) => entitiesService.resolveRelationshipSuggestion(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["entities"] }),
  });
}

/** Paginated neighbours of an entity with sort/filter controls. */
export function useEntityRelatedInfinite(
  entityId: string | undefined,
  opts: {
    sort?: RelatedEntitySort;
    direction?: TraversalDirection;
    relationshipType?: RelationshipType;
    entityType?: EntityType;
    pageSize?: number;
  } = {}
) {
  const { pageSize = RELATED_PAGE_SIZE, ...filters } = opts;
  return useInfiniteQuery({
    queryKey: ["entities", entityId, "related", filters, pageSize],
    enabled: !!entityId,
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      entitiesService.getRelated(entityId as string, {
        ...filters,
        limit: pageSize,
        page: pageParam,
      }),
    getNextPageParam: (last) =>
      last.page * last.limit < last.total ? last.page + 1 : undefined,
  });
}

export function useCreateEntity(onSuccess?: (id: string) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EntityCreatePayload) =>
      entitiesService.create(payload),
    onSuccess: (entity) => {
      qc.invalidateQueries({ queryKey: ["entities"] });
      onSuccess?.(entity.id);
    },
  });
}

export function useUpdateEntity(entityId: string, onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EntityUpdatePayload) =>
      entitiesService.update(entityId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["entities"] });
      onSuccess?.();
    },
  });
}

export function useUpdateEntityDetail(
  entityId: string,
  onSuccess?: () => void
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (detail: Record<string, unknown>) =>
      entitiesService.updateDetail(entityId, detail),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["entities", entityId] });
      onSuccess?.();
    },
  });
}

/** Invalidate every cached view of one entity (profile, graph, relationships, detail). */
function invalidateEntity(
  qc: ReturnType<typeof useQueryClient>,
  entityId: string
) {
  qc.invalidateQueries({ queryKey: ["entities", entityId] });
}

export function useAttachSelector(
  entityId: string,
  onSuccess?: (result: SelectorMention) => void
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SelectorLinkPayload) =>
      entitiesService.attachSelector(entityId, payload),
    onSuccess: (result) => {
      invalidateEntity(qc, entityId);
      toast.success(
        result.mentionCount
          ? `Selector added · ${result.mentionCount} matching mention${result.mentionCount === 1 ? "" : "s"} found`
          : "Selector added"
      );
      onSuccess?.(result);
    },
  });
}

/** ISO-3166-1 alpha-2 phone regions the backend normalizer accepts. Cached for the session. */
export function useSelectorRegions() {
  return useQuery({
    queryKey: ["entities", "selector-regions"],
    queryFn: () => entitiesService.listSelectorRegions(),
    staleTime: Infinity,
  });
}

/** The entity-layer registry (relationship types + endpoint rules + roles). Cached for the session. */
export function useOntology() {
  return useQuery({
    queryKey: ["entities", "ontology"],
    queryFn: () => entitiesService.getOntology(),
    staleTime: Infinity,
  });
}

/** Entity / selector counts for these datasets -- the dataset-view breakdown chart. */
export function useEntityBreakdown(datasetIds: string[]) {
  return useQuery({
    queryKey: ["entities", "breakdown", datasetIds],
    queryFn: () => entitiesService.getBreakdown(datasetIds),
    enabled: datasetIds.length > 0,
    staleTime: 60_000,
  });
}

/**
 * Mentions whose normalized value equals a selector's -- across every dataset and
 * regardless of resolution -- so a linked selector surfaces where it already appears.
 */
export function useSelectorMentions(
  normalizedValue: string | null | undefined,
  selectorType?: string | null
) {
  return useInfiniteQuery({
    queryKey: ["mentions", "by-value", normalizedValue, selectorType ?? null],
    enabled: !!normalizedValue,
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      mentionsService.list({
        normalizedValue: normalizedValue as string,
        selectorType: selectorType ?? undefined,
        limit: SELECTOR_MENTIONS_PAGE_SIZE,
        page: pageParam,
      }),
    getNextPageParam: (last) =>
      last.page * last.limit < last.total ? last.page + 1 : undefined,
  });
}

/** An organization's parent chain, sub-units, locations and people. */
export function useOrganizationStructure(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entities", entityId, "structure"],
    queryFn: () => entitiesService.getStructure(entityId as string),
    enabled: !!entityId,
  });
}

/** Names resolved to an entity (resolved name groups), flagged when they're curated aliases. */
export function useEntityNames(entityId: string) {
  return useQuery({
    queryKey: ["entities", entityId, "names"],
    queryFn: () => entitiesService.getNames(entityId),
  });
}

/** Evidence for selectors proposed as belonging to `entityId` (usage, names, current owners). */
export function useSelectorEvidence(entityId: string, selectorIds: string[]) {
  return useQuery({
    queryKey: ["entities", entityId, "selector-evidence", selectorIds],
    queryFn: () => entitiesService.getSelectorEvidence(entityId, selectorIds),
    enabled: selectorIds.length > 0,
    // Resolving a row shrinks `selectorIds`; keep the rest on screen instead of blanking the panel.
    placeholderData: keepPreviousData,
  });
}

type RelatedPages = InfiniteData<PaginatedRelatedEntitiesResponse>;

/**
 * Link an existing selector node to `entityId` (manual edge). `moveFrom` detaches it from
 * those owners -- for fixing an address wrongly linked to someone else. Optimistic: the
 * address joins this entity's selector list at once and `onApply` runs; a failure rolls
 * both back (`onRevert`).
 */
export function useLinkSelector(
  entityId: string,
  {
    onApply,
    onRevert,
  }: {
    onApply?: (selectorId: string) => void;
    onRevert?: (selectorId: string) => void;
  } = {}
) {
  const qc = useQueryClient();
  const selectorPages = {
    queryKey: ["entities", entityId, "related"],
    predicate: isSelectorListQuery,
  };
  return useMutation({
    mutationFn: async ({
      selector,
      moveFrom = [],
    }: {
      selector: SelectorEvidence;
      moveFrom?: string[];
    }) => {
      // Link before detaching so a failure never leaves the address with no owner.
      await entitiesService.linkSelector(entityId, selector.entityId);
      await Promise.all(
        moveFrom.map((ownerId) =>
          entitiesService.detachSelector(ownerId, selector.entityId, {
            ignoreMissing: true,
          })
        )
      );
    },
    onMutate: async ({ selector }) => {
      await qc.cancelQueries(selectorPages);
      const previous = qc.getQueriesData<RelatedPages>(selectorPages);
      const row: RelatedEntity = {
        relationshipType: "hasSelector",
        direction: "out",
        attributes: {},
        entity: {
          id: selector.entityId,
          entityType: "selector",
          displayName: selector.displayName,
          isVerified: false,
        },
        mentionCount: selector.emailCount,
        selectorType: selector.displayName.includes("@") ? "email" : null,
        normalizedValue: selector.displayName,
      };
      qc.setQueriesData<RelatedPages>(selectorPages, (data) => {
        const [first, ...rest] = data?.pages ?? [];
        if (
          !data ||
          !first ||
          first.data.some((r) => r.entity.id === row.entity.id)
        )
          return data;
        return {
          ...data,
          pages: [
            { ...first, data: [row, ...first.data], total: first.total + 1 },
            ...rest,
          ],
        };
      });
      onApply?.(selector.entityId);
      return { previous };
    },
    onError: (_error, { selector }, context) => {
      for (const [key, data] of context?.previous ?? [])
        qc.setQueryData(key, data);
      onRevert?.(selector.entityId);
    },
    onSuccess: (_result, { moveFrom = [] }) => {
      toast.success(moveFrom.length ? "Address moved" : "Address added");
    },
    onSettled: (_result, _error, { moveFrom = [] }) => {
      invalidateEntity(qc, entityId);
      for (const ownerId of moveFrom) invalidateEntity(qc, ownerId);
    },
  });
}

function isSelectorListQuery(query: { queryKey: readonly unknown[] }) {
  return (
    (query.queryKey[3] as { entityType?: EntityType } | undefined)
      ?.entityType === "selector"
  );
}

export function useDetachSelector(entityId: string, onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (selectorId: string) =>
      entitiesService.detachSelector(entityId, selectorId),
    onSuccess: () => {
      invalidateEntity(qc, entityId);
      onSuccess?.();
    },
  });
}

/**
 * Delete an entity node; relationships/matches/comments on it go too. Its mentions
 * unresolve (back to Review), or with `discardMentions` are deleted ("not an entity").
 */
export function useDeleteEntity(onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      entityId,
      discardMentions,
    }: {
      entityId: string;
      discardMentions?: boolean;
    }) => entitiesService.delete(entityId, { discardMentions }),
    onSuccess: (_result, { entityId }) => {
      // The dossier page for this entity is often still mounted here (the route
      // change hasn't unmounted it yet) -- excluding its id from the broad
      // invalidation stops that live observer from refetching a 404 for the id
      // we just removeQueries'd.
      qc.removeQueries({ queryKey: ["entities", entityId] });
      qc.invalidateQueries({
        queryKey: ["entities"],
        predicate: (q) => q.queryKey[1] !== entityId,
      });
      qc.invalidateQueries({ queryKey: ["comments"] });
      qc.invalidateQueries({ queryKey: ["mentions"] });
      qc.invalidateQueries({ queryKey: ["entity-matches"] });
      qc.invalidateQueries({ queryKey: ["entity-merges"] });
      onSuccess?.();
    },
  });
}

export function useCreateRelationship(
  srcEntityId: string,
  onSuccess?: () => void
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      datasetId?: string;
      dstEntityId: string;
      relationshipType: RelationshipType;
      attributes?: Record<string, unknown>;
    }) => entitiesService.createRelationship(srcEntityId, payload),
    onSuccess: () => {
      invalidateEntity(qc, srcEntityId);
      onSuccess?.();
    },
  });
}
