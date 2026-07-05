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
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import { ArrowDown, ArrowUp, ChevronsUpDown, Filter } from "lucide-react";
import { useEffect, useState } from "react";
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
                "flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest transition-colors",
                isSorted ? "text-indigo-400" : "text-slate-500 hover:text-slate-300"
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
                <ChevronsUpDown size={12} className="text-slate-600" />
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="bg-popover border border-white/10">
            <DropdownMenuItem
              onClick={() => onSort?.(column.key, "asc")}
              className="gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-400 focus:text-indigo-300"
            >
              <ArrowUp size={12} /> Ascending
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => onSort?.(column.key, "desc")}
              className="gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-400 focus:text-indigo-300"
            >
              <ArrowDown size={12} /> Descending
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
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
                hasFilter ? "text-indigo-400" : "text-slate-600 hover:text-slate-300"
              )}
            >
              <Filter size={11} />
              {hasFilter && (
                <span className="absolute -top-1 -right-1 h-1.5 w-1.5 rounded-full bg-indigo-500" />
              )}
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-3 bg-popover border border-white/10" align="start">
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

/** Local-state-buffered text filter: commits to the parent on debounce or Enter, never on every keystroke. */
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
  const debounced = useDebounce(local, 400);

  useEffect(() => {
    onChange(debounced || undefined);
    // Only fire when the debounced value settles -- including onChange here
    // would re-run on every parent re-render, not just on value changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return (
    <Input
      autoFocus
      placeholder={placeholder}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          onChange(local || undefined);
        }
      }}
      className="h-9 text-xs bg-slate-900/40 border-white/10"
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
          className="h-9 text-xs bg-slate-900/40 border-white/10"
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
          className="h-9 text-xs bg-slate-900/40 border-white/10"
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
            className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer py-0.5"
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
        <div className="flex flex-wrap gap-1 pt-1.5 mt-1.5 border-t border-white/5">
          {selected.map((v) => (
            <Badge
              key={v}
              className="h-5 bg-indigo-500/10 text-indigo-300 border-none text-[10px] px-1.5"
            >
              {column.enumOptions?.find((o) => o.value === v)?.label ?? v}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
