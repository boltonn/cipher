"use client";
import { facesService } from "@/features/faces/api";
import type { FaceRepresentativeUpdate } from "@/features/faces/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function useSetFaceRepresentative(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: FaceRepresentativeUpdate }) =>
      facesService.setRepresentative(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      queryClient.invalidateQueries({ queryKey: ["persons"] });
      onSuccess?.();
    },
  });
}
