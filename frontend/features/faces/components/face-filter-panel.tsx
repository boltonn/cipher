"use client";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { FaceFilters } from "@/features/faces/hooks/use-search-controller";
import { DEFAULT_MIN_SIMILARITY } from "@/features/faces/types";
import { PersonMultiSelectCombobox } from "@/features/persons/components/person-multi-select-combobox";
import { cn } from "@/lib/utils";
import { Filter, X } from "lucide-react";
import React, { useState } from "react";

const DEFAULT_MIN_SIZE = 0;
const DEFAULT_MIN_QUALITY = 0;

export function hasActiveFaceFilters(params: FaceFilters): boolean {
  return !!(
    params.unassignedOnly ||
    params.representativeOnly ||
    params.rejectedOnly ||
    params.personIds?.length ||
    (params.minSize ?? DEFAULT_MIN_SIZE) !== DEFAULT_MIN_SIZE ||
    (params.minQuality ?? DEFAULT_MIN_QUALITY) !== DEFAULT_MIN_QUALITY ||
    (params.minSimilarity ?? DEFAULT_MIN_SIMILARITY) !== DEFAULT_MIN_SIMILARITY
  );
}

interface FaceFilterPanelProps {
  params: FaceFilters;
  setParams: React.Dispatch<React.SetStateAction<FaceFilters>>;
  isSimilarityMode: boolean;
  className?: string;
}

/** Filter controls content -- rendered inside a Popover triggered from the search bar. */
export const FaceFilterPanel: React.FC<FaceFilterPanelProps> = ({
  params,
  setParams,
  isSimilarityMode,
  className,
}) => {
  const [prevMinSimilarity, setPrevMinSimilarity] = useState(
    params.minSimilarity
  );
  const [localSimilarity, setLocalSimilarity] = useState(
    params.minSimilarity ?? DEFAULT_MIN_SIMILARITY
  );
  if (params.minSimilarity !== prevMinSimilarity) {
    setPrevMinSimilarity(params.minSimilarity);
    setLocalSimilarity(params.minSimilarity ?? DEFAULT_MIN_SIMILARITY);
  }

  const [prevMinSize, setPrevMinSize] = useState(params.minSize);
  const [localMinSize, setLocalMinSize] = useState(
    params.minSize ?? DEFAULT_MIN_SIZE
  );
  if (params.minSize !== prevMinSize) {
    setPrevMinSize(params.minSize);
    setLocalMinSize(params.minSize ?? DEFAULT_MIN_SIZE);
  }

  const [prevMinQuality, setPrevMinQuality] = useState(params.minQuality);
  const [localMinQuality, setLocalMinQuality] = useState(
    params.minQuality ?? DEFAULT_MIN_QUALITY
  );
  if (params.minQuality !== prevMinQuality) {
    setPrevMinQuality(params.minQuality);
    setLocalMinQuality(params.minQuality ?? DEFAULT_MIN_QUALITY);
  }

  const hasActiveFilters = hasActiveFaceFilters(params);

  const updateParam = <K extends keyof FaceFilters>(
    key: K,
    value: FaceFilters[K]
  ) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  };

  const clearAllFilters = () => {
    setParams({
      limit: params.limit,
      sortBy: "dateCreated",
      sortOrder: "desc",
      minSimilarity: DEFAULT_MIN_SIMILARITY,
      minSize: DEFAULT_MIN_SIZE,
      minQuality: DEFAULT_MIN_QUALITY,
      personIds: undefined,
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
          <h3 className="text-[11px] font-semibold uppercase tracking-wide">
            Filters
          </h3>
        </div>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={clearAllFilters}
            className="text-xs font-medium text-destructive/70 hover:text-destructive flex items-center gap-1 transition-colors"
          >
            <X size={11} /> Reset
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-x-8 gap-y-6">
        {/* Identity */}
        <div className="flex flex-col gap-3 xl:col-span-2 min-w-0">
          <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
            Identity
          </span>
          <div className="space-y-1.5">
            <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Person (includes potential matches)
            </Label>
            <PersonMultiSelectCombobox
              value={params.personIds ?? []}
              onChange={(personIds) =>
                updateParam(
                  "personIds",
                  personIds.length ? personIds : undefined
                )
              }
            />
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-1">
            <div className="flex items-center gap-2">
              <Switch
                id="unassigned-only"
                checked={!!params.unassignedOnly}
                onCheckedChange={(v) => updateParam("unassignedOnly", v)}
              />
              <Label
                htmlFor="unassigned-only"
                className="text-[13px] text-foreground font-medium"
              >
                Unassigned only
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="representative-only"
                checked={!!params.representativeOnly}
                onCheckedChange={(v) => updateParam("representativeOnly", v)}
              />
              <Label
                htmlFor="representative-only"
                className="text-[13px] text-foreground font-medium"
              >
                Representative
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="rejected-only"
                checked={!!params.rejectedOnly}
                onCheckedChange={(v) => updateParam("rejectedOnly", v)}
              />
              <Label
                htmlFor="rejected-only"
                className="text-[13px] text-foreground font-medium"
              >
                Not a face
              </Label>
            </div>
          </div>
        </div>

        {/* Sort */}
        <div className="flex flex-col gap-3 min-w-0">
          <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
            Sort
          </span>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5 min-w-0">
              <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Sort By
              </Label>
              <Select
                value={params.sortBy || "dateCreated"}
                onValueChange={(v) =>
                  updateParam("sortBy", v as FaceFilters["sortBy"])
                }
              >
                <SelectTrigger className="w-full bg-muted/40 border-border text-xs h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="dateCreated">Date detected</SelectItem>
                  <SelectItem value="detectionConfidence">
                    Confidence
                  </SelectItem>
                  <SelectItem value="qualityScore">Quality</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5 min-w-0">
              <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Order
              </Label>
              <Select
                value={params.sortOrder || "desc"}
                onValueChange={(v) =>
                  updateParam("sortOrder", v as FaceFilters["sortOrder"])
                }
              >
                <SelectTrigger className="w-full bg-muted/40 border-border text-xs h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="desc">Descending</SelectItem>
                  <SelectItem value="asc">Ascending</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        {/* Thresholds */}
        <div className="flex flex-col gap-5 min-w-0">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <span
                id="face-similarity-label"
                className={cn(
                  "text-[11px] font-bold uppercase tracking-wide truncate",
                  isSimilarityMode ? "text-annotation" : "text-muted-foreground"
                )}
              >
                Min Similarity
              </span>
              <span
                aria-hidden="true"
                className="text-[11px] font-mono font-bold text-annotation tabular-nums shrink-0"
              >
                {(localSimilarity * 100).toFixed(0)}%
              </span>
            </div>
            <Slider
              aria-labelledby="face-similarity-label"
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
              <span className="text-[11px] text-muted-foreground italic">
                Only applies to similarity searches
              </span>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <span
                id="face-min-size-label"
                className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground truncate"
              >
                Min Resolution
              </span>
              <span
                aria-hidden="true"
                className="text-[11px] font-mono font-bold text-primary tabular-nums shrink-0"
              >
                {localMinSize}px
              </span>
            </div>
            <Slider
              aria-labelledby="face-min-size-label"
              value={[localMinSize]}
              min={0}
              max={500}
              step={10}
              onValueChange={([v]) => setLocalMinSize(v)}
              onValueCommit={([v]) => updateParam("minSize", v || undefined)}
              className="py-2"
            />
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <span
                id="face-min-quality-label"
                className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground truncate"
              >
                Min Quality
              </span>
              <span
                aria-hidden="true"
                className="text-[11px] font-mono font-bold text-primary tabular-nums shrink-0"
              >
                {(localMinQuality * 100).toFixed(0)}%
              </span>
            </div>
            <Slider
              aria-labelledby="face-min-quality-label"
              value={[localMinQuality]}
              min={0}
              max={1}
              step={0.05}
              onValueChange={([v]) => setLocalMinQuality(v)}
              onValueCommit={([v]) => updateParam("minQuality", v || undefined)}
              className="py-2"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
