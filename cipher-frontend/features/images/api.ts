import {
  BaseImageSearchParameters,
  ImagePublic,
  ImageSimilaritySearchParameters,
  PaginatedImagesResponse,
  PaginatedImageSimilarityResponse,
  TextImageKnnSearchRequest,
} from "@/features/images/types";
import { apiClient, baseURL } from "@/lib/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

const imagesBaseURL = "/images";

export const imagesService = {
  //Get uri of image by ID
  getImageUrl: (id: string) => `${baseURL}${imagesBaseURL}/${id}/view`,

  // GET /images/filetypes - distinct file types actually present among images
  getFiletypes: () =>
    apiClient.get<string[]>(`${imagesBaseURL}/filetypes`).then((res) => res.data),

  // POST /images - Non KNN search with JSON body
  searchGeneral: (params: BaseImageSearchParameters) =>
    apiClient
      .post<PaginatedImagesResponse>(`${imagesBaseURL}`, params)
      .then((res) => res.data),

  // GET /search/{id} - Axios serializes 'params' into ?sortBy=...&datasets=...
  searchById: (id: string, params: ImageSimilaritySearchParameters) =>
    apiClient
      .get<PaginatedImageSimilarityResponse>(`${imagesBaseURL}/search/${id}`, { params })
      .then((res) => res.data),

  // POST /search/text - Automatic JSON stringify
  searchByText: (payload: TextImageKnnSearchRequest) =>
    apiClient
      .post<PaginatedImageSimilarityResponse>(`${imagesBaseURL}/search/text`, payload)
      .then((res) => res.data),

  // POST /search/image - Multipart for file, Query Params for the rest
  searchByUpload: (file: File, params: ImageSimilaritySearchParameters) => {
    const formData = new FormData();
    formData.append("file", file);

    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null) return;
      if (Array.isArray(value)) {
        value.forEach((item) => formData.append(key, item.toString()));
      } else {
        formData.append(key, value.toString());
      }
    });

    return apiClient
      .post<PaginatedImageSimilarityResponse>(
        `${imagesBaseURL}/search/image`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      )
      .then((res) => res.data);
  },

  // PATCH /images/{id} - update tags
  updateTags: (id: string, tags: string[]) =>
    apiClient
      .patch<ImagePublic>(`${imagesBaseURL}/${id}`, { tags })
      .then((res) => res.data),
};

export function useImageFiletypes() {
  return useQuery({
    queryKey: ["images", "filetypes"],
    queryFn: imagesService.getFiletypes,
    staleTime: 5 * 60_000,
  });
}

export function useUpdateImageTags() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, tags }: { id: string; tags: string[] }) =>
      imagesService.updateTags(id, tags),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["images"] });
    },
  });
}
