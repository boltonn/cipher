"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ArrowRight } from "lucide-react";
import type { Lane } from "../types";

interface LaneSectionProps {
  title: string;
  icon: React.ReactNode;
  lane: Lane<unknown>;
  /** Shown instead of a count when the lane's total isn't a match count (e.g. image similarity). */
  countLabel?: string;
  onSeeAll?: () => void;
  className?: string;
  children: React.ReactNode;
}

function countText(lane: Lane<unknown>) {
  return lane.totalIsExact ? lane.total.toLocaleString() : `${lane.total.toLocaleString()}+`;
}

/** One lane's preview block: title, count, "See all", and a message instead of items when it timed out. */
export function LaneSection({ title, icon, lane, countLabel, onSeeAll, className, children }: LaneSectionProps) {
  const failed = lane.status === "timeout" || lane.status === "error";
  return (
    <section className={cn("rounded-xl border border-border bg-muted/30 p-4", className)}>
      <header className="mb-3 flex items-center gap-2">
        <span className="text-muted-foreground">{icon}</span>
        <h2 className="text-sm font-medium text-foreground">{title}</h2>
        {!failed && <span className="text-xs text-muted-foreground">{countLabel ?? countText(lane)}</span>}
        {onSeeAll && (
          <Button variant="ghost" size="sm" className="ml-auto h-7 gap-1 text-xs" onClick={onSeeAll}>
            See all <ArrowRight className="size-3.5" />
          </Button>
        )}
      </header>
      {failed ? (
        <p className="text-sm text-muted-foreground">
          {lane.status === "timeout" ? "This took too long to preview." : "This part of the search failed."}
          {onSeeAll && " Open it with See all."}
        </p>
      ) : (
        children
      )}
    </section>
  );
}
