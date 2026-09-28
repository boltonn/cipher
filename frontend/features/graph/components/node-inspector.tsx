"use client";

import { EntityTypeBadge } from "@/features/entities/components/entity-type-badge";
import { useEntity, useEntityProfile } from "@/features/entities/hooks/use-entities";
import type { SelectorType } from "@/features/entities/types";
import { Button } from "@/components/ui/button";
import {
  BadgeCheck,
  EyeOff,
  ExternalLink,
  Focus,
  Loader2,
  Minimize2,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";

interface NodeInspectorProps {
  entityId: string;
  isSeed: boolean;
  isExpanded: boolean;
  onClose: () => void;
  onAddSeed: (id: string) => void;
  onExpand: (id: string) => void;
  onCollapse: (id: string) => void;
  onHide: (id: string) => void;
  onIsolate: (id: string) => void;
}

export function NodeInspector({
  entityId,
  isSeed,
  isExpanded,
  onClose,
  onAddSeed,
  onExpand,
  onCollapse,
  onHide,
  onIsolate,
}: NodeInspectorProps) {
  const { data: entity, isPending } = useEntity(entityId);
  const { data: profile } = useEntityProfile(entityId);

  const selectorType =
    (profile?.detail?.selectorType as SelectorType | undefined) ??
    (profile?.detail?.selector_type as SelectorType | undefined) ??
    null;

  const stats = [
    { label: "Files", value: profile?.fileCount },
    { label: "Related", value: profile?.relatedTotal },
    { label: "Selectors", value: profile?.selectorTotal },
  ].filter((s) => s.value != null);

  const href =
    entity?.personId != null ? `/persons/${entity.personId}` : `/entities/${entityId}`;

  return (
    <aside className="flex w-72 shrink-0 flex-col rounded-xl border border-border bg-muted/40 shadow-xl">
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-2">
        <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">
          Node
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

      {isPending || !entity ? (
        <div className="flex flex-1 items-center justify-center py-10 text-muted-foreground">
          <Loader2 size={16} className="animate-spin" />
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-3">
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <h2 className="flex-1 text-sm font-bold leading-snug text-foreground">
                {entity.displayName}
              </h2>
              {entity.isVerified && (
                <BadgeCheck size={14} className="mt-0.5 shrink-0 text-primary" />
              )}
            </div>
            <EntityTypeBadge type={entity.entityType} detail={selectorType} />
            {isSeed && (
              <span className="ml-1.5 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-primary">
                <Sparkles size={10} /> Seed
              </span>
            )}
          </div>

          {stats.length > 0 && (
            <div className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border bg-border">
              {stats.map((s) => (
                <div key={s.label} className="bg-card px-2 py-2 text-center">
                  <div className="text-sm font-semibold text-foreground">
                    {s.value?.toLocaleString()}
                  </div>
                  <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                    {s.label}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            {isExpanded ? (
              <InspectorAction icon={Minimize2} onClick={() => onCollapse(entityId)}>
                Collapse neighbours
              </InspectorAction>
            ) : (
              <InspectorAction icon={Focus} onClick={() => onExpand(entityId)}>
                Expand neighbours
              </InspectorAction>
            )}
            {!isSeed && (
              <InspectorAction icon={Sparkles} onClick={() => onAddSeed(entityId)}>
                Pin as seed
              </InspectorAction>
            )}
            <InspectorAction icon={Focus} onClick={() => onIsolate(entityId)}>
              Isolate
            </InspectorAction>
            <InspectorAction icon={EyeOff} onClick={() => onHide(entityId)}>
              Hide from view
            </InspectorAction>
          </div>

          <Button
            asChild
            variant="outline"
            size="sm"
            className="mt-auto h-8 gap-1.5 border-border bg-muted/40 text-xs"
          >
            <Link href={href}>
              Open {entity.personId != null ? "person" : "entity"}
              <ExternalLink size={12} />
            </Link>
          </Button>
        </div>
      )}
    </aside>
  );
}

function InspectorAction({
  icon: Icon,
  onClick,
  children,
}: {
  icon: typeof Focus;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 rounded-md border border-border/60 bg-background/40 px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
    >
      <Icon size={13} className="shrink-0" />
      {children}
    </button>
  );
}
