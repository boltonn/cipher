"use client";

import { Briefing } from "@/features/global-search/components/briefing";
import { SearchLayout } from "@/features/global-search/components/search-layout";
import { EMPTY_FILTERS, useSearchActions } from "@/features/global-search/hooks/use-search-actions";
import { useState } from "react";
import { useSelectedDatasets } from "@/features/datasets/hooks/use-selected-datasets";

/** Global search, before a query: the briefing of what the selected datasets contain. */
export default function SearchPage() {
  const { datasetIds, setDatasetIds } = useSelectedDatasets();
  const [exactMatch, setExactMatch] = useState(false);
  const actions = useSearchActions({ query: "", datasetIds, filters: { ...EMPTY_FILTERS, exactMatch } });

  return (
    <SearchLayout
      query=""
      datasetIds={datasetIds}
      onDatasetIdsChange={setDatasetIds}
      onSearch={(query) => query.trim() && actions.search(query)}
      isSearching={actions.isSearching}
      exactMatch={exactMatch}
      onExactMatchChange={setExactMatch}
    >
      <Briefing
        datasetIds={datasetIds}
        onFilter={actions.narrow}
        onSearch={actions.search}
        onOpenImage={(imageId) => actions.seeAll("images", { imageId })}
      />
    </SearchLayout>
  );
}
