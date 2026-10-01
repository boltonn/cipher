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
  datasetId: string | undefined;
  entityId?: string;
  status: EntityMatchStatus;
  sortBy: "similarity_score" | "date_created";
  minSimilarity?: number;
  includeProvisionalEntities: boolean;
  page: number;
  limit?: number;
  enabled?: boolean;
};

/** The grouped resolution review queue -- one card per unresolved name. */
export function useMatchGroups({
  datasetId,
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
      datasetId,
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
        datasetId: datasetId as string,
        entityId,
        status,
        sortBy,
        minSimilarity,
        includeProvisionalEntities,
        page,
        limit,
      }),
    enabled: !!datasetId && enabled,
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

/** Entity->entity merge review queue (populate with `cipher dedupe-entities`). */
export function useMergeGroups({
  datasetId,
  status,
  page,
}: {
  datasetId: string | undefined;
  status: EntityMatchStatus;
  page: number;
}) {
  return useQuery({
    queryKey: ["entity-merges", "groups", datasetId, status, page],
    queryFn: () =>
      entitiesService.listMergeGroups({
        datasetId: datasetId as string,
        status,
        page,
      }),
    enabled: !!datasetId,
    placeholderData: keepPreviousData,
  });
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
