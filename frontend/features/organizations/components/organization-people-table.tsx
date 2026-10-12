"use client";

import { DataTable } from "@/components/data-table/data-table";
import type {
  DataTableColumn,
  DataTableFilters,
  DataTableSortOrder,
} from "@/components/data-table/types";
import { Badge } from "@/components/ui/badge";
import type { RelationshipType } from "@/features/entities/types";
import type {
  OrganizationPerson,
  RelationshipSource,
} from "@/features/organizations/types";
import { cn, humanize } from "@/lib/utils";
import { BadgeCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const label = (value: string) => humanize(value);

const RELATIONSHIP_OPTIONS: RelationshipType[] = [
  "employedBy",
  "memberOf",
  "emailed",
  "coMentionOf",
  "owns",
];
const SOURCE_OPTIONS: RelationshipSource[] = [
  "manual",
  "import",
  "extraction",
  "selectorInference",
  "coMention",
];
/** Edges a model proposed rather than a person or a structured record. */
const AI_SOURCES = new Set<RelationshipSource>(["extraction", "coMention"]);

const formatDate = (value: string | null) =>
  value
    ? new Date(value).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
      })
    : "—";

function columns(
  onSelectUnit: (id: string) => void
): DataTableColumn<OrganizationPerson>[] {
  return [
    {
      key: "displayName",
      header: "Person",
      type: "text",
      sortable: true,
      filterable: true,
      width: "2fr",
      render: (row) => (
        <Link
          href={`/entities/${row.person.id}`}
          onClick={(ev) => ev.stopPropagation()}
          className="flex min-w-0 items-center gap-1.5 font-medium text-foreground hover:text-primary"
        >
          <span className="truncate">{row.person.displayName}</span>
          {row.person.isVerified && (
            <BadgeCheck size={13} className="shrink-0 text-primary" />
          )}
        </Link>
      ),
    },
    {
      key: "role",
      header: "Role",
      type: "text",
      sortable: true,
      filterable: true,
      width: "1.6fr",
      render: (row) =>
        row.role ? (
          <span className="truncate">{row.role}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "unit",
      header: "Unit",
      type: "text",
      sortable: true,
      filterable: true,
      width: "1.6fr",
      render: (row) => (
        <button
          type="button"
          onClick={(ev) => {
            ev.stopPropagation();
            onSelectUnit(row.unit.id);
          }}
          className="truncate text-left hover:text-primary hover:underline"
        >
          {row.unit.displayName}
        </button>
      ),
    },
    {
      key: "relationshipType",
      header: "Relationship",
      type: "enum",
      sortable: true,
      filterable: true,
      width: "1.2fr",
      enumOptions: RELATIONSHIP_OPTIONS.map((value) => ({
        value,
        label: label(value),
      })),
      render: (row) => (
        <Badge
          variant="outline"
          className={cn(
            "h-5 px-1.5 text-[11px] font-normal",
            row.affiliation === "member"
              ? "border-primary/30 bg-primary/10 text-primary"
              : "border-border bg-muted/40 text-muted-foreground"
          )}
        >
          {label(row.relationshipType)}
        </Badge>
      ),
    },
    {
      key: "source",
      header: "Source",
      type: "enum",
      sortable: true,
      filterable: true,
      width: "1.1fr",
      enumOptions: SOURCE_OPTIONS.map((value) => ({
        value,
        label: label(value),
      })),
      render: (row) => (
        <span
          className={cn(
            "text-xs",
            AI_SOURCES.has(row.source)
              ? "text-annotation"
              : "text-muted-foreground"
          )}
        >
          {label(row.source)}
        </span>
      ),
    },
    {
      key: "mentionCount",
      header: "Mentions",
      type: "number",
      sortable: true,
      align: "right",
      width: "0.8fr",
      render: (row) => row.mentionCount.toLocaleString(),
    },
    {
      key: "fileCount",
      header: "Files",
      type: "number",
      sortable: true,
      align: "right",
      width: "0.7fr",
      render: (row) => row.fileCount.toLocaleString(),
    },
    {
      key: "dateObservedEnd",
      header: "Last seen",
      type: "date",
      sortable: true,
      width: "1fr",
      render: (row) => formatDate(row.dateObservedEnd),
    },
  ];
}

/** People on the selected unit, one row per person<->unit edge; sorting/filtering/paging run server-side. */
export function OrganizationPeopleTable({
  rows,
  total,
  page,
  limit,
  sortBy,
  sortOrder,
  filters,
  isLoading,
  onPageChange,
  onLimitChange,
  onSortChange,
  onFilterChange,
  onSelectUnit,
}: {
  rows: OrganizationPerson[];
  total: number;
  page: number;
  limit: number;
  sortBy: string;
  sortOrder: DataTableSortOrder;
  filters: DataTableFilters;
  isLoading: boolean;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
  onSortChange: (sortBy: string, sortOrder: DataTableSortOrder) => void;
  onFilterChange: (key: string, value: DataTableFilters[string]) => void;
  onSelectUnit: (id: string) => void;
}) {
  const router = useRouter();
  return (
    <DataTable
      columns={columns(onSelectUnit)}
      data={rows}
      getRowId={(row) => row.relationshipId}
      total={total}
      page={page}
      limit={limit}
      sortBy={sortBy}
      sortOrder={sortOrder}
      defaultSortBy="displayName"
      defaultSortOrder="asc"
      filters={filters}
      isLoading={isLoading}
      onPageChange={onPageChange}
      onLimitChange={onLimitChange}
      onSortChange={onSortChange}
      onFilterChange={onFilterChange}
      onRowClick={(row) => router.push(`/entities/${row.person.id}`)}
      emptyMessage="No people on this unit with these filters."
    />
  );
}
