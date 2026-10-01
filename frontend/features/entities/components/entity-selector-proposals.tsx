"use client";

import { Button } from "@/components/ui/button";
import { useLinkSelector, useSelectorEvidence } from "@/features/entities/hooks/use-entities";
import type { SelectorEvidence } from "@/features/entities/types";
import { AtSign, Check, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * "Suggested from chat" -- addresses the assistant proposed as belonging to this
 * entity (`?propose=id,id`). Nothing is linked until the analyst confirms each one
 * here, with the evidence in view: how often it's used, under which names, and who
 * it's linked to now. Moving an address off another entity is an explicit choice.
 */
export function EntitySelectorProposals({ entityId, entityName }: { entityId: string; entityName: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const proposed = (search.get("propose") ?? "").split(",").filter(Boolean);
  const { data: evidence, isPending } = useSelectorEvidence(entityId, proposed);

  // Resolved or dismissed rows leave the URL, so the proposal can't be re-applied by a reload.
  const drop = (selectorId: string) => {
    const rest = proposed.filter((id) => id !== selectorId);
    const params = new URLSearchParams(search);
    if (rest.length) params.set("propose", rest.join(","));
    else params.delete("propose");
    const query = params.toString();
    router.replace(`${pathname}${query ? `?${query}` : ""}`, { scroll: false });
  };
  const link = useLinkSelector(entityId, drop);

  if (proposed.length === 0 || isPending || !evidence?.length) return null;

  return (
    <div className="rounded-lg border border-annotation/30 bg-annotation/[0.04] p-3">
      <p className="flex items-center gap-2 text-xs font-medium">
        <Sparkles size={13} className="text-annotation" />
        Suggested from chat
      </p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        The assistant thinks these addresses belong to {entityName}. Nothing has changed yet — review the
        mentions and accept each one.
      </p>
      <ul className="mt-2 space-y-1.5">
        {evidence.map((row) => (
          <ProposalRow
            key={row.entityId}
            row={row}
            entityId={entityId}
            pending={link.isPending && link.variables?.selectorId === row.entityId}
            onLink={(moveFrom) => link.mutate({ selectorId: row.entityId, moveFrom })}
            onDismiss={() => drop(row.entityId)}
          />
        ))}
      </ul>
    </div>
  );
}

function ProposalRow({
  row,
  entityId,
  pending,
  onLink,
  onDismiss,
}: {
  row: SelectorEvidence;
  entityId: string;
  pending: boolean;
  onLink: (moveFrom: string[]) => void;
  onDismiss: () => void;
}) {
  const alreadyLinked = row.linkedTo.some((owner) => owner.entityId === entityId);
  const others = row.linkedTo.filter((owner) => owner.entityId !== entityId);

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border border-border bg-background/60 px-3 py-2">
      <div className="min-w-0 flex-1">
        <Link
          href={`/entities/${row.entityId}`}
          className="flex items-center gap-1.5 text-xs font-medium text-foreground hover:text-primary"
        >
          <AtSign size={12} className="shrink-0 text-muted-foreground" />
          <span className="truncate">{row.displayName}</span>
        </Link>
        <p className="mt-0.5 text-[11px] text-muted-foreground [overflow-wrap:anywhere]">
          {row.emailCount.toLocaleString()} email{row.emailCount === 1 ? "" : "s"}
          {row.names.length > 0 && <> · as {row.names.map((n) => `“${n}”`).join(", ")}</>}
        </p>
        <p className="mt-0.5 text-[11px]">
          {alreadyLinked ? (
            <span className="text-muted-foreground">Already a selector of this entity.</span>
          ) : others.length ? (
            <span className="text-destructive">
              Selector of{" "}
              {others.map((owner, index) => (
                <span key={owner.entityId}>
                  {index > 0 && ", "}
                  <Link href={`/entities/${owner.entityId}`} className="underline hover:no-underline">
                    {owner.displayName}
                  </Link>
                  <span className="text-muted-foreground"> ({owner.source.replace("_", " ")})</span>
                </span>
              ))}
            </span>
          ) : (
            <span className="text-muted-foreground">Not a selector of any entity.</span>
          )}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {!alreadyLinked && others.length > 0 && (
          <Button size="sm" variant="outline" className="h-7 text-[11px]" disabled={pending} onClick={() => onLink(others.map((o) => o.entityId))}>
            <Check size={12} /> Move here
          </Button>
        )}
        {!alreadyLinked && (
          <Button size="sm" className="h-7 text-[11px]" disabled={pending} onClick={() => onLink([])}>
            <Check size={12} /> {others.length ? "Also add here" : "Accept"}
          </Button>
        )}
        <Button size="sm" variant="ghost" className="h-7 text-[11px]" onClick={onDismiss}>
          <X size={12} /> {alreadyLinked ? "Done" : "Dismiss"}
        </Button>
      </div>
    </li>
  );
}
