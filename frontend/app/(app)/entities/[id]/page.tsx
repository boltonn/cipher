"use client";

import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CommentSection } from "@/features/comments/components/comment-section";
import { EditEntityDialog } from "@/features/entities/components/edit-entity-dialog";
import { EntityGraph } from "@/features/entities/components/entity-graph";
import { EntityMergePanel } from "@/features/entities/components/entity-merge-list";
import {
  EntityRelationships,
  RelationshipSuggestions,
} from "@/features/entities/components/entity-relationships";
import { EntityNamesPanel } from "@/features/entities/components/entity-names-panel";
import { EntitySelectorProposals } from "@/features/entities/components/entity-selector-proposals";
import { EntitySelectorsPanel } from "@/features/entities/components/entity-selectors-panel";
import { EntityTypeBadge } from "@/features/entities/components/entity-type-badge";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { Section } from "@/features/entities/components/section";
import { InvalidateEntityDialog } from "@/features/entities/components/invalidate-entity-dialog";
import { useEntityProfile } from "@/features/entities/hooks/use-entities";
import type { EntityDetail } from "@/features/entities/types";
import { cn, humanize } from "@/lib/utils";
import {
  Ban,
  BadgeCheck,
  FileText,
  Fingerprint,
  type LucideIcon,
  Network,
  Pencil,
  Search,
  Tags,
  Waypoints,
} from "lucide-react";
import { apiErrorCode } from "@/lib/api-errors";
import Link from "next/link";
import {
  notFound,
  redirect,
  RedirectType,
  useRouter,
  useSearchParams,
} from "next/navigation";
import { use, useState } from "react";

export default function EntityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const search = useSearchParams();
  const { data: profile, isPending, isError, error, refetch } = useEntityProfile(id);
  const [isEditOpen, setEditOpen] = useState(false);
  const [isInvalidateOpen, setInvalidateOpen] = useState(false);

  if (apiErrorCode(error) === "notFound") notFound();
  if (isError) {
    return (
      <PageError
        className="mt-24"
        title="Couldn’t load this entity"
        body="Its profile didn’t come back. This is usually temporary — try again, or head back to the entity list."
        onRetry={() => refetch()}
      />
    );
  }

  if (isPending || !profile) {
    return (
      <PageLoading icon={Network} label="Loading entity…" onRetry={() => refetch()} />
    );
  }

  const { entity, detail, fileCount, relatedTotal, selectorTotal } = profile;
  // People and organizations have richer pages of their own; this dossier is
  // for every other entity type.
  const ownPage =
    entity.entityType === "person" && entity.personId
      ? `/persons/${entity.personId}`
      : entity.entityType === "organization"
        ? `/organizations/${id}`
        : null;
  if (ownPage) {
    const query = search.toString();
    redirect(query ? `${ownPage}?${query}` : ownPage, RedirectType.replace);
  }
  const meta = ENTITY_TYPE_META[entity.entityType];
  const isSelector = entity.entityType === "selector";
  const searchHref = `/search/text?entityId=${id}${entity.datasetId ? `&datasetId=${entity.datasetId}` : ""}`;

  const stats: { label: string; value: number; href: string; Icon: LucideIcon }[] = [
    { label: "Files", value: fileCount, href: searchHref, Icon: FileText },
    {
      label: "Relationships",
      value: relatedTotal,
      href: "#relationships",
      Icon: Waypoints,
    },
    ...(isSelector
      ? []
      : [
          {
            label: "Selectors",
            value: selectorTotal,
            href: "#selectors",
            Icon: Fingerprint,
          } as const,
        ]),
  ];

  return (
    <div className="relative mx-auto max-w-400 px-6 pb-24 pt-5">
      <PageHeader
        eyebrow="Entity"
        value={`named in ${fileCount.toLocaleString()} file${fileCount === 1 ? "" : "s"}`}
      />

      <div className="w-full max-w-5xl">
      {/* identity header */}
      <div className="flex flex-col gap-4 rounded-2xl border border-border bg-muted/40 p-6 backdrop-blur-2xl">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <span
              className={`flex h-12 w-12 items-center justify-center rounded-xl ${meta.bgClass} ${meta.textClass}`}
            >
              <meta.Icon size={22} />
            </span>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-xl font-bold text-white">
                  {entity.displayName}
                </h1>
                {entity.isVerified && (
                  <Badge className="h-6 gap-1.5 border-none bg-primary/10 px-2.5 text-xs text-primary">
                    <BadgeCheck size={14} /> Verified
                  </Badge>
                )}
              </div>
              <div className="mt-2 flex items-center gap-3">
                <EntityTypeBadge
                  type={entity.entityType}
                  detail={(detail?.selectorType as string) ?? null}
                />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-9 gap-2 border-border/50 bg-muted/40 text-xs font-medium text-muted-foreground hover:text-primary"
            >
              <Link href={searchHref}>
                <Search size={14} /> Find in text
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditOpen(true)}
              className="h-9 gap-2 border-border/50 bg-muted/40 text-xs font-medium text-muted-foreground hover:text-primary"
            >
              <Pencil size={14} /> Edit
            </Button>
            {!entity.personId && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setInvalidateOpen(true)}
                  className="h-9 gap-2 text-xs font-medium text-muted-foreground/70 hover:bg-destructive/10 hover:text-destructive"
                >
                  <Ban size={14} /> Mark invalid
                </Button>
                <InvalidateEntityDialog
                  entity={entity}
                  open={isInvalidateOpen}
                  onOpenChange={setInvalidateOpen}
                  onDone={() => router.push("/entities")}
                />
              </>
            )}
          </div>
        </div>

        {entity.notes && (
          <p className="text-sm leading-relaxed text-foreground">
            {entity.notes}
          </p>
        )}

        {entity.tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {entity.tags.map((t) => (
              <Badge
                key={t}
                variant="outline"
                className="h-7 border-border bg-muted/40 px-3 text-sm text-foreground"
              >
                #{t}
              </Badge>
            ))}
          </div>
        )}

        <DetailPanel
          entityType={entity.entityType}
          detail={detail}
        />

        {/* count strip */}
        <div
          className={cn(
            "grid gap-px overflow-hidden rounded-xl border border-border bg-border",
            stats.length === 2 ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-3"
          )}
        >
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
                <div className="text-lg font-semibold text-foreground">
                  {s.value.toLocaleString()}
                </div>
                <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground transition-colors group-hover:text-primary">
                  {s.label}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div className="mt-8 flex flex-col gap-10">
        <EntityMergePanel entity={entity} />
        {!isSelector && <EntitySelectorProposals entityId={id} entityName={entity.displayName} />}

        {!isSelector && (
          <Section id="names" title="Names in the evidence" icon={<Tags size={14} className="text-primary" />}>
            <EntityNamesPanel entity={entity} />
          </Section>
        )}

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
            <RelationshipSuggestions entityId={id} />
            <EntityRelationships entityId={id} />
            {relatedTotal > 0 && (
              <EntityGraph focusEntityId={id} depth={1} compact />
            )}
          </div>
        </Section>

        {!isSelector && (
          <Section
            id="selectors"
            title="Selectors"
            icon={<Fingerprint size={14} className="text-primary" />}
          >
            <EntitySelectorsPanel entityId={id} />
          </Section>
        )}

        {/* CommentSection renders its own "Comments" header -- no Section
            wrapper, or the heading shows twice. */}
        <section id="comments" className="scroll-mt-20">
          <div className="rounded-2xl border border-border bg-muted/40 p-5 backdrop-blur-2xl">
            <CommentSection commentableType="entity" commentableId={id} />
          </div>
        </section>
      </div>
      </div>

      <EditEntityDialog
        entity={entity}
        detail={detail}
        isOpen={isEditOpen}
        onOpenChange={setEditOpen}
      />
    </div>
  );
}

function DetailRow({
  label,
  value,
}: {
  label: string;
  value?: React.ReactNode;
}) {
  if (value == null || value === "") return null;
  return (
    <div className="flex justify-between gap-4 py-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{value}</span>
    </div>
  );
}

function DetailPanel({
  entityType,
  detail,
}: {
  entityType: string;
  detail?: EntityDetail | null;
}) {
  const g = (key: string) => detail?.[key] as string | number | undefined;

  if (entityType === "location") {
    const lat = g("latitude");
    const lon = g("longitude");
    return (
      <div className="rounded-lg border border-border/60 bg-background/40 p-3">
        <DetailRow
          label="Address"
          value={g("addressText") as string}
        />
        <DetailRow label="Country" value={detail?.country as string} />
        <DetailRow
          label="Admin area"
          value={g("adminArea") as string}
        />
        {lat != null && lon != null && (
          <DetailRow
            label="Coordinates"
            value={
              <a
                href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=12/${lat}/${lon}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                {Number(lat).toFixed(4)}, {Number(lon).toFixed(4)}
              </a>
            }
          />
        )}
      </div>
    );
  }
  if (entityType === "selector") {
    return (
      <div className="rounded-lg border border-border/60 bg-background/40 p-3">
        <DetailRow
          label="Kind"
          value={humanize((g("selectorType") as string | undefined) ?? "")}
        />
        <DetailRow
          label="Normalized"
          value={g("normalizedValue") as string}
        />
        <DetailRow label="Raw" value={g("rawValue") as string} />
        <DetailRow
          label="Region"
          value={g("regionHint") as string}
        />
      </div>
    );
  }
  return null;
}
