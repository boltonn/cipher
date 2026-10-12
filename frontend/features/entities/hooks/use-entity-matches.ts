"use client";

import { entitiesService } from "@/features/entities/api";
import type {
  EntityMatchBatchItem,
  EntityMatchStatus,
  EntityType,
} from "@/features/entities/types";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

type GroupParams = {
  datasetIds: string[];
  entityId?: string;
  status: EntityMatchStatus;
  sortBy: "similarityScore" | "dateCreated";
  minSimilarity?: number;
  includeProvisionalEntities: boolean;
  page: number;
  limit?: number;
  enabled?: boolean;
};

/** The grouped resolution review queue -- one card per unresolved name. */
export function useMatchGroups({
  datasetIds,
  entityId,
  status,
  sortBy,
  minSimilarity,
  includeProvisionalEntities,
  page,
  limit,
  enabled = true,
}: GroupParams) {
  return useQuery({
    queryKey: [
      "entity-matches",
      "groups",
      datasetIds,
      entityId ?? null,
      status,
      sortBy,
      minSimilarity ?? null,
      includeProvisionalEntities,
      page,
      limit ?? null,
    ],
    queryFn: () =>
      entitiesService.listMatchGroups({
        datasetIds,
        entityId,
        status,
        sortBy,
        minSimilarity,
        includeProvisionalEntities,
        page,
        limit,
      }),
    enabled: datasetIds.length > 0 && enabled,
    placeholderData: keepPreviousData,
  });
}

function useMatchInvalidation() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["entity-matches"] });
    qc.invalidateQueries({ queryKey: ["entity-merges"] });
    qc.invalidateQueries({ queryKey: ["mentions"] });
    qc.invalidateQueries({ queryKey: ["entities"] });
    qc.invalidateQueries({ queryKey: ["persons"] });
  };
}

/** Merge proposals filed against one entity -- for the "Possible duplicates" panel. */
export function useEntityMergeCandidates(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity-merges", "for-entity", entityId],
    queryFn: () => entitiesService.getEntityMergeCandidates(entityId as string),
    enabled: !!entityId,
  });
}

export function useResolveMatch(onSuccess?: () => void) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: (vars: {
      matchId: string;
      status: EntityMatchStatus;
      reviewNote?: string;
    }) =>
      entitiesService.resolveMatch(vars.matchId, {
        status: vars.status,
        reviewNote: vars.reviewNote,
      }),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

export function useResolveMatchesBatch(onSuccess?: () => void) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: (vars: { decisions: EntityMatchBatchItem[] }) =>
      entitiesService.resolveMatchesBatch(vars),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

export function useDismissMatchNameGroup(onSuccess?: () => void) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: (vars: {
      datasetId: string;
      normalizedValue: string;
      reviewNote?: string;
    }) => entitiesService.dismissMatchNameGroup(vars),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

/** Keep a provisional entity as a new canonical one; rejects its pending merge proposals. */
export function usePromoteEntity(onSuccess?: () => void) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: (entityId: string) => entitiesService.promote(entityId),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

export function usePromoteEntities(onSuccess?: () => void) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: (entityIds: string[]) =>
      entitiesService.promoteBatch(entityIds),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

export function useMergeEntities(onSuccess?: () => void) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: ({
      targetId,
      sourceIds,
    }: {
      targetId: string;
      sourceIds: string[];
    }) => entitiesService.merge(targetId, sourceIds),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

/**
 * Settle a same-name type disagreement: the auto-created `source` takes `entityType`
 * (retyped if needed) and folds into `targetId`.
 */
export function usePickEntityType(onSuccess?: () => void) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: async ({
      targetId,
      source,
      entityType,
    }: {
      targetId: string;
      source: { id: string; entityType: EntityType };
      entityType: EntityType;
    }) => {
      if (source.entityType !== entityType)
        await entitiesService.retype([source.id], entityType);
      return entitiesService.merge(targetId, [source.id]);
    },
    onSettled: invalidate,
    onSuccess: () => onSuccess?.(),
  });
}

export function useUnresolveName(entityId: string) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: (normalizedValue: string) =>
      entitiesService.unresolveName(entityId, normalizedValue),
    onSuccess: invalidate,
  });
}

export function useRetypeEntities(onSuccess?: () => void) {
  const invalidate = useMatchInvalidation();
  return useMutation({
    mutationFn: ({
      entityIds,
      entityType,
    }: {
      entityIds: string[];
      entityType: EntityType;
    }) => entitiesService.retype(entityIds, entityType),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}
