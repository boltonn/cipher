"use client";

import { DateRangePicker } from "@/components/date-range-picker";
import { TagsInput } from "@/components/tags-input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { DatasetMultiSelectCombobox } from "@/features/datasets/components/dataset-multi-select-combobox";
import { useImageFiletypes } from "@/features/images/api";
import { ImageFilters } from "@/features/images/hooks/use-search-controller";
import { cn } from "@/lib/utils";
import { Filter, X } from "lucide-react";
import React, { useState } from "react";

export function hasActiveImageFilters(params: ImageFilters): boolean {
  return !!(
    params.dateFrom ||
    params.dateTo ||
    params.datasets?.length ||
    params.filetypes?.length ||
    params.tags?.length ||
    (params.minSimilarity ?? 0) > 0
  );
}

interface ImageFilterPanelProps {
  params: ImageFilters;
  setParams: React.Dispatch<React.SetStateAction<ImageFilters>>;
  isSimilarityMode: boolean;
  className?: string;
}

/** Filter controls -- rendered as a collapsible bar directly below the image search bar. */
export const ImageFilterPanel: React.FC<ImageFilterPanelProps> = ({
  params,
  setParams,
  isSimilarityMode,
  className,
}) => {
  const { data: filetypes } = useImageFiletypes();

  const [prevMinSimilarity, setPrevMinSimilarity] = useState(params.minSimilarity);
  const [localSimilarity, setLocalSimilarity] = useState(params.minSimilarity ?? 0);
  if (params.minSimilarity !== prevMinSimilarity) {
    setPrevMinSimilarity(params.minSimilarity);
    setLocalSimilarity(params.minSimilarity ?? 0);
  }

  const hasActiveFilters = hasActiveImageFilters(params);

  const updateParam = <K extends keyof ImageFilters>(key: K, value: ImageFilters[K]) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  };

  const clearAllFilters = () => {
    setParams({
      limit: params.limit,
      sortOrder: "desc",
      minSimilarity: 0,
    });
  };

  return (
    <div
      className={cn(
        "w-full bg-muted/40 backdrop-blur-2xl rounded-3xl border border-border shadow-[0_8px_32px_0_rgba(0,0,0,0.8)] p-6",
        className
      )}
    >
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2.5 text-muted-foreground">
          <Filter size={14} />
          <h3 className="text-[10px] font-black uppercase tracking-[0.2em]">Filters</h3>
        </div>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={clearAllFilters}
            className="text-[10px] font-bold uppercase tracking-widest text-destructive/70 hover:text-destructive flex items-center gap-1 transition-colors"
          >
            <X size={11} /> Reset
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-x-8 gap-y-6">
        {/* Date Taken */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
            Date Taken
          </span>
          <DateRangePicker
            placeholder="Any date"
            value={{ from: params.dateFrom, to: params.dateTo }}
            onChange={({ from, to }) => {
              setParams((prev) => ({ ...prev, dateFrom: from, dateTo: to }));
            }}
          />
        </div>

        {/* Datasets */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
            Datasets
          </span>
          <DatasetMultiSelectCombobox
            value={params.datasets ?? []}
            onChange={(datasets) => updateParam("datasets", datasets.length ? datasets : undefined)}
          />
        </div>

        {/* File Types */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
            File Types
          </span>
          <div className="flex min-h-9 flex-wrap content-start items-center gap-2">
            {(filetypes ?? []).map((ft) => {
              const active = params.filetypes?.includes(ft);
              return (
                <button
                  key={ft}
                  type="button"
                  onClick={() => {
                    const current = params.filetypes ?? [];
                    const next = active ? current.filter((t) => t !== ft) : [...current, ft];
                    updateParam("filetypes", next.length ? next : undefined);
                  }}
                  className={cn(
                    "h-7 rounded-lg border px-2.5 text-[10px] font-bold uppercase transition-all",
                    active
                      ? "bg-primary/20 border-primary/40 text-primary"
                      : "bg-transparent border-border text-muted-foreground hover:text-foreground hover:border-white/20"
                  )}
                >
                  {ft}
                </button>
              );
            })}
            {filetypes?.length === 0 && (
              <span className="text-[10px] text-muted-foreground italic self-center">
                No file types found
              </span>
            )}
          </div>
        </div>

        {/* Tags */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
            Tags
          </span>
          <TagsInput
            value={params.tags ?? []}
            onChange={(tags) => updateParam("tags", tags.length ? tags : undefined)}
            placeholder="Add a tag..."
          />
        </div>
      </div>

      {/* Similarity */}
      <div className="mt-6 pt-6 border-t border-border flex flex-col gap-2 max-w-md">
        <div className="flex items-center justify-between gap-2">
          <Label
            htmlFor="image-similarity-slider"
            className={cn(
              "text-[10px] font-bold uppercase tracking-[0.2em]",
              isSimilarityMode ? "text-primary" : "text-muted-foreground"
            )}
          >
            Min Similarity
          </Label>
          <span className="text-[11px] font-mono font-bold text-primary tabular-nums shrink-0">
            {(localSimilarity * 100).toFixed(0)}%
          </span>
        </div>
        <Slider
          id="image-similarity-slider"
          value={[localSimilarity]}
          min={0}
          max={1}
          step={0.01}
          onValueChange={([v]) => setLocalSimilarity(v)}
          onValueCommit={([v]) => updateParam("minSimilarity", v)}
          className="py-2"
          disabled={!isSimilarityMode}
        />
        {!isSimilarityMode && (
          <span className="text-[10px] text-muted-foreground italic">
            Only applies to similarity searches (text, image, or find-similar)
          </span>
        )}
      </div>
    </div>
  );
};
