import { FacePublic } from "@/features/faces/types";
import {
  PaginatedPersonsResponse,
  Person,
  PersonCreate,
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
  // Multipart form fields don't go through the JSON camelCase-alias layer,
  // so keys must match the backend's Form() parameter names (snake_case).
  createFromImage: (file: File, payload: PersonCreate & { faceIndex?: number }) => {
    const formData = new FormData();
    formData.append("file", file);
    if (payload.name) formData.append("name", payload.name);
    if (payload.sex) formData.append("sex", payload.sex);
    if (payload.dateOfBirth) formData.append("date_of_birth", payload.dateOfBirth);
    if (payload.notes) formData.append("notes", payload.notes);
    if (payload.tags?.length) formData.append("tags", payload.tags.join(","));
    if (payload.isVerified != null) formData.append("is_verified", String(payload.isVerified));
    if (payload.faceIndex != null) formData.append("face_index", String(payload.faceIndex));
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

  // POST /persons/{id}/examples - add an additional reference face to an existing person
  addExample: (id: string, file: File, faceIndex: number) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("face_index", String(faceIndex));
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
