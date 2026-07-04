"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Loader2, Search, X } from "lucide-react";
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
      <form onSubmit={handleSubmit} className="flex items-center gap-3 h-5">
        {/* Search Input */}
        <div
          className={cn(
            "relative flex items-center flex-1 rounded-lg border transition-all",
            isSearching
              ? "bg-indigo-500/5 border-indigo-500/30"
              : "bg-slate-900/40 border-white/10 hover:border-white/20"
          )}
        >
          <div className="flex items-center justify-center pl-3 text-slate-500">
            {isSearching ? (
              <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
            ) : (
              <Search size={16} className="text-slate-400" />
            )}
          </div>

          <input
            type="text"
            aria-label="Search datasets"
            value={localInput}
            onChange={(e) => setLocalInput(e.target.value)}
            placeholder="Search datasets..."
            className="w-full bg-transparent py-2.5 px-3 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
          />

          {localInput && (
            <button
              type="button"
              onClick={() => setLocalInput("")}
              className="pr-3 text-slate-500 hover:text-slate-300"
            >
              <X size={14} />
            </button>
          )}
        </div>

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
