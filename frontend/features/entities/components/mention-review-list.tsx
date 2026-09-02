"use client";

import { Pagination } from "@/components/pagination";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntitySearch } from "@/features/entities/hooks/use-entities";
import {
  useDismissNameGroup,
  useResolveNameGroup,
  useUnresolvedNameGroups,
} from "@/features/entities/hooks/use-mentions";
import type {
  EntityType,
  UnresolvedNameGroup,
} from "@/features/entities/types";
import { useMe } from "@/features/users/hooks/use-me";
import { Building2, Loader2, MapPin, User, X } from "lucide-react";
import { useState } from "react";

const PAGE_SIZE = 25;

export function MentionReviewList({ datasetId }: { datasetId: string }) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const { data, isPending, isFetching } = useUnresolvedNameGroups(
    datasetId,
    q,
    page
  );

  const groups = data?.data ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-3">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Names pulled from evidence (right now: email <code>From/To/Cc/Bcc</code>{" "}
        display names) that aren&apos;t yet tied to an entity. Each row is one
        distinct name — every email it appeared in is counted together. Say
        whether it&apos;s a <b>person</b> or an <b>organization</b> (or attach
        it to one that already exists); that creates/links the entity and
        resolves all of its mentions at once. <b>Not an entity</b> discards
        them.
      </p>

      <SearchInput
        value={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        ariaLabel="Search unresolved names"
        placeholder="Search names…"
      />

      {isPending ? (
        <div className="flex items-center gap-2 py-10 text-xs text-muted-foreground">
          <Loader2 size={14} className="animate-spin" /> Loading names…
        </div>
      ) : groups.length === 0 ? (
        <p className="py-10 text-center text-xs italic text-muted-foreground">
          {q
            ? "No unresolved names match."
            : "Nothing to review — every name is resolved."}
        </p>
      ) : (
        <>
          <ul className="divide-y divide-border/60 rounded-xl border border-border">
            {groups.map((g) => (
              <NameRow
                key={g.normalizedValue}
                group={g}
                datasetId={datasetId}
              />
            ))}
          </ul>
          <Pagination
            currentPage={page}
            totalItems={total}
            itemsPerPage={PAGE_SIZE}
            onPageChange={setPage}
            isLoading={isFetching}
          />
        </>
      )}
    </div>
  );
}

const TYPE_BUTTONS: { type: EntityType; label: string; Icon: typeof User }[] = [
  { type: "person", label: "Person", Icon: User },
  { type: "organization", label: "Organization", Icon: Building2 },
  { type: "location", label: "Location", Icon: MapPin },
];

function NameRow({
  group,
  datasetId,
}: {
  group: UnresolvedNameGroup;
  datasetId: string;
}) {
  const me = useMe().data;
  const reviewedBy = me?.name ?? me?.id ?? "analyst";
  const resolve = useResolveNameGroup();
  const dismiss = useDismissNameGroup();
  const busy = resolve.isPending || dismiss.isPending;

  const asType = (entityType: EntityType) =>
    resolve.mutate({
      datasetId,
      normalizedValue: group.normalizedValue,
      entityType,
      displayName: group.surface,
      reviewedBy,
    });

  return (
    <li className="flex flex-col gap-2 p-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="rounded bg-annotation/15 px-1 font-mono text-foreground">
            {group.surface}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {group.mentionCount.toLocaleString()} mention
            {group.mentionCount === 1 ? "" : "s"} ·{" "}
            {group.fileCount.toLocaleString()} file
            {group.fileCount === 1 ? "" : "s"}
          </span>
          {group.suggestedType && (
            <span className="rounded-full border border-border/60 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-muted-foreground">
              looks like {group.suggestedType}
            </span>
          )}
        </p>
        {group.sampleContext && (
          <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">
            …{group.sampleContext}…
          </p>
        )}
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
        {TYPE_BUTTONS.map(({ type, label, Icon }) => (
          <Button
            key={type}
            size="sm"
            variant={group.suggestedType === type ? "default" : "outline"}
            disabled={busy}
            onClick={() => asType(type)}
            className="h-7 gap-1 text-[11px]"
          >
            <Icon size={12} />
            {label}
          </Button>
        ))}

        <AttachExisting
          datasetId={datasetId}
          surface={group.surface}
          disabled={busy}
          onPick={(entityId, entityType) =>
            resolve.mutate({
              datasetId,
              normalizedValue: group.normalizedValue,
              entityType,
              entityId,
              reviewedBy,
            })
          }
        />

        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() =>
            dismiss.mutate({
              datasetId,
              normalizedValue: group.normalizedValue,
            })
          }
          className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
        >
          <X size={12} />
          Not an entity
        </Button>
      </div>
    </li>
  );
}

function AttachExisting({
  datasetId,
  surface,
  disabled,
  onPick,
}: {
  datasetId: string;
  surface: string;
  disabled?: boolean;
  onPick: (entityId: string, entityType: EntityType) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(surface.trim().slice(0, 80));
  const { data: results, isFetching } = useEntitySearch(
    { datasetId, q: query },
    open
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled}
          className="h-7 text-[11px]"
        >
          Attach…
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 border-border bg-popover p-0" align="end">
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Find an existing entity…"
            className="text-xs"
          />
          <CommandList className="max-h-48">
            {isFetching && (
              <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-muted-foreground">
                <Loader2 size={12} className="animate-spin" /> Searching…
              </div>
            )}
            {!isFetching && (results?.length ?? 0) === 0 && (
              <CommandEmpty className="py-3 text-[11px] text-muted-foreground">
                No matches.
              </CommandEmpty>
            )}
            <CommandGroup>
              {results?.map((r) => {
                const meta = ENTITY_TYPE_META[r.entityType];
                return (
                  <CommandItem
                    key={r.id}
                    value={r.id}
                    onSelect={() => {
                      onPick(r.id, r.entityType);
                      setOpen(false);
                    }}
                    className="gap-2 text-xs"
                  >
                    <meta.Icon size={12} className={meta.textClass} />
                    <span className="flex-1 truncate">{r.displayName}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
