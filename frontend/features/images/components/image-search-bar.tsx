"use client";

import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import {
  hasActiveImageFilters,
  ImageFilterPanel,
} from "@/features/images/components/image-filter-panel";
import { ImageFilters } from "@/features/images/hooks/use-search-controller";
import { cn } from "@/lib/utils";
import { Filter, ImageIcon, Search } from "lucide-react";
import React, { useRef, useState } from "react";

interface ImageSearchBarProps {
  onSearch: (query: string) => void;
  onImageUpload: (file: File) => void;
  isSearching: boolean;
  filters: ImageFilters;
  setFilters: React.Dispatch<React.SetStateAction<ImageFilters>>;
  isSimilarityMode: boolean;
  isFiltersOpen: boolean;
  onToggleFilters: () => void;
}

export const ImageSearchBar: React.FC<ImageSearchBarProps> = ({
  onSearch,
  onImageUpload,
  isSearching,
  filters,
  setFilters,
  isSimilarityMode,
  isFiltersOpen,
  onToggleFilters,
}) => {
  const [query, setQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="w-full transition-all duration-500">
      <SearchBarShell isActive={isSearching} icon={<Search size={18} strokeWidth={1.5} />}>
        <SearchInput
          ariaLabel="Search images"
          placeholder="Search images, or drop one here…"
          value={query}
          searchOnBlur={false}
          onSearch={(next) => {
            setQuery(next);
            if (next) onSearch(next);
          }}
        />

        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Filters"
            aria-expanded={isFiltersOpen}
            onClick={onToggleFilters}
            className={cn(
              "relative h-7 w-7",
              isFiltersOpen ? "text-primary" : "text-muted-foreground hover:text-primary"
            )}
          >
            <Filter size={15} strokeWidth={1.5} />
            {hasActiveImageFilters(filters) && (
              <span className="absolute top-1 right-1 h-1.5 w-1.5 rounded-full bg-primary" />
            )}
          </Button>

          <div className="mx-1 h-4 w-px bg-border" />

          <input
            name="image"
            type="file"
            aria-label="Upload image"
            ref={fileInputRef}
            className="hidden"
            accept="image/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onImageUpload(file);
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Search by image"
            title="Search by image"
            className="h-7 w-7 text-muted-foreground hover:text-primary"
            onClick={() => fileInputRef.current?.click()}
          >
            <ImageIcon size={15} strokeWidth={1.5} />
          </Button>
        </div>
      </SearchBarShell>

      <div
        className={cn(
          "grid transition-all duration-300 ease-in-out overflow-hidden",
          isFiltersOpen ? "grid-rows-[1fr] opacity-100 mt-3" : "grid-rows-[0fr] opacity-0"
        )}
      >
        <div className="min-h-0">
          <ImageFilterPanel params={filters} setParams={setFilters} isSimilarityMode={isSimilarityMode} />
        </div>
      </div>
    </div>
  );
};
