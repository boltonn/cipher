"use client";

import { Section } from "@/features/entities/components/section";
import { useEvents } from "@/features/events/api";
import { EventDetailSheet } from "@/features/events/components/event-detail-sheet";
import { categoryMeta, EVENT_TYPE_META } from "@/features/events/components/event-type-meta";
import { formatEventStart } from "@/features/events/lib/format";
import { cn } from "@/lib/utils";
import { CalendarDays } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

/**
 * "Events" block on the person dossier. Filters events by `participantEntityId`
 * (the person's bridge entity id). Renders nothing until participant resolution
 * has linked at least one event to this entity, so it stays quiet by default.
 */
export function PersonEventsSection({ entityId }: { entityId: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isPending } = useEvents({
    participantEntityId: entityId,
    sortBy: "date_start",
    sortOrder: "desc",
    limit: 12,
  });

  const events = data?.data ?? [];
  if (isPending || events.length === 0) return null;

  return (
    <Section
      title="Events"
      icon={<CalendarDays size={14} className="text-primary" />}
      action={
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
          {data?.total ?? events.length}
        </span>
      }
    >
      <ul className="divide-y divide-border rounded-2xl border border-border bg-muted/40">
        {events.map((e) => {
          const meta = EVENT_TYPE_META[e.eventType];
          const cat = categoryMeta(e.category);
          return (
            <li key={e.id}>
              <button
                type="button"
                onClick={() => setSelectedId(e.id)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-muted/60"
              >
                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", cat.dotClass)} />
                <meta.Icon size={13} className="shrink-0 text-muted-foreground" />
                <span
                  className={cn(
                    "flex-1 truncate text-sm text-foreground",
                    e.status === "cancelled" && "line-through opacity-60"
                  )}
                >
                  {e.title}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {formatEventStart(e)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <Link
        href={`/events`}
        className="mt-2 inline-block text-[11px] text-muted-foreground hover:text-foreground"
      >
        Open the events calendar →
      </Link>

      <EventDetailSheet
        eventId={selectedId}
        onOpenChange={(open) => !open && setSelectedId(null)}
      />
    </Section>
  );
}
