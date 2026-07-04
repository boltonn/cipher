"use client";

import { SearchBarShell } from "@/components/search-bar-shell";
import { Button } from "@/components/ui/button";
import { Search, X } from "lucide-react";
import React, { useState } from "react";

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
  const [localInput, setLocalInput] = useState(query || "");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(localInput);
  };

  const hasActiveFilters = !!localInput;

  return (
    <div className="w-full space-y-4">
      <form onSubmit={handleSubmit} className="flex items-center gap-3">
        <SearchBarShell isActive={isSearching} icon={<Search size={18} strokeWidth={1.5} />} className="flex-1">
          <input
            type="text"
            aria-label="Search datasets"
            autoComplete="off"
            value={localInput}
            onChange={(e) => setLocalInput(e.target.value)}
            placeholder="Search datasets..."
            className="w-full bg-transparent py-4 px-4 text-slate-100 placeholder:text-slate-600 focus:outline-none text-sm tracking-wide"
          />

          {localInput && (
            <button
              type="button"
              onClick={() => setLocalInput("")}
              className="text-slate-500 hover:text-slate-300 shrink-0"
            >
              <X size={14} />
            </button>
          )}
        </SearchBarShell>

        {/* Clear Filters */}
        {hasActiveFilters && (
          <Button
            type="button"
            onClick={() => {
              setLocalInput("");
              onClearFilters();
            }}
            variant="ghost"
            className="h-9 px-3 text-xs text-slate-500 hover:text-slate-300"
          >
            Clear
          </Button>
        )}
      </form>
    </div>
  );
}
