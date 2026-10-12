import { useRouter } from "next/navigation";
import { useRunSearch } from "../api";
import { type HandoffTarget, handOff } from "../handoff";
import type { LaneName, OverviewFilters, OverviewRequest } from "../types";

export const EMPTY_FILTERS: OverviewFilters = {
  entityIds: [],
  entityGroups: [],
  filetypeGroups: [],
  dateFrom: null,
  dateTo: null,
};

const SEE_ALL: Record<LaneName, { href: string; target?: HandoffTarget }> = {
  text: { href: "/search/text", target: "text" },
  entities: { href: "/entities", target: "entities" },
  images: { href: "/images", target: "images" },
  events: { href: "/events", target: "events" },
  faces: { href: "/faces" },
  places: { href: "/locations" },
  files: { href: "/search/text", target: "text" },
};

/**
 * What the search page can do from `current` (the search on screen, or the briefing's empty one):
 * run a new query, narrow with filters (a new search whose parent is this one, so Back undoes it),
 * or hand the query to a lane's own page.
 */
export function useSearchActions(current: OverviewRequest & { searchId?: string; imageQuery?: string | null }) {
  const router = useRouter();
  const runSearch = useRunSearch();
  const datasetId = current.datasetIds[0];

  const search = (query: string) =>
    runSearch.mutate({ query, datasetIds: current.datasetIds, filters: current.filters, parentId: current.searchId });

  const narrow = (filters: Partial<OverviewFilters>) =>
    runSearch.mutate({
      query: current.query,
      datasetIds: current.datasetIds,
      filters: {
        ...current.filters,
        ...filters,
        entityIds: [...new Set([...current.filters.entityIds, ...(filters.entityIds ?? [])])],
        entityGroups: [...(current.filters.entityGroups ?? []), ...(filters.entityGroups ?? [])],
        filetypeGroups: [...new Set([...current.filters.filetypeGroups, ...(filters.filetypeGroups ?? [])])],
      },
      parentId: current.searchId,
    });

  const replaceFilters = (filters: OverviewFilters) =>
    runSearch.mutate({ ...current, filters, parentId: current.searchId });

  const seeAll = (lane: LaneName, options?: { imageId?: string }) => {
    const { href, target } = SEE_ALL[lane];
    if (target) {
      const query = target === "images" ? (current.imageQuery ?? current.query) : current.query;
      handOff({ target, query, datasetId, filters: current.filters, imageId: options?.imageId });
    }
    router.push(href);
  };

  return { search, narrow, replaceFilters, seeAll, isSearching: runSearch.isPending };
}
