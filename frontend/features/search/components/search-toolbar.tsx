"use client";

import { ExactMatchToggle } from "@/components/exact-match-toggle";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { cn } from "@/lib/utils";
import { Search, Sparkles, Type, Zap } from "lucide-react";
import type { SearchMode } from "../types";

const SEARCH_MODE_LABELS: Record<SearchMode, string> = {
  text: "Text",
  semantic: "Semantic",
  hybrid: "Hybrid",
};

interface SearchToolbarProps {
  isSearching: boolean;
  searchMode: SearchMode;
  /** Exact phrase only; ranking is keyword-only while on, so the mode buttons sit out. */
  exactMatch: boolean;
  onExactMatchChange: (exactMatch: boolean) => void;
  /** The committed query -- clearing it back to "" is a real search (browse the full index). */
  query: string;
  onSearch: (query: string) => void;
  onSearchModeChange: (mode: SearchMode) => void;
}

export function SearchToolbar({
  isSearching,
  searchMode,
  exactMatch,
  onExactMatchChange,
  query,
  onSearch,
  onSearchModeChange,
}: SearchToolbarProps) {
  return (
    <div className="flex flex-1 items-center gap-4">
      <div className="flex-1">
        <SearchBarShell isActive={isSearching} icon={<Search size={16} strokeWidth={1.5} />}>
          <SearchInput
            ariaLabel="Search documents and emails"
            placeholder="Search documents and emails..."
            value={query}
            onSearch={onSearch}
          />
          <div className="flex items-center gap-0.5 pr-1">
            <ExactMatchToggle value={exactMatch} onChange={onExactMatchChange} />
            {(Object.keys(SEARCH_MODE_LABELS) as SearchMode[]).map((mode) => {
              const Icon = mode === "text" ? Type : mode === "semantic" ? Sparkles : Zap;
              const isActive = !exactMatch && searchMode === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  disabled={exactMatch}
                  onClick={() => onSearchModeChange(mode)}
                  title={SEARCH_MODE_LABELS[mode]}
                  className={cn(
                    "flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium transition-colors disabled:opacity-40",
                    isActive
                      ? "bg-primary text-white hover:bg-primary"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  {isActive && SEARCH_MODE_LABELS[mode]}
                </button>
              );
            })}
          </div>
        </SearchBarShell>
      </div>
    </div>
  );
}
