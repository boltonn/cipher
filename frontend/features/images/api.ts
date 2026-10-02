import type { FileRecord } from "@/features/files/types";
import {
  BaseImageSearchParameters,
  ImagePublic,
  ImageSimilaritySearchParameters,
  ImageTagRequest,
  ImageTagResult,
  PaginatedImagesResponse,
  PaginatedImageSimilarityResponse,
  TextImageKnnSearchRequest,
} from "@/features/images/types";
import { apiClient, baseURL } from "@/lib/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

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

  // GET /images/{id} - single image record by its content id (sha256)
  getById: (id: string): Promise<ImagePublic> =>
    apiClient.get<ImagePublic>(`${imagesBaseURL}/${id}`).then((res) => res.data),

  // PATCH /images/{id} - update tags
  updateTags: (id: string, tags: string[]) =>
    apiClient
      .patch<ImagePublic>(`${imagesBaseURL}/${id}`, { tags })
      .then((res) => res.data),

  // POST /images/tag - bulk label: positive, negative, or (no type) clear
  tag: (payload: ImageTagRequest) =>
    apiClient
      .post<ImageTagResult>(`${imagesBaseURL}/tag`, payload)
      .then((res) => res.data),

  // GET /files/{id}/image -- a 404 just means this file has no Image record yet
  getByFileId: (fileId: string): Promise<ImagePublic> =>
    apiClient
      .get<ImagePublic>(`/files/${fileId}/image`, { suppressErrorToast: true })
      .then((res) => res.data),

  // GET /images/{id}/files -- every file whose content is this image (matched on sha256)
  getFiles: (id: string): Promise<FileRecord[]> =>
    apiClient
      .get<FileRecord[]>(`${imagesBaseURL}/${id}/files`)
      .then((res) => res.data),
};

export function useImageFiletypes() {
  return useQuery({
    queryKey: ["images", "filetypes"],
    queryFn: imagesService.getFiletypes,
    staleTime: 5 * 60_000,
  });
}

/** Resolve a single image record by its content id; React Query dedupes across callers. */
export function useImage(imageId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["images", imageId],
    queryFn: () => imagesService.getById(imageId as string),
    enabled: !!imageId && (options?.enabled ?? true),
    staleTime: 60_000,
  });
}

/** A 404 (file has no associated Image record) resolves as `isError`, not a thrown/toasted error. */
export function useFileImage(fileId: string | undefined) {
  return useQuery({
    queryKey: ["files", fileId, "image"],
    queryFn: () => imagesService.getByFileId(fileId as string),
    enabled: !!fileId,
    staleTime: 60_000,
    retry: false,
  });
}

/** Every file the image's content was found in; shown on the image detail view. */
export function useImageFiles(imageId: string | undefined) {
  return useQuery({
    queryKey: ["images", imageId, "files"],
    queryFn: () => imagesService.getFiles(imageId as string),
    enabled: !!imageId,
    staleTime: 60_000,
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

/** Label a set of images with one tag; accepting or rejecting a predicted tag is the same call. */
export function useTagImages(onSuccess?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ImageTagRequest) => imagesService.tag(payload),
    onSuccess: ({ updated }, { tag, type }) => {
      queryClient.invalidateQueries({ queryKey: ["images"] });
      const images = `${updated.toLocaleString()} image${updated === 1 ? "" : "s"}`;
      toast.success(
        type === "positive"
          ? `Tagged ${images} “${tag}”`
          : type === "negative"
            ? `Marked ${images} not “${tag}”`
            : `Removed “${tag}” from ${images}`
      );
      onSuccess?.();
    },
    onError: () => toast.error("Couldn't update tags"),
  });
}
