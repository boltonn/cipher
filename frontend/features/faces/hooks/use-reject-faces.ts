"use client";
import { facesService } from "@/features/faces/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

const plural = (n: number, word: string) =>
  `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

/**
 * Face state touched by a (un)reject: every face list, person face counts and
 * the photo co-occurrence graph.
 */
function useInvalidateFaceState() {
  const queryClient = useQueryClient();
  return () => {
    for (const queryKey of [
      ["faces"],
      ["face-matches"],
      ["persons"],
      ["graph-explore"],
    ])
      queryClient.invalidateQueries({ queryKey });
  };
}

export function useUnrejectFaces(onSuccess?: () => void) {
  const invalidate = useInvalidateFaceState();
  return useMutation({
    mutationFn: (faceIds: string[]) => facesService.unreject(faceIds),
    onSuccess: (result) => {
      invalidate();
      toast.success(`Restored ${plural(result.updated, "face")}`);
      onSuccess?.();
    },
    onError: () => toast.error("Couldn't restore faces"),
  });
}

/** Mark faces "not a face"; the toast reports auto-rejected look-alikes and offers undo. */
export function useRejectFaces(onSuccess?: () => void) {
  const invalidate = useInvalidateFaceState();
  const unreject = useUnrejectFaces();
  return useMutation({
    mutationFn: (faceIds: string[]) => facesService.reject({ faceIds }),
    onSuccess: (result, faceIds) => {
      invalidate();
      toast.success(`Marked ${plural(result.updated, "face")} as not a face`, {
        description: result.autoRejected
          ? `${plural(result.autoRejected, "similar face")} auto-rejected too`
          : undefined,
        action: { label: "Undo", onClick: () => unreject.mutate(faceIds) },
      });
      onSuccess?.();
    },
    onError: () => toast.error("Couldn't mark faces as not a face"),
  });
}
