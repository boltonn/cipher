"use client";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { EdgeBinding, EntitySlot, RelationshipVerbOption } from "@/features/tables/types";
import { ArrowRight, Check, Loader2 } from "lucide-react";
import { useState } from "react";
import { humanize } from "@/lib/utils";

export const verbLabel = (verb: string) => {
  const text = humanize(verb);
  return text.charAt(0).toUpperCase() + text.slice(1);
};

interface RelationshipPopoverProps {
  slots: EntitySlot[];
  verbs: RelationshipVerbOption[];
  /** The relationship being edited; absent = adding one. */
  edge?: EdgeBinding;
  busy: boolean;
  onApply: (value: { srcSlot: string; verb: string; dstSlot: string; isEnabled: boolean }) => void;
  children: React.ReactNode;
}

function SlotSelect({ value, slots, onChange }: { value: string; slots: EntitySlot[]; onChange: (v: string) => void }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-8 w-full min-w-0 bg-muted/40 text-xs">
        <SelectValue placeholder="Entity" />
      </SelectTrigger>
      <SelectContent>
        {slots.map((s) => (
          <SelectItem key={s.name} value={s.name} className="text-xs">
            {s.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** What each row says between two of its entities -- e.g. sender → paid → receiver. */
export function RelationshipPopover({ slots, verbs, edge, busy, onApply, children }: RelationshipPopoverProps) {
  const [open, setOpen] = useState(false);
  const [srcSlot, setSrcSlot] = useState(edge?.srcSlot ?? "");
  const [dstSlot, setDstSlot] = useState(edge?.dstSlot ?? "");
  const [verb, setVerb] = useState(edge?.relationshipType ?? "locatedIn");
  const [isEnabled, setIsEnabled] = useState(edge?.isEnabled ?? true);
  const ontology = verbs.filter((v) => !v.isProposed);
  const proposed = verbs.filter((v) => v.isProposed);
  const valid = !!srcSlot && !!dstSlot && srcSlot !== dstSlot;

  const reset = (next: boolean) => {
    if (next) {
      setSrcSlot(edge?.srcSlot ?? "");
      setDstSlot(edge?.dstSlot ?? "");
      setVerb(edge?.relationshipType ?? "locatedIn");
      setIsEnabled(edge?.isEnabled ?? true);
    }
    setOpen(next);
  };

  return (
    <Popover open={open} onOpenChange={reset}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent align="start" sideOffset={8} collisionPadding={12} className="w-80 gap-0 p-3">
        <p className="text-xs text-muted-foreground">{edge ? "Relationship on every row" : "New relationship on every row"}</p>

        <div className="mt-2 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
          {edge ? (
            <span className="truncate text-xs font-medium">{edge.srcSlot}</span>
          ) : (
            <SlotSelect value={srcSlot} slots={slots} onChange={setSrcSlot} />
          )}
          <ArrowRight size={12} className="text-muted-foreground" />
          {edge ? (
            <span className="truncate text-xs font-medium">{edge.dstSlot}</span>
          ) : (
            <SlotSelect value={dstSlot} slots={slots} onChange={setDstSlot} />
          )}
        </div>

        <Select value={verb} onValueChange={setVerb}>
          <SelectTrigger className="mt-2 h-8 w-full bg-muted/40 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ontology.map((v) => (
              <SelectItem key={v.verb} value={v.verb} className="text-xs" title={v.description}>
                {verbLabel(v.verb)}
              </SelectItem>
            ))}
            {proposed.length > 0 && (
              <>
                <SelectSeparator />
                <SelectGroup>
                  <SelectLabel className="text-[11px]">Not in the ontology yet — not emitted</SelectLabel>
                  {proposed.map((v) => (
                    <SelectItem key={v.verb} value={v.verb} className="text-xs" title={v.description}>
                      {verbLabel(v.verb)}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </>
            )}
          </SelectContent>
        </Select>
        <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">
          {verbs.find((v) => v.verb === verb)?.description}
        </p>

        {edge && (
          <label className="mt-3 flex items-center justify-between text-xs">
            Emit this relationship
            <Switch checked={isEnabled} onCheckedChange={setIsEnabled} />
          </label>
        )}

        <div className="mt-3 flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)} className="h-8 flex-1 text-xs">
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={busy || !(edge || valid)}
            onClick={() => {
              onApply({ srcSlot: edge?.srcSlot ?? srcSlot, verb, dstSlot: edge?.dstSlot ?? dstSlot, isEnabled });
              setOpen(false);
            }}
            className="h-8 flex-1 gap-1.5 text-xs"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            {edge ? "Apply" : "Add"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
