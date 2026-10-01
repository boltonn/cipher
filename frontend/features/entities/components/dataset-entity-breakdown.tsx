"use client";

import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntityBreakdown } from "@/features/entities/hooks/use-entities";
import {
  SELECTOR_TYPE_LABELS,
  type EntityBreakdownItem,
  type SelectorType,
} from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { motion } from "motion/react";
import Link from "next/link";

interface Props {
  datasetId: string;
}

function labelFor(section: Section, key: string): string {
  if (section === "entityType")
    return (
      ENTITY_TYPE_META[key as keyof typeof ENTITY_TYPE_META]?.label ?? key
    );
  if (section === "selectorType")
    return SELECTOR_TYPE_LABELS[key as SelectorType] ?? key;
  return key.replace(/_/g, " ");
}

type Section = "entityType" | "selectorType" | "selectorSubtype";

function hrefFor(datasetId: string, section: Section, key: string): string {
  const p = new URLSearchParams({ datasetId });
  if (section === "entityType") p.set("entityType", key);
  else {
    p.set("entityType", "selector");
    p.set(section, key);
  }
  return `/entities?${p.toString()}`;
}

function BarList({
  datasetId,
  section,
  items,
}: {
  datasetId: string;
  section: Section;
  items: EntityBreakdownItem[];
}) {
  if (items.length === 0) return null;
  const total = items.reduce((s, i) => s + i.count, 0);
  return (
    <div className="flex flex-col gap-2.5">
      {items.map((item) => {
        const pct = total > 0 ? (item.count / total) * 100 : 0;
        return (
          <motion.div key={item.key} layout transition={{ duration: 0.2 }}>
            <Link
              href={hrefFor(datasetId, section, item.key)}
              className="group flex flex-col gap-1 rounded-lg -mx-1 px-1 py-0.5 hover:bg-muted/60"
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-foreground group-hover:text-primary">
                  {labelFor(section, item.key)}
                </span>
                <span className="text-muted-foreground">
                  {item.count.toLocaleString()}{" "}
                  <span className="opacity-60">({pct.toFixed(0)}%)</span>
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                <motion.div
                  className="h-full rounded-full bg-primary/50 group-hover:bg-primary"
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                />
              </div>
            </Link>
          </motion.div>
        );
      })}
    </div>
  );
}

/** Compact linked breakdown of a dataset's entities -- by type, then by selector type/subtype. */
export function DatasetEntityBreakdown({ datasetId }: Props) {
  const { data, isPending } = useEntityBreakdown(datasetId);

  if (isPending) {
    return (
      <div className="h-40 flex items-center justify-center text-xs text-muted-foreground">
        Loading...
      </div>
    );
  }
  if (!data || data.total === 0) {
    return (
      <p className="py-8 text-center text-xs italic text-muted-foreground">
        No entities extracted for this dataset yet.
      </p>
    );
  }

  const allCols: {
    title: string;
    section: Section;
    items: EntityBreakdownItem[];
  }[] = [
    { title: "By type", section: "entityType", items: data.byEntityType },
    { title: "By selector type", section: "selectorType", items: data.bySelectorType },
    {
      title: "By platform / network",
      section: "selectorSubtype",
      items: data.bySelectorSubtype,
    },
  ];
  const cols = allCols.filter((c) => c.items.length > 0);

  return (
    <div
      className={cn(
        "grid gap-6",
        cols.length === 3
          ? "sm:grid-cols-3"
          : cols.length === 2
            ? "sm:grid-cols-2"
            : "grid-cols-1"
      )}
    >
      {cols.map((c) => (
        <div key={c.section} className="flex flex-col gap-3">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {c.title}
          </h3>
          <BarList datasetId={datasetId} section={c.section} items={c.items} />
        </div>
      ))}
    </div>
  );
}
