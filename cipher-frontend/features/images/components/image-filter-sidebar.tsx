"use client";

import { format } from "date-fns";
import {
  CalendarIcon,
  ChevronDown,
  Database,
  FileCode,
  Filter,
  Hash,
  X,
} from "lucide-react";
import React, { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";

import { cn } from "@/lib/utils";
import { AVAILABLE_TAGS, DATASETS, FILE_TYPES } from "../constants";
import { ImageFilters } from "../hooks/use-search-controller";

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
          "w-full justify-start text-left font-normal text-xs h-10 bg-slate-900/40 border-white/5 hover:bg-slate-900/60 hover:border-white/10",
          !value && "text-slate-500"
        )}
      >
        <CalendarIcon className="mr-2 h-3 w-3" />
        {value ? format(new Date(value), "PPP") : <span>{label}</span>}
      </Button>
    </PopoverTrigger>
    <PopoverContent
      className="w-auto p-0 bg-slate-950 border-white/10"
      align="start"
    >
      <Calendar
        mode="single"
        selected={value ? new Date(value) : undefined}
        onSelect={onChange}
        className="rounded-md border-none"
      />
    </PopoverContent>
  </Popover>
);

interface ImageFilterSidebarProps {
  isMinimized: boolean;
  setIsMinimized: (value: boolean) => void;
  params: ImageFilters;
  setParams: React.Dispatch<React.SetStateAction<ImageFilters>>;
  className?: string;
}

function toggleList(list: string[] | undefined, item: string) {
  const current = list || [];
  return current.includes(item)
    ? current.filter((i) => i !== item)
    : [...current, item];
}

// image-filter-sidebar.tsx

export const ImageFilterSidebar: React.FC<ImageFilterSidebarProps> = ({
  params,
  setParams,
  isMinimized,
  setIsMinimized,
  className,
}) => {
  const prevSimilarityRef = useRef(params.minSimilarity || 0);
  const [localSimilarity, setLocalSimilarity] = useState(
    params.minSimilarity || 0
  );

  if (params.minSimilarity !== prevSimilarityRef.current) {
    prevSimilarityRef.current = params.minSimilarity || 0;
    setLocalSimilarity(params.minSimilarity || 0);
  }

  const hasActiveFilters = !!(
    params.dateFrom ||
    params.dateTo ||
    (params.datasets && params.datasets.length > 0) ||
    (params.filetypes && params.filetypes.length > 0) ||
    (params.tags && params.tags.length > 0) ||
    (params.minSimilarity && params.minSimilarity > 0)
  );

  const updateParam = <K extends keyof ImageFilters>(
    key: K,
    value: ImageFilters[K]
  ) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  };

  const clearAllFilters = (e: React.MouseEvent) => {
    e.stopPropagation();
    setParams({
      limit: 20,
      sortBy: "dateTaken",
      sortOrder: "desc",
      minSimilarity: 0,
    });
  };

  return (
    <div
      className={cn(
        "w-full bg-slate-950/40 backdrop-blur-2xl rounded-3xl flex flex-col border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.8)] transition-all duration-300",
        className
      )}
    >
      {/* Header with toggle logic - ALWAYS VISIBLE */}
      <div className="flex w-full items-center justify-between group p-6">
        <button
          type="button"
          className="flex items-center gap-2.5 text-slate-400 group-hover:text-indigo-400 transition-colors text-left"
          onClick={() => setIsMinimized(!isMinimized)}
        >
          <div className="relative">
            <Filter size={14} />
            {hasActiveFilters && (
              <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.8)] animate-pulse" />
            )}
          </div>
          <h3 className="text-[10px] font-black uppercase tracking-[0.2em]">
            Filters
          </h3>
        </button>

        <div className="flex items-center gap-3">
          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearAllFilters}
              className="text-[9px] font-bold uppercase tracking-widest text-rose-500/60 hover:text-rose-400 flex items-center gap-1 transition-colors"
            >
              <X size={10} /> Reset
            </button>
          )}
          <button
            type="button"
            aria-label={isMinimized ? "Expand filters" : "Collapse filters"}
            onClick={() => setIsMinimized(!isMinimized)}
          >
            <ChevronDown
              size={14}
              className={cn(
                "text-slate-600 transition-transform duration-300",
                isMinimized ? "-rotate-90" : "rotate-0"
              )}
            />
          </button>
        </div>
      </div>

      {/* Collapsible Content Wrapper - REMOVE overflow-hidden, use grid instead */}
      <div
        className={cn(
          "grid transition-all duration-500 ease-in-out px-6",
          isMinimized
            ? "grid-rows-[0fr] opacity-0"
            : "grid-rows-[1fr] opacity-100 pb-6"
        )}
      >
        {/* Inner wrapper with min-h-0 for grid trick */}
        <div className="min-h-0">
          <div className="flex flex-col gap-8">
            {/* Date Taken Section */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-slate-500">
                <CalendarIcon size={14} />
                <span className="text-[10px] font-bold uppercase tracking-[0.2em]">
                  Date Taken
                </span>
              </div>
              <div className="grid gap-2">
                <DatePicker
                  label="From date"
                  value={params.dateFrom}
                  onChange={(d) => updateParam("dateFrom", d?.toISOString())}
                />
                <DatePicker
                  label="To date"
                  value={params.dateTo}
                  onChange={(d) => updateParam("dateTo", d?.toISOString())}
                />
              </div>
            </div>

            <Separator className="bg-white/5" />

            {/* Datasets Section */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-slate-500">
                <Database size={14} />
                <span className="text-[10px] font-bold uppercase tracking-[0.2em]">
                  Datasets
                </span>
              </div>
              <div className="space-y-3 pl-1">
                {DATASETS.map((dataset) => (
                  <div
                    key={dataset.id}
                    className="flex items-center space-x-3 group"
                  >
                    <Checkbox
                      id={dataset.id}
                      checked={params.datasets?.includes(dataset.id)}
                      onCheckedChange={() =>
                        updateParam(
                          "datasets",
                          toggleList(params.datasets, dataset.id)
                        )
                      }
                      className="border-slate-700 rounded-md data-[state=checked]:bg-indigo-600"
                    />
                    <Label
                      htmlFor={dataset.id}
                      className="text-[13px] text-slate-400 font-medium cursor-pointer group-hover:text-slate-100 transition-colors"
                    >
                      {dataset.name}
                    </Label>
                  </div>
                ))}
              </div>
            </div>

            <Separator className="bg-white/5" />

            {/* File Type Filter */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-slate-500">
                <FileCode size={14} />
                <span className="text-[10px] font-bold uppercase tracking-[0.2em]">
                  File Types
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {FILE_TYPES.map((ft) => (
                  <Badge
                    key={ft}
                    variant="outline"
                    onClick={() =>
                      updateParam("filetypes", toggleList(params.filetypes, ft))
                    }
                    className={cn(
                      "cursor-pointer px-3 py-1 text-[10px] font-bold transition-all",
                      params.filetypes?.includes(ft)
                        ? "bg-indigo-600 border-indigo-500 text-white shadow-[0_0_12px_rgba(79,70,229,0.4)]"
                        : "bg-slate-900/40 border-white/10 text-slate-400 hover:border-slate-400 hover:text-slate-100"
                    )}
                  >
                    {ft.toUpperCase()}
                  </Badge>
                ))}
              </div>
            </div>

            <Separator className="bg-white/5" />

            {/* Tags Section */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-slate-500">
                <Hash size={14} />
                <span className="text-[10px] font-bold uppercase tracking-[0.2em]">
                  Tags
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {AVAILABLE_TAGS.map((tag) => (
                  <button
                    type="button"
                    key={tag}
                    onClick={() =>
                      updateParam("tags", toggleList(params.tags, tag))
                    }
                    className={cn(
                      "text-[11px] px-3 py-1.5 rounded-lg border transition-all duration-200",
                      params.tags?.includes(tag)
                        ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-300"
                        : "bg-transparent border-white/5 text-slate-500 hover:text-slate-200 hover:border-white/10"
                    )}
                  >
                    #{tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Similarity Slider Footer */}
            <div className="pt-6 border-t border-white/10 space-y-5">
              <div className="flex items-center justify-between">
                <span
                  id="image-similarity-label"
                  className="text-[10px] font-black text-slate-400 uppercase tracking-[0.25em]"
                >
                  Similarity
                </span>

                <span
                  aria-hidden="true"
                  className="text-[11px] font-mono font-bold text-indigo-400 tabular-nums"
                >
                  {(localSimilarity * 100).toFixed(0)}%
                </span>
              </div>

              <Slider
                aria-labelledby="image-similarity-label"
                value={[localSimilarity]}
                min={0}
                max={1}
                step={0.01}
                onValueChange={([v]) => setLocalSimilarity(v)}
                onValueCommit={([v]) => updateParam("minSimilarity", v)}
                className="py-2"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
