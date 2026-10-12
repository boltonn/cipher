import { apiClient } from "@/lib/api-client";
import type {
  EmailSignature,
  EmailSignatureSearchParameters,
  MentionRelationship,
  MentionRelationshipDraft,
  MentionRelationshipUpdate,
  PaginatedEmailSignatures,
} from "@/features/email-signatures/types";

const relationshipsURL = "/mention-relationships";

export const emailSignaturesService = {
  list: (params: EmailSignatureSearchParameters) =>
    apiClient
      .get<PaginatedEmailSignatures>("/email-signatures", { params })
      .then((res) => res.data),

  // Most files have no email signature: a 404 is an answer the caller handles, not a missing page.
  get: (fileId: string) =>
    apiClient
      .get<EmailSignature>(`/email-signatures/${fileId}`, {
        expectNotFound: true,
      })
      .then((res) => res.data),

  listRelationships: (fileId: string) =>
    apiClient
      .get<MentionRelationship[]>(relationshipsURL, { params: { fileId } })
      .then((res) => res.data),

  createRelationship: (draft: MentionRelationshipDraft) =>
    apiClient
      .post<MentionRelationship>(relationshipsURL, draft)
      .then((res) => res.data),

  updateRelationship: (id: string, patch: MentionRelationshipUpdate) =>
    apiClient
      .patch<MentionRelationship>(`${relationshipsURL}/${id}`, patch)
      .then((res) => res.data),

  review: (id: string, action: "accept" | "reject" | "reopen") =>
    apiClient
      .post<MentionRelationship>(`${relationshipsURL}/${id}/${action}`)
      .then((res) => res.data),

  deleteRelationship: (id: string) =>
    apiClient.delete(`${relationshipsURL}/${id}`).then((res) => res.data),
};
