"use client";

import { DatePicker } from "@/components/date-picker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  SELECTOR_TYPES,
  type EntityType,
  type SelectorSubtype,
  type SelectorType,
} from "@/features/entities/types";
import { CalendarRange, RotateCcw, X } from "lucide-react";
import { useState } from "react";

export interface EntityFilters {
  entityType?: EntityType;
  selectorType?: SelectorType;
  /** set via a deep link from the dataset breakdown; no dropdown for it yet */
  selectorSubtype?: SelectorSubtype;
  country?: string;
  category?: string;
  dobFrom?: string;
  dobTo?: string;
}

export const EMPTY_ENTITY_FILTERS: EntityFilters = {};

const ALL = "__all__";

/** Filters that only make sense once an entity type is chosen. */
function hasTypeScopedFilter(f: EntityFilters) {
  return (
    !!f.selectorType ||
    !!f.selectorSubtype ||
    !!f.country ||
    !!f.category ||
    !!f.dobFrom ||
    !!f.dobTo
  );
}

/** Any refinement beyond the bare entity-type scope. */
export function entityRefinementsActive(f: EntityFilters) {
  return hasTypeScopedFilter(f);
}

export function entityFiltersActive(f: EntityFilters) {
  return !!f.entityType || entityRefinementsActive(f);
}

interface EntitySearchFiltersProps {
  value: EntityFilters;
  onChange: (next: EntityFilters) => void;
  /** true when a text query is also active; makes the Clear button show */
  queryActive?: boolean;
  /** clears filters AND the text query */
  onClear?: () => void;
}

/**
 * The row of refinements under the search bar. The entity-type scope lives in
 * the search bar itself; this bar shows whichever type-specific fields apply,
 * so the controls on screen always match what the chosen type can be filtered
 * by. A "Clear filters" action appears only once a query or filter is set.
 */
export function EntitySearchFilters({
  value,
  onChange,
  queryActive,
  onClear,
}: EntitySearchFiltersProps) {
  const set = (patch: Partial<EntityFilters>) =>
    onChange({ ...value, ...patch });
  const type = value.entityType;
  const showClear = queryActive || entityFiltersActive(value);
  const hasTypeControls =
    type === "person" ||
    type === "organization" ||
    type === "location" ||
    type === "selector";

  if (!showClear && !hasTypeControls) return null;

  return (
    <div className="flex flex-wrap items-end gap-x-3 gap-y-3 rounded-xl border border-border/60 bg-muted/20 px-4 py-3">
      {type === "person" && (
        <DobField from={value.dobFrom} to={value.dobTo} onChange={set} />
      )}

      {type === "organization" && (
        <>
          <Field label="Category" className="w-40">
            <Input
              value={value.category ?? ""}
              onChange={(e) => set({ category: e.target.value || undefined })}
              placeholder="e.g. company"
              className="h-9 bg-muted/40 text-xs"
            />
          </Field>
          <Field label="Country" className="w-28">
            <Input
              value={value.country ?? ""}
              onChange={(e) => set({ country: e.target.value || undefined })}
              placeholder="US"
              className="h-9 bg-muted/40 text-xs"
            />
          </Field>
        </>
      )}

      {type === "location" && (
        <Field label="Country" className="w-28">
          <Input
            value={value.country ?? ""}
            onChange={(e) => set({ country: e.target.value || undefined })}
            placeholder="US"
            className="h-9 bg-muted/40 text-xs"
          />
        </Field>
      )}

      {type === "selector" && (
        <Field label="Selector kind" className="w-44">
          <Select
            value={value.selectorType ?? ALL}
            onValueChange={(v) =>
              set({ selectorType: v === ALL ? undefined : (v as SelectorType) })
            }
          >
            <SelectTrigger className="h-9 w-full bg-muted/40 text-xs">
              <SelectValue placeholder="Any kind" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL} className="text-xs">
                Any kind
              </SelectItem>
              {SELECTOR_TYPES.map((k) => (
                <SelectItem key={k} value={k} className="text-xs capitalize">
                  {k.replace(/_/g, " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}

      {showClear && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            onClear ? onClear() : onChange({ ...EMPTY_ENTITY_FILTERS })
          }
          className="h-9 gap-1.5 self-end px-2 text-[11px] text-muted-foreground hover:text-foreground"
        >
          <RotateCcw size={12} /> Clear filters
        </Button>
      )}
    </div>
  );
}

/**
 * Date-of-birth filter. Starts as a single "on or after" date; the analyst can
 * add an upper bound to turn it into a range.
 */
function DobField({
  from,
  to,
  onChange,
}: {
  from?: string;
  to?: string;
  onChange: (patch: Partial<EntityFilters>) => void;
}) {
  const [expanded, setExpanded] = useState(!!to);
  const [prevTo, setPrevTo] = useState(to);
  if (to !== prevTo) {
    setPrevTo(to);
    if (to) setExpanded(true);
  }
  const range = expanded || !!to;

  return (
    <div className="flex items-end gap-2">
      <Field label={range ? "Born from" : "Date of birth"} className="w-40">
        <DatePicker value={from} onChange={(d) => onChange({ dobFrom: d })} />
      </Field>
      {range ? (
        <>
          <Field label="Born to" className="w-40">
            <DatePicker value={to} onChange={(d) => onChange({ dobTo: d })} />
          </Field>
          <button
            type="button"
            aria-label="Remove end date"
            onClick={() => {
              setExpanded(false);
              onChange({ dobTo: undefined });
            }}
            className="mb-2.5 text-muted-foreground hover:text-foreground"
          >
            <X size={14} />
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mb-0.5 flex h-9 items-center gap-1.5 whitespace-nowrap rounded-md border border-dashed border-border/60 px-2.5 text-[11px] text-muted-foreground transition-colors hover:border-border hover:text-foreground"
        >
          <CalendarRange size={13} /> Range
        </button>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <Label className="mb-1.5 flex items-baseline gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
        {hint && (
          <span className="font-normal normal-case tracking-normal text-muted-foreground/60">
            {hint}
          </span>
        )}
      </Label>
      {children}
    </div>
  );
}
