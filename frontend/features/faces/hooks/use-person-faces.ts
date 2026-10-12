"use client";
import { facesService } from "@/features/faces/api";
import type { PaginatedFacesResponse } from "@/features/faces/types";
import { useInfiniteQuery } from "@tanstack/react-query";

/** All faces assigned to a person, best quality first. */
export function usePersonFaces(personId: string | undefined, limit = 24) {
  return useInfiniteQuery<PaginatedFacesResponse, Error>({
    queryKey: ["faces", "by-person", personId],
    queryFn: ({ pageParam = 1 }) =>
      facesService.search({
        personId,
        sortBy: "qualityScore",
        sortOrder: "desc",
        limit,
        page: pageParam as number,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.hasMore ? lastPage.page + 1 : undefined),
    enabled: !!personId,
  });
}
