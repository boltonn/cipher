"use client";

import { FilterChip as Chip } from "@/components/active-filters";
import { useEntity } from "@/features/entities/hooks/use-entities";
import { format, parseISO } from "date-fns";
import { CalendarRange, FileType, User, Users } from "lucide-react";
import type { OverviewFilters } from "../types";

interface FilterChipsProps {
  filters: OverviewFilters;
  onChange: (filters: OverviewFilters) => void;
}

function EntityChip({ entityId, onRemove }: { entityId: string; onRemove: () => void }) {
  const { data: entity } = useEntity(entityId);
  return (
    <Chip
      icon={<User className="size-3.5 text-muted-foreground" />}
      label={entity?.displayName ?? "Entity"}
      onRemove={onRemove}
    />
  );
}

function EntityGroupChip({ entityIds, onRemove }: { entityIds: string[]; onRemove: () => void }) {
  const { data: entity } = useEntity(entityIds[0]);
  const more = entityIds.length - 1;
  return (
    <Chip
      icon={<Users className="size-3.5 text-muted-foreground" />}
      label={`${entity?.displayName ?? "Entity"}${more > 0 ? ` + ${more} more` : ""}`}
      onRemove={onRemove}
    />
  );
}

function dateLabel(filters: OverviewFilters) {
  const day = (iso: string) => format(parseISO(iso), "d MMM yyyy");
  if (filters.dateFrom && filters.dateTo) return `${day(filters.dateFrom)} – ${day(filters.dateTo)}`;
  if (filters.dateFrom) return `From ${day(filters.dateFrom)}`;
  return `Until ${day(filters.dateTo as string)}`;
}

/** The filters on this search; each removes itself (as a new search, so Back restores it). */
export function FilterChips({ filters, onChange }: FilterChipsProps) {
  const hasDate = !!(filters.dateFrom || filters.dateTo);
  const groups = filters.entityGroups ?? [];
  if (!filters.entityIds.length && !groups.length && !filters.filetypeGroups.length && !hasDate) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {filters.entityIds.map((entityId) => (
        <EntityChip
          key={entityId}
          entityId={entityId}
          onRemove={() => onChange({ ...filters, entityIds: filters.entityIds.filter((id) => id !== entityId) })}
        />
      ))}
      {groups.map((group, index) => (
        <EntityGroupChip
          key={group.join()}
          entityIds={group}
          onRemove={() => onChange({ ...filters, entityGroups: groups.filter((_, other) => other !== index) })}
        />
      ))}
      {filters.filetypeGroups.map((group) => (
        <Chip
          key={group}
          icon={<FileType className="size-3.5 text-muted-foreground" />}
          label={group}
          onRemove={() =>
            onChange({ ...filters, filetypeGroups: filters.filetypeGroups.filter((value) => value !== group) })
          }
        />
      ))}
      {hasDate && (
        <Chip
          icon={<CalendarRange className="size-3.5 text-muted-foreground" />}
          label={dateLabel(filters)}
          onRemove={() => onChange({ ...filters, dateFrom: null, dateTo: null })}
        />
      )}
    </div>
  );
}
