"use client";

import { TagsInput } from "@/components/tags-input";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { DatasetMultiSelectCombobox } from "@/features/datasets/components/dataset-multi-select-combobox";
import { useImageFiletypes } from "@/features/images/api";
import { ImageFilters } from "@/features/images/hooks/use-search-controller";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { CalendarIcon, Filter, X } from "lucide-react";
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

interface DatePickerProps {
  label: string;
  value: string | undefined;
  onChange: (date: Date | undefined) => void;
}

const DatePicker = ({ label, value, onChange }: DatePickerProps) => (
  <Popover>
    <PopoverTrigger asChild>
      <Button
        variant="outline"
        className={cn(
          "w-full justify-start text-left font-normal text-xs h-9 bg-slate-900/40 border-white/10 hover:bg-slate-900/60",
          !value && "text-slate-500"
        )}
      >
        <CalendarIcon className="mr-2 h-3 w-3" />
        {value ? format(new Date(value), "PPP") : <span>{label}</span>}
      </Button>
    </PopoverTrigger>
    <PopoverContent className="w-auto p-0 bg-slate-950 border-white/10" align="start">
      <Calendar mode="single" selected={value ? new Date(value) : undefined} onSelect={onChange} className="rounded-md border-none" />
    </PopoverContent>
  </Popover>
);

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
        "w-full bg-slate-950/40 backdrop-blur-2xl rounded-3xl border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.8)] p-6",
        className
      )}
    >
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2.5 text-slate-400">
          <Filter size={14} />
          <h3 className="text-[10px] font-black uppercase tracking-[0.2em]">Filters</h3>
        </div>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={clearAllFilters}
            className="text-[10px] font-bold uppercase tracking-widest text-rose-500/70 hover:text-rose-400 flex items-center gap-1 transition-colors"
          >
            <X size={11} /> Reset
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-x-8 gap-y-6">
        {/* Date Taken */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
            Date Taken
          </span>
          <div className="grid grid-cols-2 gap-3">
            <DatePicker
              label="From"
              value={params.dateFrom}
              onChange={(d) => updateParam("dateFrom", d?.toISOString())}
            />
            <DatePicker
              label="To"
              value={params.dateTo}
              onChange={(d) => updateParam("dateTo", d?.toISOString())}
            />
          </div>
        </div>

        {/* Datasets */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
            Datasets
          </span>
          <DatasetMultiSelectCombobox
            value={params.datasets ?? []}
            onChange={(datasets) => updateParam("datasets", datasets.length ? datasets : undefined)}
          />
        </div>

        {/* File Types */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
            File Types
          </span>
          <div className="flex flex-wrap gap-2">
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
                    "text-[10px] font-bold uppercase px-2.5 py-1.5 rounded-lg border transition-all",
                    active
                      ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-300"
                      : "bg-transparent border-white/10 text-slate-500 hover:text-slate-200 hover:border-white/20"
                  )}
                >
                  {ft}
                </button>
              );
            })}
            {filetypes?.length === 0 && (
              <span className="text-[10px] text-slate-600 italic">No file types found</span>
            )}
          </div>
        </div>

        {/* Tags */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
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
      <div className="mt-6 pt-6 border-t border-white/10 flex flex-col gap-2 max-w-md">
        <div className="flex items-center justify-between gap-2">
          <Label
            htmlFor="image-similarity-slider"
            className={cn(
              "text-[10px] font-bold uppercase tracking-[0.2em]",
              isSimilarityMode ? "text-indigo-400" : "text-slate-500"
            )}
          >
            Min Similarity
          </Label>
          <span className="text-[11px] font-mono font-bold text-indigo-400 tabular-nums shrink-0">
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
          <span className="text-[10px] text-slate-600 italic">
            Only applies to similarity searches (text, image, or find-similar)
          </span>
        )}
      </div>
    </div>
  );
};
