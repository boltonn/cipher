"use client";
import { facesService } from "@/features/faces/api";
import { FaceMatchStatusType } from "@/features/faces/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

/** A face's candidate person matches still awaiting analyst review. */
export function usePendingFaceMatches(faceId: string | undefined) {
  return useQuery({
    queryKey: ["face-matches", "by-face", faceId],
    queryFn: () => facesService.listMatches({ faceId, status: "pending", limit: 10, page: 1 }),
    enabled: !!faceId,
  });
}

export function useResolveFaceMatch(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, status, reviewNote }: { id: string; status: FaceMatchStatusType; reviewNote?: string }) =>
      facesService.resolveMatch(id, status, reviewNote),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["face-matches"] });
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["persons"] });
      onSuccess?.();
    },
  });
}
