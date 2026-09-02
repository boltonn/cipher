"use client";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { COLOR_FIELDS } from "@/features/locations/lib/marker-style";
import { MAP_STYLES, useMapStyleStore } from "@/features/locations/style-store";
import { Check, SlidersHorizontal } from "lucide-react";

function OptionRow({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground"
    >
      {label}
      {active && <Check className="size-3.5 text-primary" />}
    </button>
  );
}

export function MapControls() {
  const { styleId, setStyleId, colorField, setColorField } = useMapStyleStore();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="secondary" size="icon" className="size-9 shadow-md" aria-label="Map options">
          <SlidersHorizontal className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent side="top" align="start" className="w-44 p-1">
        <p className="px-2 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Basemap
        </p>
        {MAP_STYLES.map((s) => (
          <OptionRow key={s.id} label={s.label} active={s.id === styleId} onClick={() => setStyleId(s.id)} />
        ))}
        <div className="my-1 border-t" />
        <p className="px-2 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Colour points by
        </p>
        {COLOR_FIELDS.map((f) => (
          <OptionRow
            key={f.id}
            label={f.label}
            active={f.id === colorField}
            onClick={() => setColorField(f.id)}
          />
        ))}
      </PopoverContent>
    </Popover>
  );
}
