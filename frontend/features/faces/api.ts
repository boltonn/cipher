import {
  BaseFaceSearchParameters,
  DetectedFace,
  FaceAssignment,
  FaceMatch,
  FaceMatchSearchParameters,
  FaceMatchStatusType,
  FaceRepresentativeUpdate,
  FaceSimilaritySearchParameters,
  PaginatedFaceMatchesResponse,
  PaginatedFaceSimilarityResponse,
  PaginatedFacesResponse,
  FacePublic,
} from "@/features/faces/types";
import { apiClient, baseURL } from "@/lib/api-client";

const facesBaseURL = "/faces";

export const facesService = {
  // Get uri of the source image a face was detected in
  getFaceViewUrl: (id: string) => `${baseURL}${facesBaseURL}/${id}/view`,

  // Small cached crop of just the face -- use for grids/cards, not the full view
  getFaceThumbnailUrl: (id: string) => `${baseURL}${facesBaseURL}/${id}/thumbnail`,

  // POST /faces - filter/paginate
  search: (params: BaseFaceSearchParameters) =>
    apiClient
      .post<PaginatedFacesResponse>(facesBaseURL, params)
      .then((res) => res.data),

  // GET /faces/search/{id} - find faces similar to an existing face
  searchById: (id: string, params: FaceSimilaritySearchParameters) =>
    apiClient
      .get<PaginatedFaceSimilarityResponse>(`${facesBaseURL}/search/${id}`, { params })
      .then((res) => res.data),

  // POST /faces/search/image - find faces similar to an uploaded photo
  //
  // Multipart form fields don't go through the JSON camelCase-alias layer,
  // so keys must match the backend's Form() parameter names (snake_case)
  // directly rather than the camelCase param object keys.
  searchByUpload: (file: File, params: FaceSimilaritySearchParameters) => {
    const formData = new FormData();
    formData.append("file", file);
    if (params.page != null) formData.append("page", params.page.toString());
    if (params.limit != null) formData.append("limit", params.limit.toString());
    if (params.sortBy != null) formData.append("sort_by", params.sortBy);
    if (params.sortOrder != null) formData.append("sort_order", params.sortOrder);
    if (params.minSimilarity != null) formData.append("min_similarity", params.minSimilarity.toString());
    return apiClient
      .post<PaginatedFaceSimilarityResponse>(`${facesBaseURL}/search/image`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((res) => res.data);
  },

  // POST /faces/detect - detect all faces in an uploaded photo, no persistence
  detect: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient
      .post<DetectedFace[]>(`${facesBaseURL}/detect`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((res) => res.data);
  },

  // POST /faces/search/embedding - find faces similar to a chosen embedding
  // (e.g. one the caller picked from a multi-face /detect result)
  searchByEmbedding: (embedding: number[], params: FaceSimilaritySearchParameters) =>
    apiClient
      .post<PaginatedFaceSimilarityResponse>(`${facesBaseURL}/search/embedding`, {
        ...params,
        embedding,
      })
      .then((res) => res.data),

  getById: (id: string) =>
    apiClient.get<FacePublic>(`${facesBaseURL}/${id}`).then((res) => res.data),

  assign: (id: string, payload: FaceAssignment) =>
    apiClient
      .patch<FacePublic>(`${facesBaseURL}/${id}/assign`, payload)
      .then((res) => res.data),

  setRepresentative: (id: string, payload: FaceRepresentativeUpdate) =>
    apiClient
      .patch<FacePublic>(`${facesBaseURL}/${id}/representative`, payload)
      .then((res) => res.data),

  delete: (id: string) =>
    apiClient.delete<boolean>(`${facesBaseURL}/${id}`).then((res) => res.data),

  // GET /faces/matches - candidate face-to-person matches awaiting (or having received) review
  listMatches: (params: FaceMatchSearchParameters) =>
    apiClient
      .get<PaginatedFaceMatchesResponse>(`${facesBaseURL}/matches`, { params })
      .then((res) => res.data),

  // PATCH /faces/matches/{id} - confirm or reject a candidate match
  resolveMatch: (id: string, status: FaceMatchStatusType, reviewNote?: string) =>
    apiClient
      .patch<FaceMatch>(`${facesBaseURL}/matches/${id}`, { status, reviewNote })
      .then((res) => res.data),
};
