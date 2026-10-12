"use client";
import { facesService } from "@/features/faces/api";
import type { FacePublic } from "@/features/faces/types";
import { useQuery } from "@tanstack/react-query";

/** Every face detected in a given image, for the shared asset viewer's overlays. */
export function useImageFaces(imageId: string | undefined) {
  return useQuery<FacePublic[]>({
    queryKey: ["faces", "by-image", imageId],
    queryFn: () =>
      facesService
        .search({ imageId, sortBy: "qualityScore", sortOrder: "desc", limit: 100, page: 1 })
        .then((res) => res.data),
    enabled: !!imageId,
    staleTime: 60_000,
  });
}
