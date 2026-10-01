"use client";

import { mentionsService } from "@/features/entities/api";
import type {
  MentionCreatePayload,
  MentionResolvePayload,
  MentionUpdatePayload,
  ResolveNameGroupPayload,
} from "@/features/entities/types";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

/** All mentions anchored in one file's extracted text (feeds the highlight overlay). */
export function useFileMentions(fileId: string | undefined) {
  return useQuery({
    queryKey: ["mentions", "file", fileId],
    queryFn: () =>
      mentionsService.list({ fileId: fileId as string, limit: 500 }),
    enabled: !!fileId,
    staleTime: 15_000,
  });
}

/** The resolver's scored candidates for one mention's name group. */
export function useMentionResolution(mentionId: string | undefined) {
  return useQuery({
    queryKey: ["mentions", "resolution", mentionId],
    queryFn: () => mentionsService.getResolution(mentionId as string),
    enabled: !!mentionId,
  });
}

/** Entities other mentions of this value already resolve to, most mentions first -- "elsewhere this is …". */
export function useValueResolvedEntities(datasetId: string, normalizedValue: string | undefined) {
  return useQuery({
    queryKey: ["mentions", "value-entities", datasetId, normalizedValue],
    queryFn: () =>
      mentionsService.list({ datasetId, normalizedValue: normalizedValue as string, resolved: true, limit: 200 }),
    enabled: !!normalizedValue,
    select: (page) => {
      const counts = new Map<string, number>();
      for (const m of page.data) if (m.entityId) counts.set(m.entityId, (counts.get(m.entityId) ?? 0) + 1);
      return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([entityId, count]) => ({ entityId, count }));
    },
  });
}

/** Unresolved mentions in a dataset -- the review queue. */
export function useUnresolvedMentions(datasetId: string | undefined) {
  return useQuery({
    queryKey: ["mentions", "unresolved", datasetId],
    queryFn: () =>
      mentionsService.list({
        datasetId: datasetId as string,
        resolved: false,
        limit: 200,
      }),
    enabled: !!datasetId,
  });
}

/** The Resolve queue: one row per unresolved name group, with its suggested resolutions. */
export function useUnresolvedNameGroups(params: {
  datasetId: string | undefined;
  q?: string;
  hasResolution?: boolean;
  entityId?: string;
  page: number;
}) {
  return useQuery({
    queryKey: ["mentions", "unresolved-names", params],
    queryFn: () =>
      mentionsService.listUnresolvedNames({
        ...params,
        datasetId: params.datasetId as string,
        q: params.q || undefined,
      }),
    enabled: !!params.datasetId,
    placeholderData: keepPreviousData,
  });
}

export function useResolveNameGroup(onSuccess?: () => void) {
  const invalidate = useMentionInvalidation();
  return useMutation({
    mutationFn: (payload: ResolveNameGroupPayload) =>
      mentionsService.resolveNameGroup(payload),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

export function useDismissNameGroup(onSuccess?: () => void) {
  const invalidate = useMentionInvalidation();
  return useMutation({
    mutationFn: (vars: { datasetId: string; normalizedValue: string }) =>
      mentionsService.dismissNameGroup(vars),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

function useMentionInvalidation() {
  const qc = useQueryClient();
  return () => {
    // Resolution lookups only go stale: the open popover's mention may have just been deleted or replaced.
    qc.invalidateQueries({ queryKey: ["mentions"], predicate: (q) => q.queryKey[1] !== "resolution" });
    qc.invalidateQueries({ queryKey: ["mentions", "resolution"], refetchType: "none" });
    qc.invalidateQueries({ queryKey: ["entities"] });
    qc.invalidateQueries({ queryKey: ["search"] });
  };
}

export function useCreateMention(onSuccess?: () => void) {
  const invalidate = useMentionInvalidation();
  return useMutation({
    mutationFn: (payload: MentionCreatePayload) =>
      mentionsService.create(payload),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

export function useUpdateMention(onSuccess?: () => void) {
  const invalidate = useMentionInvalidation();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: MentionUpdatePayload;
    }) => mentionsService.update(id, payload),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

export function useResolveMention(onSuccess?: () => void) {
  const invalidate = useMentionInvalidation();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: MentionResolvePayload;
    }) => mentionsService.resolve(id, payload),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}

export function useDeleteMention(onSuccess?: () => void) {
  const invalidate = useMentionInvalidation();
  return useMutation({
    mutationFn: (id: string) => mentionsService.delete(id),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
  });
}
