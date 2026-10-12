"use client";

import type {
  DataTableFilters,
  DataTableSortOrder,
} from "@/components/data-table/types";
import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { CommentSection } from "@/features/comments/components/comment-section";
import { EditEntityDialog } from "@/features/entities/components/edit-entity-dialog";
import { EntityGraph } from "@/features/entities/components/entity-graph";
import { EntityMergePanel } from "@/features/entities/components/entity-merge-list";
import { EntityNamesPanel } from "@/features/entities/components/entity-names-panel";
import { EntityRelationships } from "@/features/entities/components/entity-relationships";
import { EntitySelectorProposals } from "@/features/entities/components/entity-selector-proposals";
import { EntitySelectorsPanel } from "@/features/entities/components/entity-selectors-panel";
import { InvalidateEntityDialog } from "@/features/entities/components/invalidate-entity-dialog";
import { Section } from "@/features/entities/components/section";
import { useEntityProfile } from "@/features/entities/hooks/use-entities";
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
import { cn, humanize } from "@/lib/utils";
import {
  BadgeCheck,
  Ban,
  Building2,
  ChevronRight,
  Ellipsis,
  FileText,
  Fingerprint,
  type LucideIcon,
  MessageSquareQuote,
  Network,
  Pencil,
  Search,
  Tags,
  Waypoints,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
    query: (filters.displayName as string) || undefined,
    role: (filters.role as string) || undefined,
    unit: (filters.unit as string) || undefined,
    relationshipTypes: list<RelationshipType>("relationshipType"),
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
  sortBy: "displayName",
  sortOrder: "asc",
};

export default function OrganizationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { data: profile } = useEntityProfile(id);
  const [isEditOpen, setEditOpen] = useState(false);
  const [isInvalidateOpen, setInvalidateOpen] = useState(false);
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
  const entity = profile?.entity;
  const category = profile?.detail?.category;
  const facts = [
    typeof category === "string" ? humanize(category) : undefined,
    profile?.detail?.legalName,
    profile?.detail?.country,
  ].filter((v): v is string => typeof v === "string" && v !== "");
  const searchHref = `/search/text?entityId=${id}${entity?.datasetId ? `&datasetId=${entity.datasetId}` : ""}`;
  const mentionTotal = Object.values(profile?.mentionCounts ?? {}).reduce(
    (sum, n) => sum + (n ?? 0),
    0
  );
  const stats: {
    label: string;
    value: number;
    href: string;
    Icon: LucideIcon;
  }[] = [
    {
      label: "Mentions",
      value: mentionTotal,
      href: searchHref,
      Icon: MessageSquareQuote,
    },
    {
      label: "Files",
      value: profile?.fileCount ?? 0,
      href: searchHref,
      Icon: FileText,
    },
    {
      label: "Relationships",
      value: profile?.relatedTotal ?? 0,
      href: "#relationships",
      Icon: Waypoints,
    },
    {
      label: "Selectors",
      value: profile?.selectorTotal ?? 0,
      href: "#selectors",
      Icon: Fingerprint,
    },
  ];
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
          <>
            {selectedId !== id && (
              <Button asChild variant="outline" className="h-9 gap-2 text-xs">
                <Link href={`/organizations/${selectedId}`}>
                  <Building2 size={14} />
                  Open {selected?.entity.displayName ?? "unit"}
                </Link>
              </Button>
            )}
            <Button asChild variant="outline" className="h-9 gap-2 text-xs">
              <Link href={searchHref}>
                <Search size={14} />
                Find in text
              </Link>
            </Button>
            <Button
              variant="outline"
              onClick={() => setEditOpen(true)}
              disabled={!entity}
              className="h-9 gap-2 text-xs"
            >
              <Pencil size={14} />
              Edit
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="More actions"
                  disabled={!entity}
                  className="h-9 w-9"
                >
                  <Ellipsis size={14} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={() => setInvalidateOpen(true)}
                >
                  <Ban size={14} />
                  Mark invalid
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      {entity && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted-foreground">
            {entity.isVerified && (
              <Badge className="h-6 gap-1.5 border-none bg-primary/10 px-2.5 text-xs text-primary">
                <BadgeCheck size={14} /> Verified
              </Badge>
            )}
            {facts.map((f) => (
              <span key={f} className="inline-block first-letter:uppercase">
                {f}
              </span>
            ))}
            {entity.tags.map((t) => (
              <Badge
                key={t}
                variant="outline"
                className="h-6 border-border bg-muted/40 px-2.5 text-xs text-foreground"
              >
                #{t}
              </Badge>
            ))}
          </div>
          {entity.notes && (
            <p className="text-sm leading-relaxed text-foreground">
              {entity.notes}
            </p>
          )}
          <div className="grid max-w-5xl grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-4">
            {stats.map((s) => (
              <Link
                key={s.label}
                href={s.href}
                className="group flex items-center gap-3 bg-card px-4 py-3 transition-colors hover:bg-primary/5"
              >
                <s.Icon
                  size={18}
                  className="shrink-0 text-primary/60 transition-colors group-hover:text-primary"
                />
                <div className="min-w-0">
                  <div className="text-lg font-semibold tabular-nums text-foreground">
                    {s.value.toLocaleString()}
                  </div>
                  <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground transition-colors group-hover:text-primary">
                    {s.label}
                  </div>
                </div>
              </Link>
            ))}
          </div>
          <EntityMergePanel entity={entity} />
          <EntitySelectorProposals
            entityId={id}
            entityName={entity.displayName}
          />
        </div>
      )}

      <section className="mt-4 rounded-xl border border-border bg-muted/20 p-4">
        {tree.nodes.length === 1 && (
          <p className="py-6 text-center text-xs text-muted-foreground">
            No sub-units yet — give an organization this one as its parent
            (Edit) to build the hierarchy.
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

      {entity && (
        <div className="mt-10 flex max-w-5xl flex-col gap-10">
          <Section
            id="names"
            title="Names in the evidence"
            icon={<Tags size={14} className="text-primary" />}
          >
            <EntityNamesPanel entity={entity} />
          </Section>

          <Section
            id="relationships"
            title="Relationships"
            icon={<Waypoints size={14} className="text-primary" />}
            action={
              <Button
                asChild
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-xs font-medium text-primary hover:text-primary"
              >
                <Link href={`/entities/${id}/graph`}>
                  <Network size={13} /> Full graph
                </Link>
              </Button>
            }
          >
            <div className="space-y-4">
              <EntityRelationships entityId={id} />
              {profile.relatedTotal > 0 && (
                <EntityGraph focusEntityId={id} depth={1} compact />
              )}
            </div>
          </Section>

          <Section
            id="selectors"
            title="Selectors"
            icon={<Fingerprint size={14} className="text-primary" />}
          >
            <EntitySelectorsPanel entityId={id} />
          </Section>

          {/* CommentSection renders its own "Comments" header -- no Section
              wrapper, or the heading shows twice. */}
          <section id="comments" className="scroll-mt-20">
            <div className="rounded-2xl border border-border bg-muted/40 p-5 backdrop-blur-2xl">
              <CommentSection commentableType="entity" commentableId={id} />
            </div>
          </section>

          <EditEntityDialog
            entity={entity}
            detail={profile.detail}
            isOpen={isEditOpen}
            onOpenChange={setEditOpen}
          />
          <InvalidateEntityDialog
            entity={entity}
            open={isInvalidateOpen}
            onOpenChange={setInvalidateOpen}
            onDone={() => router.push("/entities")}
          />
        </div>
      )}
    </div>
  );
}
