"use client";

import { SearchBarShell } from "@/components/search-bar-shell";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { Search, Sparkles, Type, Zap } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import type { SearchMode } from "../types";

const SEARCH_MODE_LABELS: Record<SearchMode, string> = {
  text: "Text",
  semantic: "Semantic",
  hybrid: "Hybrid",
};

interface SearchToolbarProps {
  isSearching: boolean;
  searchMode: SearchMode;
  groupByFile: boolean;
  onSearch: (query: string) => void;
  onSearchModeChange: (mode: SearchMode) => void;
  onToggleGroupByFile: () => void;
}

export function SearchToolbar({
  isSearching,
  searchMode,
  groupByFile,
  onSearch,
  onSearchModeChange,
  onToggleGroupByFile,
}: SearchToolbarProps) {
  const [inputValue, setInputValue] = useState("");
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const debouncedSearch = useCallback(
    (value: string) => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
      searchTimerRef.current = setTimeout(() => {
        if (value.trim()) onSearch(value.trim());
      }, 500);
    },
    [onSearch]
  );

  return (
    <div className="flex flex-1 items-center gap-4">
      <div className="flex-1">
        <SearchBarShell isActive={isSearching} icon={<Search size={16} strokeWidth={1.5} />}>
          <input
            aria-label="Search documents and emails"
            type="text"
            autoComplete="off"
            placeholder="Search documents and emails..."
            className="w-full bg-transparent py-3 px-2 text-sm tracking-wide text-slate-100 placeholder:text-slate-600 focus:outline-none"
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value);
              debouncedSearch(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && inputValue.trim()) onSearch(inputValue.trim());
            }}
          />
          <div className="flex items-center gap-0.5 pr-1">
            {(Object.keys(SEARCH_MODE_LABELS) as SearchMode[]).map((mode) => {
              const Icon = mode === "text" ? Type : mode === "semantic" ? Sparkles : Zap;
              const isActive = searchMode === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => onSearchModeChange(mode)}
                  title={SEARCH_MODE_LABELS[mode]}
                  className={cn(
                    "flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium transition-colors",
                    isActive
                      ? "bg-indigo-600 text-white hover:bg-indigo-500"
                      : "text-slate-500 hover:text-slate-300"
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

      <div className="flex shrink-0 items-center gap-2">
        <Switch id="group-by-file" checked={groupByFile} onCheckedChange={onToggleGroupByFile} />
        <Label htmlFor="group-by-file" className="text-xs text-slate-400">
          Group by file
        </Label>
      </div>
    </div>
  );
}
