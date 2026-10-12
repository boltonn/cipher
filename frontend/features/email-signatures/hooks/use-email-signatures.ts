import { emailSignaturesService } from "@/features/email-signatures/api";
import type {
  EmailSignatureSearchParameters,
  MentionRelationshipDraft,
  MentionRelationshipUpdate,
} from "@/features/email-signatures/types";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

/** The review queue: emails whose email signature was read. */
export function useEmailSignatures(params: EmailSignatureSearchParameters) {
  return useQuery({
    queryKey: ["email-signatures", "list", params],
    queryFn: () => emailSignaturesService.list(params),
    placeholderData: keepPreviousData,
  });
}

/** Where an email's email signature is; no retry -- most emails have none. */
export function useEmailSignature(fileId: string | undefined) {
  return useQuery({
    queryKey: ["email-signatures", "detail", fileId],
    queryFn: () => emailSignaturesService.get(fileId as string),
    enabled: !!fileId,
    retry: false,
  });
}

/** Keyed under `mentions` so relabelling / resolving a mention refreshes its relationships too. */
export function useMentionRelationships(fileId: string | undefined) {
  return useQuery({
    queryKey: ["mentions", "relationships", fileId],
    queryFn: () => emailSignaturesService.listRelationships(fileId as string),
    enabled: !!fileId,
  });
}

function useRelationshipInvalidation() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["mentions", "relationships"] });
    qc.invalidateQueries({ queryKey: ["email-signatures", "list"] });
    qc.invalidateQueries({ queryKey: ["entities"] });
    qc.invalidateQueries({ queryKey: ["name-suggestions"] });
  };
}

const onError = (error: unknown) =>
  toast.error(
    error instanceof Error ? error.message : "Couldn't save that change"
  );

export function useCreateRelationship(onSuccess?: () => void) {
  const invalidate = useRelationshipInvalidation();
  return useMutation({
    mutationFn: (draft: MentionRelationshipDraft) =>
      emailSignaturesService.createRelationship(draft),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
    onError,
  });
}

export function useUpdateRelationship(onSuccess?: () => void) {
  const invalidate = useRelationshipInvalidation();
  return useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: MentionRelationshipUpdate;
    }) => emailSignaturesService.updateRelationship(id, patch),
    onSuccess: () => {
      invalidate();
      onSuccess?.();
    },
    onError,
  });
}

export function useReviewRelationship() {
  const invalidate = useRelationshipInvalidation();
  return useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: string;
      action: "accept" | "reject" | "reopen";
    }) => emailSignaturesService.review(id, action),
    onSuccess: invalidate,
    onError,
  });
}

export function useDeleteRelationship() {
  const invalidate = useRelationshipInvalidation();
  return useMutation({
    mutationFn: (id: string) => emailSignaturesService.deleteRelationship(id),
    onSuccess: invalidate,
    onError,
  });
}
