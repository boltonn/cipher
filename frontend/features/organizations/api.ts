import { apiClient } from "@/lib/api-client";
import type {
  NameSuggestion,
  NameSuggestionChoice,
  OrganizationPeopleParameters,
  OrganizationSuggestion,
  OrganizationTree,
  PaginatedOrganizationPeople,
  RelationshipEvidence,
} from "@/features/organizations/types";

const baseURL = "/entities";

export const organizationsService = {
  getTree: (id: string) =>
    apiClient
      .get<OrganizationTree>(`${baseURL}/${id}/structure/tree`)
      .then((res) => res.data),

  listPeople: (id: string, params: OrganizationPeopleParameters) =>
    apiClient
      .get<PaginatedOrganizationPeople>(`${baseURL}/${id}/structure/people`, {
        params,
      })
      .then((res) => res.data),

  getSuggestions: (id: string) =>
    apiClient
      .get<OrganizationSuggestion[]>(`${baseURL}/${id}/structure/suggestions`)
      .then((res) => res.data),

  getEvidence: (candidateId: string) =>
    apiClient
      .get<
        RelationshipEvidence[]
      >(`${baseURL}/relationship-candidates/${candidateId}/evidence`)
      .then((res) => res.data),

  getNameSuggestions: (id: string) =>
    apiClient
      .get<NameSuggestion[]>(`${baseURL}/${id}/structure/name-suggestions`)
      .then((res) => res.data),

  getUnplacedNameSuggestions: () =>
    apiClient
      .get<NameSuggestion[]>(`${baseURL}/name-suggestions/unplaced`)
      .then((res) => res.data),

  getNameSuggestionEvidence: (ids: string[]) =>
    apiClient
      .get<
        RelationshipEvidence[]
      >(`${baseURL}/name-suggestions/evidence`, { params: { ids } })
      .then((res) => res.data),

  /** Settle both names (attach / create + confirm) and add the edge; the reviewer comes from the session. */
  acceptNameSuggestion: (
    suggestion: NameSuggestion,
    source: NameSuggestionChoice,
    target: NameSuggestionChoice
  ) =>
    apiClient
      .post(`${baseURL}/name-suggestions/accept`, {
        datasetId: suggestion.datasetId,
        relationshipType: suggestion.relationshipType,
        role: suggestion.role,
        mentionRelationshipIds: suggestion.mentionRelationshipIds,
        source,
        target,
      })
      .then((res) => res.data),

  dismissNameSuggestion: (mentionRelationshipIds: string[]) =>
    apiClient
      .post(`${baseURL}/name-suggestions/dismiss`, { mentionRelationshipIds })
      .then((res) => res.data),

  /** Accept (promote to a real edge) or reject a suggestion; the reviewer comes from the session. */
  resolveSuggestion: (candidateId: string, status: "confirmed" | "rejected") =>
    apiClient
      .post(`${baseURL}/relationship-candidates/${candidateId}/resolve`, {
        status,
      })
      .then((res) => res.data),
};
