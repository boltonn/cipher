"use client";

import { Button } from "@/components/ui/button";
import { EntityPicker } from "@/features/entities/components/entity-picker";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { entitiesService } from "@/features/entities/api";
import { useOrganizationStructure } from "@/features/entities/hooks/use-entities";
import type { EntitySummary, EntityType, RelationshipType } from "@/features/entities/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

type AddKind = "child" | "location" | "person";

/** Each add action as an edge: sub-units point up at the org, the org points at its locations, people at the org. */
const ADD: Record<AddKind, { label: string; pick: EntityType; relationshipType: RelationshipType; fromOrg: boolean }> = {
  child: { label: "sub-unit", pick: "organization", relationshipType: "part_of", fromOrg: false },
  location: { label: "location", pick: "location", relationshipType: "located_in", fromOrg: true },
  person: { label: "person", pick: "person", relationshipType: "employed_by", fromOrg: false },
};

/**
 * An organization's hierarchy: its parent chain, sub-units (divisions, offices, branches),
 * locations and people -- all read from `part_of` / `located_in` / `employed_by` / `member_of`
 * edges. The parent itself is set in Edit (an organization has at most one).
 */
export function OrganizationStructure({ entityId, entityName }: { entityId: string; entityName: string }) {
  const { data } = useOrganizationStructure(entityId);
  const [adding, setAdding] = useState<AddKind | null>(null);
  const qc = useQueryClient();
  const add = useMutation({
    mutationFn: ({ kind, otherId }: { kind: AddKind; otherId: string }) => {
      const { relationshipType, fromOrg } = ADD[kind];
      const [src, dst] = fromOrg ? [entityId, otherId] : [otherId, entityId];
      return entitiesService.createRelationship(src, { dstEntityId: dst, relationshipType });
    },
    onSuccess: (_r, { otherId }) => {
      qc.invalidateQueries({ queryKey: ["entities", entityId] });
      qc.invalidateQueries({ queryKey: ["entities", otherId] });
      setAdding(null);
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Couldn't add it"),
  });

  if (!data) return null;
  const parentChain = [...data.ancestors].reverse();

  return (
    <div className="space-y-4">
      <nav className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
        {parentChain.length === 0 && <span className="italic">Top-level organization — set a parent in Edit.</span>}
        {parentChain.map((a) => (
          <span key={a.id} className="inline-flex items-center gap-1">
            <EntityLink entity={a} />
            <ChevronRight size={12} />
          </span>
        ))}
        {parentChain.length > 0 && <span className="font-medium text-foreground">{entityName}</span>}
      </nav>

      <div className="grid gap-3 sm:grid-cols-3">
        <Group title="Sub-units" kind="child" entities={data.children} onAdd={setAdding} />
        <Group title="Locations" kind="location" entities={data.locations} onAdd={setAdding} />
        <Group
          title="People"
          kind="person"
          entities={data.members.map((m) => m.entity)}
          notes={Object.fromEntries(
            data.members.map((m) => [
              m.entity.id,
              m.role ?? (m.relationshipType === "member_of" ? "member" : "employee"),
            ])
          )}
          onAdd={setAdding}
        />
      </div>

      {adding && (
        <div className="flex items-center gap-2 rounded-lg border border-border p-2">
          <span className="shrink-0 text-xs text-muted-foreground">Add {ADD[adding].label}:</span>
          <EntityPicker
            entityTypes={[ADD[adding].pick]}
            placeholder={`Search ${ADD[adding].pick}s…`}
            onSelect={(otherId) => otherId !== entityId && add.mutate({ kind: adding, otherId })}
            className="min-w-0 flex-1"
          />
          <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setAdding(null)}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}

function Group({
  title,
  kind,
  entities,
  notes,
  onAdd,
}: {
  title: string;
  kind: AddKind;
  entities: EntitySummary[];
  notes?: Record<string, string>;
  onAdd: (kind: AddKind) => void;
}) {
  return (
    <div className="rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border/60 px-3 py-1.5">
        <span className="text-[11px] font-semibold text-foreground">
          {title} <span className="font-normal text-muted-foreground">{entities.length}</span>
        </span>
        <Button variant="ghost" size="sm" className="h-6 gap-1 px-1.5 text-[11px]" onClick={() => onAdd(kind)}>
          <Plus size={11} /> Add
        </Button>
      </div>
      {entities.length === 0 ? (
        <p className="px-3 py-2 text-[11px] italic text-muted-foreground">None yet.</p>
      ) : (
        <ul className="max-h-56 divide-y divide-border/60 overflow-y-auto">
          {entities.map((e) => (
            <li key={e.id} className="flex items-center gap-2 px-3 py-1.5 text-xs">
              <EntityLink entity={e} />
              {notes?.[e.id] && <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{notes[e.id]}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EntityLink({ entity }: { entity: EntitySummary }) {
  const { Icon } = ENTITY_TYPE_META[entity.entityType];
  return (
    <Link href={`/entities/${entity.id}`} className="inline-flex min-w-0 items-center gap-1 hover:text-primary hover:underline">
      <Icon size={12} className="shrink-0" />
      <span className="truncate">{entity.displayName}</span>
    </Link>
  );
}
