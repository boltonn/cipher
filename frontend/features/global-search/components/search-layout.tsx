"use client";

import { PageHeader } from "@/components/page-header";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { Search } from "lucide-react";
import type { LaneName } from "../types";
import { GlobalSearchBar } from "./global-search-bar";

const LANE_CHIPS: { lane: LaneName; label: string }[] = [
  { lane: "text", label: "Emails & documents" },
  { lane: "entities", label: "People & organizations" },
  { lane: "images", label: "Images" },
  { lane: "faces", label: "Faces" },
  { lane: "events", label: "Events" },
  { lane: "places", label: "Places" },
];

interface SearchLayoutProps {
  query: string;
  datasetIds: string[];
  onDatasetIdsChange: (datasetIds: string[]) => void;
  onSearch: (query: string) => void;
  isSearching: boolean;
  exactMatch: boolean;
  onExactMatchChange: (exactMatch: boolean) => void;
  /** Header readout, e.g. the result timing. */
  value?: React.ReactNode;
  /** When set, shows "All · …" chips that open each lane's own page with this query. */
  onOpenLane?: (lane: LaneName) => void;
  filterChips?: React.ReactNode;
  /** Extra header actions next to the dataset picker, e.g. saving the search. */
  headerActions?: React.ReactNode;
  children: React.ReactNode;
}

/** Shared frame of the search pages: header + dataset, the one search box, lane chips, then the body. */
export function SearchLayout({
  query,
  datasetIds,
  onDatasetIdsChange,
  onSearch,
  isSearching,
  exactMatch,
  onExactMatchChange,
  value,
  onOpenLane,
  filterChips,
  headerActions,
  children,
}: SearchLayoutProps) {
  return (
    <div className="mx-auto flex w-full max-w-400 flex-col px-6 pb-10 pt-5">
      <PageHeader
        eyebrow="Search"
        icon={<Search size={10} className="text-primary/50" />}
        value={value ?? "Everything in your datasets"}
        actions={
          <div className="flex items-center gap-2">
            {headerActions}
            <DatasetSelect datasetIds={datasetIds} placeholder="All datasets" onChange={onDatasetIdsChange} />
          </div>
        }
      />
      <div className="mt-4 space-y-2">
        <GlobalSearchBar
          query={query}
          onSearch={onSearch}
          isSearching={isSearching}
          exactMatch={exactMatch}
          onExactMatchChange={onExactMatchChange}
        />
        {onOpenLane && (
          <nav aria-label="Search one kind of result" className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="inline-flex h-7 items-center rounded-full bg-primary/15 px-2.5 font-medium text-primary">
              All
            </span>
            {LANE_CHIPS.map(({ lane, label }) => (
              <button
                key={lane}
                type="button"
                onClick={() => onOpenLane(lane)}
                className="inline-flex h-7 items-center rounded-full border border-border px-2.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                {label}
              </button>
            ))}
          </nav>
        )}
        {filterChips}
      </div>
      <div className="mt-5">{children}</div>
    </div>
  );
}
