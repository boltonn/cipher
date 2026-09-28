"use client";

import { EntityPicker } from "@/features/entities/components/entity-picker";
import { useEntity } from "@/features/entities/hooks/use-entities";
import { SELECTOR_TYPE_LABELS } from "@/features/entities/types";
import type { SelectorType } from "@/features/entities/types";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { cn } from "@/lib/utils";
import { FileText, Mail, X } from "lucide-react";
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

/** Dataset + content-type + entity filters for chunk search -- makes what's being searched visible. */
export function SearchFiltersBar({ filters, onFiltersChange }: SearchFiltersBarProps) {
  const entityId = filters.entityIds?.[0];
  const { data: entity } = useEntity(entityId);
  const selectorType = filters.selectorTypes?.[0] as SelectorType | undefined;

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-3 px-1">
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
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {Icon && <Icon className="h-3 w-3 shrink-0" />}
            {label}
          </button>
        ))}
      </div>

      {/* Entity filter -- composes with text/semantic/hybrid; needs `sync-chunk-entities`. */}
      {entityId ? (
        <span className="flex h-7 items-center gap-1.5 rounded-md bg-annotation/10 px-2 text-xs font-medium text-annotation">
          {entity?.displayName ?? "Entity"}
          <button
            type="button"
            aria-label="Clear entity filter"
            onClick={() => onFiltersChange({ ...filters, entityIds: undefined })}
            className="rounded-sm hover:bg-annotation/20"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ) : (
        <EntityPicker
          datasetId={filters.datasetId}
          placeholder="Filter by entity…"
          className="h-7 w-48"
          onSelect={(id) => onFiltersChange({ ...filters, entityIds: [id] })}
        />
      )}

      {selectorType && (
        <span className="flex h-7 items-center gap-1.5 rounded-md bg-muted px-2 text-xs font-medium text-muted-foreground">
          {SELECTOR_TYPE_LABELS[selectorType] ?? selectorType}
          <button
            type="button"
            aria-label="Clear selector-type filter"
            onClick={() => onFiltersChange({ ...filters, selectorTypes: undefined })}
            className="rounded-sm hover:bg-foreground/10"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      )}
    </div>
  );
}
