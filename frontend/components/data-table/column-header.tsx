"use client";

import { DateRangePicker } from "@/components/date-range-picker";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { ArrowDown, ArrowUp, ChevronsUpDown, Filter } from "lucide-react";
import { useState } from "react";
import type {
  DataTableColumn,
  DataTableFilterValue,
  DataTableSortOrder,
} from "./types";

interface DataTableColumnHeaderProps<T> {
  column: DataTableColumn<T>;
  sortBy?: string;
  sortOrder?: DataTableSortOrder;
  onSort?: (key: string, order: DataTableSortOrder) => void;
  filterValue: DataTableFilterValue;
  onFilterChange: (key: string, value: DataTableFilterValue) => void;
}

export function DataTableColumnHeader<T>({
  column,
  sortBy,
  sortOrder,
  onSort,
  filterValue,
  onFilterChange,
}: DataTableColumnHeaderProps<T>) {
  const isSorted = sortBy === column.key;
  const hasFilter = isFilterActive(filterValue);

  return (
    <div
      className={cn(
        "flex items-center gap-1",
        column.align === "right" && "justify-end"
      )}
    >
      {column.sortable ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className={cn(
                "flex items-center gap-1.5 text-xs font-medium transition-colors",
                isSorted ? "text-primary" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {column.header}
              {isSorted ? (
                sortOrder === "asc" ? (
                  <ArrowUp size={12} />
                ) : (
                  <ArrowDown size={12} />
                )
              ) : (
                <ChevronsUpDown size={12} className="text-muted-foreground" />
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="bg-popover border border-border">
            <DropdownMenuItem
              onClick={() => onSort?.(column.key, "asc")}
              className="gap-2 text-xs text-muted-foreground focus:text-foreground"
            >
              <ArrowUp size={12} /> Ascending
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => onSort?.(column.key, "desc")}
              className="gap-2 text-xs text-muted-foreground focus:text-foreground"
            >
              <ArrowDown size={12} /> Descending
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
          {column.header}
        </span>
      )}

      {column.filterable && (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={`Filter ${column.header}`}
              className={cn(
                "relative h-4 w-4 flex items-center justify-center rounded transition-colors",
                hasFilter ? "text-primary" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Filter size={11} />
              {hasFilter && (
                <span className="absolute -top-1 -right-1 h-1.5 w-1.5 rounded-full bg-primary" />
              )}
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-3 bg-popover border border-border" align="start">
            <ColumnFilterControl
              column={column}
              value={filterValue}
              onChange={(value) => onFilterChange(column.key, value)}
            />
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}

/** Local-state-buffered text filter: commits to the parent on Enter or blur, never on every keystroke. */
function TextFilterInput({
  placeholder,
  value,
  onChange,
}: {
  placeholder: string;
  value: string | undefined;
  onChange: (value: string | undefined) => void;
}) {
  const [local, setLocal] = useState(value ?? "");
  const [lastValue, setLastValue] = useState(value ?? "");

  // Adopt an externally-cleared value (clear-all filters) without an effect.
  if ((value ?? "") !== lastValue) {
    setLastValue(value ?? "");
    setLocal(value ?? "");
  }

  const commit = () => onChange(local.trim() || undefined);

  return (
    <Input
      autoFocus
      placeholder={placeholder}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        }
      }}
      className="h-9 text-xs bg-muted/40 border-border"
    />
  );
}

export function isFilterActive(value: DataTableFilterValue): boolean {
  if (value == null) return false;
  if (typeof value === "string") return value.length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if ("from" in value || "to" in value) return !!(value.from || value.to);
  if ("min" in value || "max" in value) return value.min != null || value.max != null;
  return false;
}

function ColumnFilterControl<T>({
  column,
  value,
  onChange,
}: {
  column: DataTableColumn<T>;
  value: DataTableFilterValue;
  onChange: (value: DataTableFilterValue) => void;
}) {
  if (column.type === "text") {
    return (
      <TextFilterInput
        placeholder={`Search ${column.header.toLowerCase()}...`}
        value={value as string | undefined}
        onChange={onChange}
      />
    );
  }

  if (column.type === "date") {
    const range = (value as { from?: string; to?: string }) ?? {};
    return (
      <DateRangePicker
        value={range}
        onChange={(next) => onChange(next.from || next.to ? next : undefined)}
        className="h-9"
      />
    );
  }

  if (column.type === "number") {
    const range = (value as { min?: number; max?: number }) ?? {};
    return (
      <div className="grid grid-cols-2 gap-2">
        <Input
          type="number"
          placeholder="Min"
          value={range.min ?? ""}
          onChange={(e) => {
            const min = e.target.value ? Number(e.target.value) : undefined;
            const next = { ...range, min };
            onChange(next.min == null && next.max == null ? undefined : next);
          }}
          className="h-9 text-xs bg-muted/40 border-border"
        />
        <Input
          type="number"
          placeholder="Max"
          value={range.max ?? ""}
          onChange={(e) => {
            const max = e.target.value ? Number(e.target.value) : undefined;
            const next = { ...range, max };
            onChange(next.min == null && next.max == null ? undefined : next);
          }}
          className="h-9 text-xs bg-muted/40 border-border"
        />
      </div>
    );
  }

  // enum
  const selected = (value as string[]) ?? [];
  return (
    <div className="flex flex-col gap-1.5 max-h-56 overflow-y-auto">
      {column.enumOptions?.map((option) => {
        const checked = selected.includes(option.value);
        return (
          <label
            key={option.value}
            className="flex items-center gap-2 text-xs text-foreground cursor-pointer py-0.5"
          >
            <Checkbox
              checked={checked}
              onCheckedChange={(next) => {
                const nextSelected = next
                  ? [...selected, option.value]
                  : selected.filter((v) => v !== option.value);
                onChange(nextSelected.length ? nextSelected : undefined);
              }}
            />
            {option.label}
          </label>
        );
      })}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-1.5 mt-1.5 border-t border-border/50">
          {selected.map((v) => (
            <Badge
              key={v}
              className="h-5 bg-primary/10 text-primary border-none text-[11px] px-1.5"
            >
              {column.enumOptions?.find((o) => o.value === v)?.label ?? v}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
