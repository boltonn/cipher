"use client";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntityProfile } from "@/features/entities/hooks/use-entities";
import type { EntityType } from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { motion } from "motion/react";
import { ArrowUpRight, BadgeCheck, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

interface EntityTooltipCardProps {
  entityId: string;
}

/** The card body -- the aceternity "tooltip card" look, lazily fed by the profile endpoint. */
export function EntityTooltipCard({ entityId }: EntityTooltipCardProps) {
  const { data, isPending } = useEntityProfile(entityId);

  if (isPending || !data) {
    return (
      <div className="flex items-center gap-2 p-1 text-xs text-muted-foreground">
        <Loader2 size={12} className="animate-spin" /> Loading entity…
      </div>
    );
  }

  const { entity, detail, selectors, fileCount } = data;
  const meta = ENTITY_TYPE_META[entity.entityType];
  const selectorValue =
    (detail?.normalizedValue as string) ?? null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 24 }}
      className="flex flex-col gap-2.5"
    >
      <div
        className="-m-2.5 mb-0 flex items-center gap-2.5 rounded-t-lg border-b border-border/60 px-3 py-2.5"
        style={{ background: `linear-gradient(120deg, ${meta.color}22, transparent)` }}
      >
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
            meta.bgClass,
            meta.textClass
          )}
        >
          <meta.Icon size={16} />
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-sm font-semibold text-foreground">
              {entity.displayName}
            </span>
            {entity.isVerified && <BadgeCheck size={13} className="shrink-0 text-primary" />}
          </div>
          <span className={cn("text-[11px] font-bold uppercase tracking-wide", meta.textClass)}>
            {meta.label}
            {selectorValue ? ` · ${selectorValue}` : ""}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
        <Stat label="files" value={fileCount} />
        <Stat label="selectors" value={selectors.length} />
        <Stat label="relationships" value={data.relatedEntities.length} />
      </div>

      {entity.notes && (
        <p className="line-clamp-2 text-[11px] leading-relaxed text-foreground/80">{entity.notes}</p>
      )}

      <Link
        href={`/entities/${entity.id}`}
        className="mt-0.5 inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
      >
        Open profile <ArrowUpRight size={12} />
      </Link>
    </motion.div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <span className="rounded bg-muted/60 px-1.5 py-0.5">
      <span className="font-mono text-foreground">{value}</span> {label}
    </span>
  );
}

interface EntityHoverCardProps {
  entityId: string;
  entityType?: EntityType;
  /** keep the card shut (e.g. while an editor for this span is open) */
  disabled?: boolean;
  children: React.ReactNode;
}

/**
 * Wraps any trigger element in a hover card that shows the entity tooltip. Stays shut while a
 * mouse button is down, so dragging across a mention chip selects text instead of the card.
 */
export function EntityHoverCard({ entityId, disabled, children }: EntityHoverCardProps) {
  const [open, setOpen] = useState(false);
  const pressed = useRef(false);
  const press = () => {
    pressed.current = true;
    setOpen(false);
    window.addEventListener("pointerup", () => (pressed.current = false), { once: true });
  };
  return (
    <HoverCard open={open && !disabled} onOpenChange={(next) => setOpen(next && !pressed.current)} openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild onPointerDown={press}>
        {children}
      </HoverCardTrigger>
      <HoverCardContent className="w-72" side="top">
        <EntityTooltipCard entityId={entityId} />
      </HoverCardContent>
    </HoverCard>
  );
}
