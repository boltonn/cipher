"use client";

import type {
  DataTableFilters,
  DataTableSortOrder,
} from "@/components/data-table/types";
import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Switch } from "@/components/ui/switch";
import type { RelationshipType } from "@/features/entities/types";
import {
  indexTree,
  OrgChart,
  pathTo,
} from "@/features/organizations/components/org-chart";
import { OrganizationPeopleTable } from "@/features/organizations/components/organization-people-table";
import { OrganizationSuggestions } from "@/features/organizations/components/organization-suggestions";
import {
  useOrganizationPeople,
  useOrganizationTree,
} from "@/features/organizations/hooks/use-organization";
import type {
  OrganizationAffiliation,
  OrganizationPeopleParameters,
  OrganizationPeopleSortKey,
  RelationshipSource,
} from "@/features/organizations/types";
import { cn } from "@/lib/utils";
import { Building2, ChevronRight, ExternalLink } from "lucide-react";
import Link from "next/link";
import { use, useMemo, useState } from "react";

const AFFILIATIONS: {
  value: OrganizationAffiliation | undefined;
  label: string;
}[] = [
  { value: undefined, label: "All" },
  { value: "member", label: "Members" },
  { value: "connected", label: "Connected" },
];

/** The table's per-column filters, in the backend's people-parameters shape. */
function toPeopleFilters(
  filters: DataTableFilters
): Partial<OrganizationPeopleParameters> {
  const list = <T,>(key: string) => {
    const value = filters[key] as T[] | undefined;
    return value?.length ? value : undefined;
  };
  return {
    query: (filters.display_name as string) || undefined,
    role: (filters.role as string) || undefined,
    unit: (filters.unit as string) || undefined,
    relationshipTypes: list<RelationshipType>("relationship_type"),
    sources: list<RelationshipSource>("source"),
  };
}

type PeopleView = Omit<
  OrganizationPeopleParameters,
  "query" | "role" | "unit" | "relationshipTypes" | "sources"
>;

const DEFAULT_VIEW: PeopleView = {
  includeSubUnits: true,
  page: 1,
  limit: 50,
  sortBy: "display_name",
  sortOrder: "asc",
};

export default function OrganizationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: tree, isPending, isError, refetch } = useOrganizationTree(id);
  const index = useMemo(() => (tree ? indexTree(tree) : undefined), [tree]);

  const [selectedId, setSelectedId] = useState(id);
  const [view, setView] = useState<PeopleView>(DEFAULT_VIEW);
  const [filters, setFilters] = useState<DataTableFilters>({});
  const people = useOrganizationPeople(selectedId, {
    ...view,
    ...toPeopleFilters(filters),
  });

  const update = (patch: Partial<PeopleView>) =>
    setView((prev) => ({ ...prev, page: 1, ...patch }));
  const select = (unitId: string) => {
    setSelectedId(unitId);
    update({});
  };

  if (isError) {
    return (
      <PageError
        className="mt-24"
        title="Couldn’t load this organization"
        body="Its hierarchy didn’t come back. This is usually temporary — try again."
        onRetry={() => refetch()}
      />
    );
  }
  if (isPending || !index)
    return <PageLoading icon={Building2} label="Loading organization…" />;

  const root = index.byId.get(tree.rootId);
  const selected = index.byId.get(selectedId) ?? root;
  const path = pathTo(index, selectedId);
  const hasSubUnits = (index.children.get(selectedId)?.length ?? 0) > 0;

  return (
    <div className="mx-auto max-w-400 px-6 pb-20 pt-5">
      <PageHeader
        eyebrow={root?.entity.displayName ?? "Organization"}
        icon={<Building2 />}
        value={`${tree.nodes.length} ${tree.nodes.length === 1 ? "unit" : "units"} · ${(
          index.subtreeMembers.get(tree.rootId) ?? 0
        ).toLocaleString()} members`}
        actions={
          <Button asChild variant="outline" className="h-9 gap-2 text-xs">
            <Link href={`/entities/${selectedId}`}>
              <ExternalLink size={14} />
              Open entity
            </Link>
          </Button>
        }
      />

      <section className="mt-4 rounded-xl border border-border bg-muted/20 p-4">
        {tree.nodes.length === 1 && (
          <p className="py-6 text-center text-xs text-muted-foreground">
            No sub-units yet — give an organization this one as its parent (Edit
            on the entity page) to build the hierarchy.
          </p>
        )}
        <OrgChart
          tree={tree}
          index={index}
          selectedId={selectedId}
          onSelect={select}
        />
      </section>

      <section className="mt-6 space-y-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <nav className="flex min-w-0 flex-1 flex-wrap items-center gap-1 text-xs text-muted-foreground">
            {path.map((node, i) => (
              <span
                key={node.entity.id}
                className="inline-flex items-center gap-1"
              >
                {i > 0 && <ChevronRight size={12} />}
                <button
                  type="button"
                  onClick={() => select(node.entity.id)}
                  className={cn(
                    "hover:text-primary",
                    node.entity.id === selectedId &&
                      "font-semibold text-foreground"
                  )}
                >
                  {node.entity.displayName}
                </button>
              </span>
            ))}
            <span className="ml-2 tabular-nums">
              {(people.data?.total ?? 0).toLocaleString()}{" "}
              {people.data?.total === 1 ? "person" : "people"}
            </span>
          </nav>

          <ButtonGroup>
            {AFFILIATIONS.map(({ value, label }) => (
              <Button
                key={label}
                variant="outline"
                size="sm"
                aria-pressed={view.affiliation === value}
                onClick={() => update({ affiliation: value })}
                className={cn(
                  "h-8 border-border text-xs",
                  view.affiliation === value
                    ? "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                    : "bg-muted/40 text-muted-foreground hover:text-foreground"
                )}
              >
                {label}
              </Button>
            ))}
          </ButtonGroup>

          <label
            className={cn(
              "flex items-center gap-2 text-xs text-muted-foreground",
              !hasSubUnits && "opacity-50"
            )}
          >
            Include sub-units
            <Switch
              checked={view.includeSubUnits}
              disabled={!hasSubUnits}
              onCheckedChange={(includeSubUnits) => update({ includeSubUnits })}
            />
          </label>
        </div>

        <OrganizationSuggestions unitId={selectedId} onSelectUnit={select} />

        {people.isError ? (
          <PageError
            title={`Couldn’t load people for ${selected?.entity.displayName ?? "this unit"}`}
            body="The request failed. This is usually temporary — try again."
            onRetry={() => people.refetch()}
          />
        ) : (
          <OrganizationPeopleTable
            rows={people.data?.data ?? []}
            total={people.data?.total ?? 0}
            page={view.page}
            limit={view.limit}
            sortBy={view.sortBy}
            sortOrder={view.sortOrder}
            filters={filters}
            isLoading={people.isFetching}
            onPageChange={(page) => setView((prev) => ({ ...prev, page }))}
            onLimitChange={(limit) => update({ limit })}
            onSortChange={(sortBy: string, sortOrder: DataTableSortOrder) =>
              update({ sortBy: sortBy as OrganizationPeopleSortKey, sortOrder })
            }
            onFilterChange={(key, value) => {
              setFilters((prev) => ({ ...prev, [key]: value }));
              update({});
            }}
            onSelectUnit={select}
          />
        )}
      </section>
    </div>
  );
}
