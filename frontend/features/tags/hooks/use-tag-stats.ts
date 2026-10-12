import { useQuery } from "@tanstack/react-query";
import { tagService } from "../api";

/** How every tag is used -- analyst labels, model coverage, and yours. */
export function useTagStats() {
  return useQuery({ queryKey: ["tags", "stats"], queryFn: tagService.stats, staleTime: 60_000 });
}

/** Admin only: which image tags have enough analyst labels to train a head. */
export function useTagTrainingReadiness() {
  return useQuery({ queryKey: ["admin", "tag-training"], queryFn: tagService.trainingReadiness });
}
