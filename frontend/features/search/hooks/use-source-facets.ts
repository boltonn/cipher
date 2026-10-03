import { useQuery } from "@tanstack/react-query";
import { searchService } from "../api";

/** Values for the "from the data" filters (Gmail categories, spam / sent ...), counted over searchable files. */
export function useSourceFacets(datasetId?: string) {
  return useQuery({
    queryKey: ["search", "source-facets", datasetId ?? null],
    queryFn: () => searchService.sourceFacets(datasetId ? [datasetId] : undefined),
    staleTime: 60_000,
  });
}
