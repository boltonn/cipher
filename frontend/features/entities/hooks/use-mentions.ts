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

/** The review queue as distinct names -- one row per name, not per mention. */
export function useUnresolvedNameGroups(
  datasetId: string | undefined,
  q: string,
  page: number
) {
  return useQuery({
    queryKey: ["mentions", "unresolved-names", datasetId, q, page],
    queryFn: () =>
      mentionsService.listUnresolvedNames({
        datasetId: datasetId as string,
        q: q || undefined,
        page,
      }),
    enabled: !!datasetId,
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
    qc.invalidateQueries({ queryKey: ["mentions"] });
    qc.invalidateQueries({ queryKey: ["entities"] });
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
