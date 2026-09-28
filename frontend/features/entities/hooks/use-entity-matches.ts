"use client";

import { entitiesService } from "@/features/entities/api";
import type {
  EntityMatchBatchItem,
  EntityMatchStatus,
} from "@/features/entities/types";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

type GroupParams = {
  datasetId: string | undefined;
  status: EntityMatchStatus;
  sortBy: "similarity_score" | "date_created";
  minSimilarity?: number;
  page: number;
};

/** The grouped resolution review queue -- one card per unresolved name. */
export function useMatchGroups({
  datasetId,
  status,
  sortBy,
  minSimilarity,
  page,
}: GroupParams) {
  return useQuery({
    queryKey: [
      "entity-matches",
      "groups",
      datasetId,
      status,
      sortBy,
      minSimilarity ?? null,
      page,
    ],
    queryFn: () =>
      entitiesService.listMatchGroups({
        datasetId: datasetId as string,
        status,
        sortBy,
        minSimilarity,
        page,
      }),
    enabled: !!datasetId,
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
      reviewedBy: string;
      reviewNote?: string;
    }) =>
      entitiesService.resolveMatch(vars.matchId, {
        status: vars.status,
        reviewedBy: vars.reviewedBy,
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
    mutationFn: (vars: {
      reviewedBy: string;
      decisions: EntityMatchBatchItem[];
    }) => entitiesService.resolveMatchesBatch(vars),
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
      reviewedBy: string;
      reviewNote?: string;
    }) => entitiesService.dismissMatchNameGroup(vars),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}
