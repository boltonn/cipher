"use client";
import { facesService } from "@/features/faces/api";
import type { FaceAssignment } from "@/features/faces/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function useAssignFace(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, assignment }: { id: string; assignment: FaceAssignment }) =>
      facesService.assign(id, assignment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["faces"] });
      onSuccess?.();
    },
  });
}
