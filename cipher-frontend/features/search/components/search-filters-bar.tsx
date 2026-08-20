"use client";

import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { cn } from "@/lib/utils";
import { FileText, Mail } from "lucide-react";
import type { SearchFilters, SearchFiletypeGroup } from "../types";

interface SearchFiltersBarProps {
  filters: SearchFilters;
  onFiltersChange: (filters: SearchFilters) => void;
}

const TYPE_OPTIONS: { value: SearchFiletypeGroup | undefined; label: string; Icon?: typeof FileText }[] = [
  { value: undefined, label: "All" },
  { value: "document", label: "Documents", Icon: FileText },
  { value: "email", label: "Emails", Icon: Mail },
];

/** Dataset + content-type filters for chunk search -- makes what's being searched visible. */
export function SearchFiltersBar({ filters, onFiltersChange }: SearchFiltersBarProps) {
  return (
    <div className="flex shrink-0 items-center gap-3 px-1">
      <DatasetSelect
        datasetId={filters.datasetId}
        onChange={(datasetId) => onFiltersChange({ ...filters, datasetId })}
      />

      <div className="flex items-center gap-0.5">
        {TYPE_OPTIONS.map(({ value, label, Icon }) => (
          <button
            key={label}
            type="button"
            onClick={() => onFiltersChange({ ...filters, filetypeGroup: value })}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors",
              filters.filetypeGroup === value
                ? "bg-indigo-500/10 text-indigo-300"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            {Icon && <Icon className="h-3 w-3 shrink-0" />}
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
