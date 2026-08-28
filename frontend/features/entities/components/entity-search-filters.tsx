"use client";

import { DatePicker } from "@/components/date-picker";
import { TagsInput } from "@/components/tags-input";
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
import { Switch } from "@/components/ui/switch";
import { SELECTOR_KINDS, type EntityType, type SelectorKind } from "@/features/entities/types";
import { CalendarRange, RotateCcw, X } from "lucide-react";
import { useState } from "react";

export interface EntityFilters {
  entityType?: EntityType;
  selectorKind?: SelectorKind;
  isVerified?: boolean;
  tags: string[];
  country?: string;
  orgType?: string;
  dobFrom?: string;
  dobTo?: string;
  /** exact selector value lookup -- switches the table into single-lookup mode */
  selectorValue?: string;
}

export const EMPTY_ENTITY_FILTERS: EntityFilters = { tags: [] };

const ALL = "__all__";

/** Filters that only make sense once an entity type is chosen. */
function hasTypeScopedFilter(f: EntityFilters) {
  return (
    !!f.selectorKind ||
    !!f.selectorValue ||
    !!f.country ||
    !!f.orgType ||
    !!f.dobFrom ||
    !!f.dobTo
  );
}

/** Any refinement beyond the bare entity-type scope. */
export function entityRefinementsActive(f: EntityFilters) {
  return f.isVerified != null || f.tags.length > 0 || hasTypeScopedFilter(f);
}

export function entityFiltersActive(f: EntityFilters) {
  return !!f.entityType || entityRefinementsActive(f);
}

interface EntitySearchFiltersProps {
  value: EntityFilters;
  onChange: (next: EntityFilters) => void;
}

/**
 * The row of refinements under the search bar. The entity-type scope lives in
 * the search bar itself; this bar shows the shared filters plus whichever
 * type-specific fields apply, so the controls on screen always match what the
 * chosen type can actually be filtered by.
 */
export function EntitySearchFilters({ value, onChange }: EntitySearchFiltersProps) {
  const set = (patch: Partial<EntityFilters>) => onChange({ ...value, ...patch });
  const type = value.entityType;

  return (
    <div className="rounded-xl border border-border/60 bg-muted/20 px-4 py-3">
      <div className="flex flex-wrap items-end gap-x-3 gap-y-3">
        <Field label="Tags" className="w-56">
          <TagsInput value={value.tags} onChange={(tags) => set({ tags })} />
        </Field>

        {type === "person" && (
          <DobField from={value.dobFrom} to={value.dobTo} onChange={set} />
        )}

        {type === "organization" && (
          <>
            <Field label="Org type" className="w-40">
              <Input
                value={value.orgType ?? ""}
                onChange={(e) => set({ orgType: e.target.value || undefined })}
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
          <>
            <Field label="Selector kind" className="w-44">
              <Select
                value={value.selectorKind ?? ALL}
                onValueChange={(v) =>
                  set({ selectorKind: v === ALL ? undefined : (v as SelectorKind) })
                }
              >
                <SelectTrigger className="h-9 w-full bg-muted/40 text-xs">
                  <SelectValue placeholder="Any kind" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL} className="text-xs">
                    Any kind
                  </SelectItem>
                  {SELECTOR_KINDS.map((k) => (
                    <SelectItem key={k} value={k} className="text-xs capitalize">
                      {k.replace(/_/g, " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Exact value" className="w-52" hint="jumps straight to the owner">
              <Input
                value={value.selectorValue ?? ""}
                onChange={(e) => set({ selectorValue: e.target.value || undefined })}
                placeholder="+15551234567"
                className="h-9 bg-muted/40 text-xs"
              />
            </Field>
          </>
        )}

        <div className="flex items-center gap-4 self-end pb-1.5 pl-1">
          <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap">
            <Switch
              checked={value.isVerified === true}
              onCheckedChange={(c) => set({ isVerified: c ? true : undefined })}
            />
            <span className="text-[11px] text-muted-foreground">Verified only</span>
          </label>
          {entityFiltersActive(value) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onChange({ ...EMPTY_ENTITY_FILTERS })}
              className="h-7 gap-1.5 px-2 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <RotateCcw size={12} /> Reset
            </Button>
          )}
        </div>
      </div>
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
      <Label className="mb-1.5 flex items-baseline gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
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
