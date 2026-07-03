import {
  BaseImageSearchParameters,
  ImageSimilaritySearchParameters,
  PaginatedImagesResponse,
  TextImageKnnSearchRequest,
} from "@/features/images/types";
import { apiClient, baseURL } from "@/lib/api-client";

const imagesBaseURL = "/images";

export const imagesService = {
  //Get uri of image by ID
  getImageUrl: (id: string) => `${baseURL}${imagesBaseURL}/${id}/view`,

  // POST /images - Non KNN search with JSON body
  searchGeneral: (params: BaseImageSearchParameters) =>
    apiClient
      .post<PaginatedImagesResponse>(`${imagesBaseURL}`, params)
      .then((res) => res.data),

  // GET /search/{id} - Axios serializes 'params' into ?sortBy=...&datasets=...
  searchById: (id: string, params: ImageSimilaritySearchParameters) =>
    apiClient
      .get<PaginatedImagesResponse>(`${imagesBaseURL}/search/${id}`, { params })
      .then((res) => res.data),

  // POST /search/text - Automatic JSON stringify
  searchByText: (payload: TextImageKnnSearchRequest) =>
    apiClient
      .post<PaginatedImagesResponse>(`${imagesBaseURL}/search/text`, payload)
      .then((res) => res.data),

  // POST /search/image - Multipart for file, Query Params for the rest
  searchByUpload: (file: File, params: ImageSimilaritySearchParameters) => {
    const formData = new FormData();
    formData.append("file", file);

    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        formData.append(key, value.toString());
      }
    });

    return apiClient
      .post<PaginatedImagesResponse>(
        `${imagesBaseURL}/search/image`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      )
      .then((res) => res.data);
  },
};
