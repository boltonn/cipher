"use client";

import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Search } from "lucide-react";

interface DatasetsSearchBarProps {
  query?: string;
  onSearch: (query: string) => void;
  onClearFilters: () => void;
  isSearching?: boolean;
}

export function DatasetsSearchBar({
  query,
  onSearch,
  onClearFilters,
  isSearching,
}: DatasetsSearchBarProps) {
  const hasActiveFilters = !!query;

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center gap-3">
        <SearchBarShell isActive={isSearching} icon={<Search size={18} strokeWidth={1.5} />} className="flex-1">
          <SearchInput ariaLabel="Search datasets" placeholder="Search datasets..." value={query ?? ""} onSearch={onSearch} />
        </SearchBarShell>

        {/* Clear Filters */}
        {hasActiveFilters && (
          <Button
            type="button"
            onClick={onClearFilters}
            variant="ghost"
            className="h-9 px-3 text-xs text-muted-foreground hover:text-foreground"
          >
            Clear
          </Button>
        )}
      </div>
    </div>
  );
}
