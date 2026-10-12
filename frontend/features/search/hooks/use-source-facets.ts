import { useQuery } from "@tanstack/react-query";
import { searchService } from "../api";

/** Values for the "from the data" filters (Gmail categories, spam / sent ...), counted over searchable files. */
export function useSourceFacets(datasetIds: string[]) {
  return useQuery({
    queryKey: ["search", "source-facets", datasetIds],
    queryFn: () => searchService.sourceFacets(datasetIds.length ? datasetIds : undefined),
    staleTime: 60_000,
  });
}
