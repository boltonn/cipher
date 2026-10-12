"use client";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { FIELD_GROUP_LABELS, fieldIcon } from "@/features/tables/lib/field-meta";
import type { ColumnDecision, FieldTypeOption } from "@/features/tables/types";
import { cn } from "@/lib/utils";
import { Check, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";

interface ColumnMappingPopoverProps {
  column: ColumnDecision;
  fieldTypes: FieldTypeOption[];
  busy: boolean;
  onApply: (fieldType: string, role: string) => void;
  children: React.ReactNode;
}

const percent = (value: number) => `${Math.round(value * 100)}%`;

/**
 * Retype a column and set whose it is -- the table counterpart of the mention popover.
 * Whatever is applied here is locked; the rest of the mapping is re-checked around it.
 */
export function ColumnMappingPopover({ column, fieldTypes, busy, onApply, children }: ColumnMappingPopoverProps) {
  const [open, setOpen] = useState(false);
  const [fieldType, setFieldType] = useState(column.fieldType);
  const [role, setRole] = useState(column.role ?? "");
  const labels = new Map(fieldTypes.map((f) => [f.id, f.label]));
  const groups = Object.keys(FIELD_GROUP_LABELS).filter((g) => fieldTypes.some((f) => f.group === g));
  const changed = fieldType !== column.fieldType || role.trim() !== (column.role ?? "");

  const reset = (next: boolean) => {
    if (next) {
      setFieldType(column.fieldType);
      setRole(column.role ?? "");
    }
    setOpen(next);
  };

  return (
    <Popover open={open} onOpenChange={reset}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        align="start"
        side="bottom"
        sideOffset={8}
        collisionPadding={12}
        className="w-80 gap-0 p-3"
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <div className="space-y-0.5">
          <p className="truncate text-xs">
            <span className="text-muted-foreground">Column</span>{" "}
            <span className="font-mono text-foreground">“{column.header}”</span>
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {column.examples.slice(0, 3).join(" · ") || "No values in the sample"}
          </p>
        </div>

        <Command className="mt-3 rounded-md border border-border/60 bg-transparent">
          <CommandInput placeholder="Search column types…" className="text-xs" />
          <CommandList className="max-h-48">
            <CommandEmpty className="py-3 text-[11px] text-muted-foreground">No matching type.</CommandEmpty>
            {groups.map((group) => (
              <CommandGroup key={group} heading={FIELD_GROUP_LABELS[group]}>
                {fieldTypes
                  .filter((f) => f.group === group)
                  .map((f) => {
                    const Icon = fieldIcon(f);
                    return (
                      <CommandItem
                        key={f.id}
                        value={`${f.label} ${f.id}`}
                        onSelect={() => setFieldType(f.id)}
                        title={f.description}
                        className="gap-2 text-xs"
                      >
                        <Icon size={12} className="shrink-0 text-muted-foreground" />
                        <span className="truncate">{f.label}</span>
                        {f.needsOntology && (
                          <span className="ml-auto text-[11px] text-muted-foreground">not emitted</span>
                        )}
                        {f.id === fieldType && <Check size={12} className="ml-auto shrink-0 text-primary" />}
                      </CommandItem>
                    );
                  })}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>

        {column.evidence.length > 0 && (
          <div className="mt-3">
            <p className="mb-1 flex items-center gap-1 text-[11px] font-medium text-annotation">
              <Sparkles size={11} /> Detected
            </p>
            <ul className="space-y-0.5 text-[11px]">
              {column.evidence.map((e) => (
                <li key={e.detector} className="flex gap-2">
                  <span className="w-16 shrink-0 text-muted-foreground">{e.detector}</span>
                  <span className="truncate">
                    {Object.entries(e.scores)
                      .slice(0, 2)
                      .map(([id, score]) => `${labels.get(id) ?? id} ${percent(score)}`)
                      .join(" · ") || e.note}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {column.hitRate != null && (
          <p className={cn("mt-2 text-[11px]", column.hitRate < 0.8 ? "text-destructive" : "text-muted-foreground")}>
            {percent(column.hitRate)} of sampled cells fit {labels.get(column.fieldType)?.toLowerCase()}
            {column.failingExamples.length > 0 && (
              <span className="block truncate font-mono text-muted-foreground">
                e.g. {column.failingExamples.slice(0, 3).join(" · ")}
              </span>
            )}
          </p>
        )}

        <label className="mt-3 block text-[11px] text-muted-foreground">
          Whose column — columns sharing a role make one entity per row
          <Input
            value={role}
            onChange={(e) => setRole(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && changed && onApply(fieldType, role)}
            placeholder="main party (e.g. sender, receiver)"
            className="mt-1 h-8 bg-muted/40 text-xs"
          />
        </label>

        <div className="mt-3 flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)} className="h-8 flex-1 text-xs">
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={busy || !changed}
            onClick={() => {
              onApply(fieldType, role);
              setOpen(false);
            }}
            className="h-8 flex-1 gap-1.5 text-xs"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            Apply
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
