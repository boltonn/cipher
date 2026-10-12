"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useDeleteRelationship,
  useReviewRelationship,
  useUpdateRelationship,
} from "@/features/email-signatures/hooks/use-email-signatures";
import type { MentionRelationship } from "@/features/email-signatures/types";
import {
  ENTITY_TYPE_META,
  SELECTOR_TYPE_META,
} from "@/features/entities/components/entity-type-meta";
import { useEntity } from "@/features/entities/hooks/use-entities";
import type {
  Mention,
  OntologyRelationship,
  RelationshipType,
} from "@/features/entities/types";
import { cn } from "@/lib/utils";
import {
  ArrowLeftRight,
  ArrowRight,
  Check,
  HelpCircle,
  RotateCcw,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

/** Relationship types the ontology allows from `src`'s type to `dst`'s (untyped ends allow all). */
export function allowedRelationships(
  relationships: OntologyRelationship[],
  src?: Mention,
  dst?: Mention
): OntologyRelationship[] {
  return relationships.filter(
    (r) =>
      (!src?.entityType || r.allowedSrc.includes(src.entityType)) &&
      (!dst?.entityType || r.allowedDst.includes(dst.entityType))
  );
}

/** Types whose edge carries a role (`employedBy` -> "Assistant Director"). */
export function takesRole(relationship?: OntologyRelationship) {
  return (
    !!relationship &&
    (relationship.roles.length > 0 ||
      ["employedBy", "memberOf"].includes(relationship.relationshipType))
  );
}

const oneLine = (text: string) => text.replace(/\s+/g, " ").trim();
const sameText = (a: string, b: string) =>
  oneLine(a).toLowerCase() === oneLine(b).toLowerCase();

export function MentionEnd({ mention }: { mention: Mention }) {
  const { data: entity } = useEntity(mention.entityId ?? undefined);
  const Icon =
    mention.entityType === "selector" && mention.selectorType
      ? SELECTOR_TYPE_META[mention.selectorType].Icon
      : mention.entityType
        ? ENTITY_TYPE_META[mention.entityType].Icon
        : HelpCircle;
  const meta = mention.entityType ? ENTITY_TYPE_META[mention.entityType] : null;
  const resolved = !!mention.entityId;
  const surface = oneLine(mention.surfaceText);
  return (
    <span
      className={cn(
        "inline-flex min-w-0 max-w-full shrink items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium",
        resolved && meta
          ? cn(meta.bgClass, meta.textClass, meta.borderClass)
          : "border-dashed border-annotation/50 bg-annotation/10 text-annotation"
      )}
      title={
        resolved
          ? `${mention.surfaceText} → ${entity?.displayName ?? "entity"}`
          : `${mention.surfaceText} -- not resolved yet: click it in the email signature`
      }
    >
      <Icon size={11} className="shrink-0" />
      <span className="truncate">{surface}</span>
      {resolved &&
        entity &&
        mention.entityType !== "selector" &&
        !sameText(entity.displayName, surface) && (
          <span className="truncate font-normal opacity-70">
            = {entity.displayName}
          </span>
        )}
    </span>
  );
}

/** Review outcome, or who proposed it when that isn't the email-signature reader. */
function Status({ relationship: r }: { relationship: MentionRelationship }) {
  if (r.isAccepted === true)
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-primary">
        <Check size={11} /> Accepted
      </span>
    );
  if (r.isAccepted === false || r.dateReviewed)
    return (
      <span className="text-[11px] text-muted-foreground">
        {r.isAccepted === false ? "Rejected" : "Reviewed"}
      </span>
    );
  if (r.extractor === "manual")
    return <span className="text-[11px] text-primary">Added by you</span>;
  if (r.extractor && r.extractor !== "signature")
    return (
      <span className="text-[11px] text-annotation">
        Proposed by {r.extractor}
      </span>
    );
  return null;
}

/**
 * One relationship between two labels of the email signature: the two ends (their colour
 * says whether each is resolved), the type, the role for an employment-like edge, and
 * the review actions. Accepting needs both ends resolved -- it adds the entity edge.
 */
export function RelationshipRow({
  relationship: r,
  relationships,
  onHover,
}: {
  relationship: MentionRelationship;
  relationships: OntologyRelationship[];
  onHover: (mentionIds: string[] | undefined) => void;
}) {
  const update = useUpdateRelationship();
  const review = useReviewRelationship();
  const remove = useDeleteRelationship();
  const busy = update.isPending || review.isPending || remove.isPending;
  const isPending = r.dateReviewed == null;
  const spec = relationships.find(
    (o) => o.relationshipType === r.relationshipType
  );
  const options = allowedRelationships(relationships, r.src, r.dst);
  const unresolved = [r.src, r.dst].filter((m) => !m.entityId);
  const commitRole = (value: string) => {
    if (value.trim() === (r.attributes.role ?? "")) return;
    update.mutate({
      id: r.id,
      patch: { attributes: { ...r.attributes, role: value.trim() } },
    });
  };

  const role = takesRole(spec) && (
    <Input
      key={r.attributes.role ?? ""}
      defaultValue={r.attributes.role ?? ""}
      disabled={!isPending || busy}
      placeholder="Role or title (optional)"
      aria-label="Role"
      onBlur={(e) => commitRole(e.currentTarget.value)}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      className="h-7 w-64 bg-muted/30 text-xs"
    />
  );
  const resolveFirst = isPending && unresolved.length > 0 && (
    <span className="text-[11px] text-muted-foreground">
      To accept, resolve{" "}
      {unresolved.map((m) => `“${oneLine(m.surfaceText)}”`).join(" and ")} in
      the email signature
    </span>
  );

  return (
    <li
      onMouseEnter={() => onHover([r.srcMentionId, r.dstMentionId])}
      onMouseLeave={() => onHover(undefined)}
      className={cn(
        "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 px-3 py-2 text-xs hover:bg-muted/30",
        r.isAccepted === false && "opacity-60"
      )}
    >
      <div className="flex min-w-0 items-center gap-1.5">
        {r.extractor !== "manual" && isPending && (
          <Sparkles
            size={12}
            className="shrink-0 text-annotation"
            aria-label="Proposed by the email-signature reader"
          />
        )}
        <MentionEnd mention={r.src} />
        {isPending ? (
          <Select
            value={r.relationshipType}
            onValueChange={(value) =>
              update.mutate({
                id: r.id,
                patch: { relationshipType: value as RelationshipType },
              })
            }
            disabled={busy}
          >
            <SelectTrigger className="h-6 w-auto shrink-0 gap-1 border-border/60 bg-muted/40 px-2 text-[11px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(options.some(
                (o) => o.relationshipType === r.relationshipType
              ) || !spec
                ? options
                : [spec, ...options]
              ).map((o) => (
                <SelectItem
                  key={o.relationshipType}
                  value={o.relationshipType}
                  className="text-xs"
                >
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {spec?.label ?? r.relationshipType}
          </span>
        )}
        <ArrowRight size={11} className="shrink-0 text-muted-foreground" />
        <MentionEnd mention={r.dst} />
      </div>

      <span className="flex items-center gap-0.5">
        <Status relationship={r} />
        {isPending ? (
          <>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                update.mutate({ id: r.id, patch: { reverse: true } })
              }
              className="h-7 w-7 p-0 text-muted-foreground"
              title="Swap the two ends"
              aria-label="Swap the two ends"
            >
              <ArrowLeftRight size={12} />
            </Button>
            {r.extractor === "manual" ? (
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => remove.mutate(r.id)}
                className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
              >
                <Trash2 size={12} /> Delete
              </Button>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => review.mutate({ id: r.id, action: "reject" })}
                className="h-7 gap-1 px-2 text-xs text-muted-foreground"
              >
                <X size={12} /> Reject
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              disabled={busy || unresolved.length > 0}
              onClick={() => review.mutate({ id: r.id, action: "accept" })}
              className="h-7 gap-1 px-2 text-xs"
              title={
                unresolved.length
                  ? "Resolve both ends in the email signature first"
                  : "Add this relationship to the graph"
              }
            >
              <Check size={12} /> Accept
            </Button>
          </>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => review.mutate({ id: r.id, action: "reopen" })}
            className="h-7 gap-1 px-2 text-xs text-muted-foreground"
          >
            <RotateCcw size={12} /> Reopen
          </Button>
        )}
      </span>

      {(role || resolveFirst) && (
        <div className="col-span-2 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 pl-[18px]">
          {role}
          {resolveFirst}
        </div>
      )}
    </li>
  );
}
