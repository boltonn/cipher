"use client";

import { Button } from "@/components/ui/button";
import { GRAPH_NODE_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEvent } from "@/features/events/api";
import { EventDetailSheet } from "@/features/events/components/event-detail-sheet";
import { EVENT_TYPE_META } from "@/features/events/components/event-type-meta";
import { formatDateRange, formatEventStart } from "@/features/events/lib/format";
import {
  INSPECTOR_SHELL,
  InspectorAction,
} from "@/features/graph/components/node-inspector";
import { cn } from "@/lib/utils";
import {
  EyeOff,
  ExternalLink,
  Focus,
  Loader2,
  Maximize2,
  Minimize2,
  X,
} from "lucide-react";
import { useState } from "react";

interface EventNodeInspectorProps {
  eventId: string;
  isExpanded: boolean;
  onClose: () => void;
  onExpand: (id: string) => void;
  onCollapse: (id: string) => void;
  onHide: (id: string) => void;
  onIsolate: (id: string) => void;
}

/** Side panel for an event node (reached through `participant_in` edges); expanding it pulls in every participant. */
export function EventNodeInspector({
  eventId,
  isExpanded,
  onClose,
  onExpand,
  onCollapse,
  onHide,
  onIsolate,
}: EventNodeInspectorProps) {
  const { data: event, isPending } = useEvent(eventId);
  const [sheetOpen, setSheetOpen] = useState(false);
  const nodeMeta = GRAPH_NODE_TYPE_META.event;
  const typeMeta = event ? EVENT_TYPE_META[event.eventType] : null;

  return (
    <aside className={INSPECTOR_SHELL}>
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Event
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-muted-foreground hover:text-foreground"
        >
          <X size={13} />
        </button>
      </div>

      {isPending || !event ? (
        <div className="flex flex-1 items-center justify-center py-10 text-muted-foreground">
          <Loader2 size={16} className="animate-spin" />
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-3">
          <div className="space-y-2">
            <h2 className="text-sm font-bold leading-snug text-foreground">{event.title}</h2>
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
                nodeMeta.bgClass,
                nodeMeta.textClass,
                nodeMeta.borderClass
              )}
            >
              {typeMeta && <typeMeta.Icon size={11} />}
              {typeMeta?.label ?? nodeMeta.label}
            </span>
            <p className="text-xs text-muted-foreground">
              {formatEventStart(event)}
              {event.dateEnd && event.dateEnd !== event.dateStart && (
                <span className="block">{formatDateRange(event)}</span>
              )}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
            <div className="bg-card px-2 py-2 text-center">
              <div className="text-sm font-semibold text-foreground">{event.participants.length}</div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                Participants
              </div>
            </div>
            <div className="bg-card px-2 py-2 text-center">
              <div className="text-sm font-semibold text-foreground">
                {event.participants.filter((p) => p.entityId).length}
              </div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                Resolved
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            {isExpanded ? (
              <InspectorAction icon={Minimize2} onClick={() => onCollapse(eventId)}>
                Collapse participants
              </InspectorAction>
            ) : (
              <InspectorAction icon={Maximize2} onClick={() => onExpand(eventId)}>
                Expand participants
              </InspectorAction>
            )}
            <InspectorAction icon={Focus} onClick={() => onIsolate(eventId)}>
              Isolate
            </InspectorAction>
            <InspectorAction icon={EyeOff} onClick={() => onHide(eventId)}>
              Hide from view
            </InspectorAction>
          </div>

          <Button
            variant="outline"
            size="sm"
            className="mt-auto h-8 gap-1.5 border-border bg-muted/40 text-xs"
            onClick={() => setSheetOpen(true)}
          >
            Open event
            <ExternalLink size={12} />
          </Button>
        </div>
      )}

      <EventDetailSheet eventId={sheetOpen ? eventId : null} onOpenChange={setSheetOpen} />
    </aside>
  );
}
