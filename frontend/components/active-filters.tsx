"use client";

import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import type { ReactNode } from "react";

export interface ActiveFilter {
  key: string;
  label: string;
  icon?: ReactNode;
  onRemove: () => void;
}

/** One applied filter as a removable pill. */
export function FilterChip({ icon, label, onRemove }: Omit<ActiveFilter, "key">) {
  return (
    <span className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-muted/60 pl-2.5 pr-1 text-xs text-foreground [&_svg]:size-3.5 [&_svg]:text-muted-foreground">
      {icon}
      <span className="max-w-56 truncate">{label}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove filter ${label}`}
        className="rounded-full p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        <X />
      </button>
    </span>
  );
}

/** The applied filters as removable chips plus "Clear all"; renders nothing when none are set. */
export function ActiveFilters({ filters, onClearAll }: { filters: ActiveFilter[]; onClearAll: () => void }) {
  if (!filters.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {filters.map(({ key, ...chip }) => (
        <FilterChip key={key} {...chip} />
      ))}
      <Button
        variant="ghost"
        size="sm"
        onClick={onClearAll}
        className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground"
      >
        Clear all
      </Button>
    </div>
  );
}
