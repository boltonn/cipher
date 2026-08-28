"use client";

import { entitiesService } from "@/features/entities/api";
import type {
  EntityCreatePayload,
  EntitySearchParameters,
  EntityUpdatePayload,
  RelationshipType,
  TraversalDirection,
} from "@/features/entities/types";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

export function useEntityList(params: EntitySearchParameters) {
  return useQuery({
    queryKey: ["entities", "list", params],
    queryFn: () => entitiesService.list(params),
    placeholderData: keepPreviousData,
  });
}

export function useEntitySearch(
  opts: { datasetId?: string; q?: string; selector?: string; limit?: number },
  enabled = true
) {
  return useQuery({
    queryKey: ["entities", "search", opts],
    queryFn: () =>
      entitiesService.search({ ...opts, datasetId: opts.datasetId as string }),
    enabled: enabled && !!opts.datasetId && !!(opts.q || opts.selector),
    staleTime: 15_000,
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

export function useEntityRelationships(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entities", entityId, "relationships"],
    queryFn: () => entitiesService.getRelationships(entityId as string),
    enabled: !!entityId,
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

export function useDeleteEntity(onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entityId: string) => entitiesService.delete(entityId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["entities"] });
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
      datasetId: string;
      dstEntityId: string;
      relationshipType: RelationshipType;
    }) => entitiesService.createRelationship(srcEntityId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["entities", srcEntityId] });
      onSuccess?.();
    },
  });
}
