"use client";

import { EmptyState } from "@/components/empty-state";
import { PageLoading } from "@/components/page-loading";
import { useSelectedDatasets } from "@/features/datasets/hooks/use-selected-datasets";
import { useRunSearch, useSearchAssist, useSearchOverview } from "@/features/global-search/api";
import { AiPanel } from "@/features/global-search/components/ai-panel";
import { FilterChips } from "@/features/global-search/components/filter-chips";
import { OverviewResults } from "@/features/global-search/components/overview-results";
import { SearchLayout } from "@/features/global-search/components/search-layout";
import { SaveSearchButton } from "@/features/global-search/components/save-search-button";
import { SearchTrail } from "@/features/global-search/components/search-trail";
import { useRememberedScroll } from "@/features/global-search/hooks/use-remembered-scroll";
import { useSearchActions } from "@/features/global-search/hooks/use-search-actions";
import type { OverviewResponse } from "@/features/global-search/types";
import { SearchX } from "lucide-react";
import { useParams } from "next/navigation";

function Results({ overview }: { overview: OverviewResponse }) {
  const { request, layout, searchId } = overview;
  const actions = useSearchActions({ ...request, searchId, imageQuery: layout.imageQuery });
  const rescope = useRunSearch();
  const { setDatasetIds } = useSelectedDatasets();
  const nothing = layout.laneOrder.length === 0;
  const scrollRef = useRememberedScroll<HTMLDivElement>(searchId);
  // Same cached query the AI panel runs; when the model reads the search as visual, images lead.
  const { data: assist } = useSearchAssist(searchId, !!request.query);

  return (
    <SearchLayout
      query={request.query}
      datasetIds={request.datasetIds}
      onDatasetIdsChange={(datasetIds) => {
        setDatasetIds(datasetIds);
        rescope.mutate({ ...request, datasetIds, parentId: searchId });
      }}
      onSearch={actions.search}
      isSearching={actions.isSearching || rescope.isPending}
      value={`Searched everything in ${(overview.tookMs / 1000).toFixed(1)} s`}
      onOpenLane={actions.seeAll}
      headerActions={<SaveSearchButton searchId={searchId} query={request.query} />}
      exactMatch={!!request.filters.exactMatch}
      onExactMatchChange={(exactMatch) => actions.replaceFilters({ ...request.filters, exactMatch })}
      filterChips={
        <>
          <SearchTrail trail={overview.trail} />
          <FilterChips filters={request.filters} onChange={actions.replaceFilters} />
        </>
      }
    >
      <div ref={scrollRef} className="space-y-4">
        <AiPanel overview={overview} onApply={(next) => rescope.mutate(next)} />
        {nothing ? (
          <EmptyState icon={SearchX} title="No matches" body="Try fewer words, or remove a filter." />
        ) : (
          <OverviewResults
            overview={overview}
            isVisual={!!assist?.isVisual}
            onAddFilters={actions.narrow}
            onSeeAll={actions.seeAll}
          />
        )}
      </div>
    </SearchLayout>
  );
}

/** One search's results; the id is opaque (the query never goes in the URL), so Back walks searches. */
export default function SearchResultsPage() {
  const { searchId } = useParams<{ searchId: string }>();
  const { data: overview, isPending, isError } = useSearchOverview(searchId);
  if (isPending) return <PageLoading />;
  if (isError || !overview) {
    return <EmptyState icon={SearchX} title="Search not found" body="It may have expired from your history." />;
  }
  return <Results key={overview.searchId} overview={overview} />;
}
