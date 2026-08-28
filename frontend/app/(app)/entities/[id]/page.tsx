"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CommentSection } from "@/features/comments/components/comment-section";
import { EditEntityDialog } from "@/features/entities/components/edit-entity-dialog";
import { EntityGraph } from "@/features/entities/components/entity-graph";
import { EntityMentionsByFile } from "@/features/entities/components/entity-mentions-by-file";
import { EntityTypeBadge } from "@/features/entities/components/entity-type-badge";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { Section } from "@/features/entities/components/section";
import { useEntityProfile } from "@/features/entities/hooks/use-entities";
import type { EntityDetail } from "@/features/entities/types";
import {
  BadgeCheck,
  ExternalLink,
  Loader2,
  Pencil,
  ScanFace,
} from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";

export default function EntityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: profile, isPending } = useEntityProfile(id);
  const [isEditOpen, setEditOpen] = useState(false);

  if (isPending || !profile) {
    return (
      <div className="flex items-center justify-center py-48 text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin text-primary/40" />
      </div>
    );
  }

  const { entity, detail, selectors, relatedEntities, mentionCounts } = profile;
  const meta = ENTITY_TYPE_META[entity.entityType];
  const totalMentions = Object.values(mentionCounts ?? {}).reduce(
    (a, b) => a + b,
    0
  );

  return (
    <div className="relative mx-auto max-w-400 px-6 pb-20">
      <PageHeader eyebrow="Entity" value={`${totalMentions} mentions`} />

      {/* identity header */}
      <div className="mt-4 flex flex-col gap-4 rounded-2xl border border-border bg-muted/40 p-6 backdrop-blur-2xl">
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
                  detail={
                    (detail?.selectorKind as string) ??
                    (detail?.selector_kind as string) ??
                    null
                  }
                />
                {entity.aliases.length > 0 && (
                  <span className="text-xs text-muted-foreground">
                    aka {entity.aliases.join(", ")}
                  </span>
                )}
              </div>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditOpen(true)}
            className="h-9 gap-2 border-border/50 bg-muted/40 text-[10px] font-bold uppercase tracking-widest text-muted-foreground hover:text-primary"
          >
            <Pencil size={14} /> Edit
          </Button>
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
          personId={entity.personId}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-8 lg:col-span-2">
          <Section
            title="Mentions"
            icon={<ScanFace size={14} className="text-primary" />}
          >
            <EntityMentionsByFile
              entityId={id}
              emptyLabel="No mentions recorded for this entity yet."
            />
          </Section>

          {relatedEntities.length > 0 && (
            <Section title="Related entities">
              <ul className="mb-4 flex flex-wrap gap-2">
                {relatedEntities.map((r, i) => {
                  const m = ENTITY_TYPE_META[r.entity.entityType];
                  return (
                    <li key={`${r.entity.id}-${i}`}>
                      <Link
                        href={`/entities/${r.entity.id}`}
                        className="flex items-center gap-1.5 rounded-lg border border-border bg-muted/40 px-2.5 py-1.5 text-xs hover:border-primary/40"
                      >
                        <m.Icon size={12} className={m.textClass} />
                        <span className="font-medium text-foreground">
                          {r.entity.displayName}
                        </span>
                        <span className="text-[10px] uppercase text-muted-foreground">
                          {r.direction === "out" ? "" : "← "}
                          {r.relationshipType.replace(/_/g, " ")}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
              <EntityGraph focusEntityId={id} depth={1} compact />
            </Section>
          )}

          {selectors.length > 0 && (
            <Section title="Selectors">
              <ul className="flex flex-wrap gap-2">
                {selectors.map((s) => (
                  <li key={s.id}>
                    <Link
                      href={`/entities/${s.id}`}
                      className="rounded-lg border border-pink-500/30 bg-pink-500/10 px-2.5 py-1.5 font-mono text-xs text-pink-300 hover:border-pink-400/60"
                    >
                      {s.displayName}
                    </Link>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>

        <div className="h-fit rounded-2xl border border-border bg-muted/40 p-5 backdrop-blur-2xl">
          <CommentSection commentableType="entity" commentableId={id} />
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
  personId,
}: {
  entityType: string;
  detail?: EntityDetail | null;
  personId?: string;
}) {
  const g = (camel: string, snake: string) =>
    (detail?.[camel] as string | number | undefined) ??
    (detail?.[snake] as string | number | undefined);

  if (entityType === "person") {
    return (
      <div className="rounded-lg border border-border/60 bg-background/40 p-3">
        <DetailRow
          label="Date of birth"
          value={g("dateOfBirth", "date_of_birth") as string}
        />
        <DetailRow label="Sex" value={detail?.sex as string} />
        <DetailRow label="Nationality" value={detail?.nationality as string} />
        <Link
          href={`/persons/${personId ?? ""}`}
          className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
        >
          Edit in Persons <ExternalLink size={11} />
        </Link>
      </div>
    );
  }
  if (entityType === "organization") {
    return (
      <div className="rounded-lg border border-border/60 bg-background/40 p-3">
        <DetailRow
          label="Legal name"
          value={g("legalName", "legal_name") as string}
        />
        <DetailRow
          label="Org type"
          value={g("orgType", "org_type") as string}
        />
        <DetailRow label="Country" value={detail?.country as string} />
      </div>
    );
  }
  if (entityType === "location") {
    const lat = g("latitude", "latitude");
    const lon = g("longitude", "longitude");
    return (
      <div className="rounded-lg border border-border/60 bg-background/40 p-3">
        <DetailRow
          label="Address"
          value={g("addressText", "address_text") as string}
        />
        <DetailRow label="Country" value={detail?.country as string} />
        <DetailRow
          label="Admin area"
          value={g("adminArea", "admin_area") as string}
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
          value={(g("selectorKind", "selector_kind") as string)?.replace(
            /_/g,
            " "
          )}
        />
        <DetailRow
          label="Normalized"
          value={g("normalizedValue", "normalized_value") as string}
        />
        <DetailRow label="Raw" value={g("rawValue", "raw_value") as string} />
        <DetailRow
          label="Region"
          value={g("regionHint", "region_hint") as string}
        />
      </div>
    );
  }
  return null;
}
