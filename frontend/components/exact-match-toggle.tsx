"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { useId } from "react";

interface ExactMatchToggleProps {
  value: boolean;
  onChange: (value: boolean) => void;
}

/** Search-bar checkbox: only results containing the query's words, in that order. */
export function ExactMatchToggle({ value, onChange }: ExactMatchToggleProps) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      title="Exact phrase: only results containing these words, in this order"
      className="flex h-7 shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:text-foreground"
    >
      <Checkbox id={id} checked={value} onCheckedChange={(checked) => onChange(checked === true)} />
      Exact match
    </label>
  );
}
