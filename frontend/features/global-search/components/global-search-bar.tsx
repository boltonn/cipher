"use client";

import { ExactMatchToggle } from "@/components/exact-match-toggle";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Search } from "lucide-react";

interface GlobalSearchBarProps {
  query: string;
  onSearch: (query: string) => void;
  isSearching?: boolean;
  exactMatch: boolean;
  onExactMatchChange: (exactMatch: boolean) => void;
}

/** One box for everything: commits on Enter only (blur would fire a search when clicking a result). */
export function GlobalSearchBar({ query, onSearch, isSearching, exactMatch, onExactMatchChange }: GlobalSearchBarProps) {
  return (
    <SearchBarShell isActive={isSearching} icon={<Search className="size-4 text-muted-foreground" />}>
      <SearchInput
        value={query}
        onSearch={onSearch}
        searchOnBlur={false}
        historyKey={false}
        ariaLabel="Search everything"
        placeholder="Search people, emails, documents, images, events, places… or paste an email or phone number"
      />
      <div className="pr-1">
        <ExactMatchToggle value={exactMatch} onChange={onExactMatchChange} />
      </div>
    </SearchBarShell>
  );
}
