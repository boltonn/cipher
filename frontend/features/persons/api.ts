import { FacePublic } from "@/features/faces/types";
import {
  PaginatedPersonsResponse,
  Person,
  PersonCreate,
  PersonMergeResult,
  PersonMergeSuggestion,
  PersonSearchParameters,
  PersonUpdate,
} from "@/features/persons/types";
import { apiClient } from "@/lib/api-client";

const personsBaseURL = "/persons";

export const personsService = {
  search: (params: PersonSearchParameters) =>
    apiClient
      .get<PaginatedPersonsResponse>(personsBaseURL, { params })
      .then((res) => res.data),

  getById: (id: string) =>
    apiClient.get<Person>(`${personsBaseURL}/${id}`).then((res) => res.data),

  create: (payload: PersonCreate) =>
    apiClient.post<Person>(personsBaseURL, payload).then((res) => res.data),

  // POST /persons/from-image - detect a face in an uploaded photo and create a person from it.
  //
  createFromImage: (file: File, payload: PersonCreate & { faceIndex?: number }) => {
    const formData = new FormData();
    formData.append("file", file);
    if (payload.name) formData.append("name", payload.name);
    if (payload.sex) formData.append("sex", payload.sex);
    if (payload.dateOfBirth) formData.append("dateOfBirth", payload.dateOfBirth);
    if (payload.notes) formData.append("notes", payload.notes);
    if (payload.tags?.length) formData.append("tags", payload.tags.join(","));
    if (payload.faceIndex != null) formData.append("faceIndex", String(payload.faceIndex));
    return apiClient
      .post<Person>(`${personsBaseURL}/from-image`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((res) => res.data);
  },

  // POST /persons/from-face - create a person directly from an already-detected
  // face (JSON body, so the usual camelCase aliasing applies -- no multipart gotcha)
  createFromFace: (faceId: string, payload: PersonCreate) =>
    apiClient
      .post<Person>(`${personsBaseURL}/from-face`, { ...payload, faceId })
      .then((res) => res.data),

  update: (id: string, payload: PersonUpdate) =>
    apiClient
      .patch<Person>(`${personsBaseURL}/${id}`, payload)
      .then((res) => res.data),

  // GET /persons/{id}/merge-candidates - other persons whose representative
  // faces look like this one's, ranked by similarity (merge shortlist).
  mergeCandidates: (id: string) =>
    apiClient
      .get<PersonMergeSuggestion[]>(`${personsBaseURL}/${id}/merge-candidates`)
      .then((res) => res.data),

  // POST /persons/{id}/merge - fold `sourceId` into this person, then delete it.
  // Faces, pending matches, event participations, comments, mentions and
  // relationship edges all move onto {id}; moved faces lose their exemplar flags.
  merge: (id: string, sourceId: string) =>
    apiClient
      .post<PersonMergeResult>(`${personsBaseURL}/${id}/merge`, { sourceId })
      .then((res) => res.data),

  // POST /persons/{id}/examples - add an additional reference face to an existing person
  addExample: (id: string, file: File, faceIndex: number) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("faceIndex", String(faceIndex));
    return apiClient
      .post(`${personsBaseURL}/${id}/examples`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((res) => res.data);
  },

  delete: (id: string) =>
    apiClient.delete<boolean>(`${personsBaseURL}/${id}`).then((res) => res.data),

  getRepresentativeFaces: (id: string) =>
    apiClient
      .get<FacePublic[]>(`${personsBaseURL}/${id}/representative-faces`)
      .then((res) => res.data),
};
