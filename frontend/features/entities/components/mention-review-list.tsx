"use client";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntitySearch } from "@/features/entities/hooks/use-entities";
import {
  useDeleteMention,
  useResolveMention,
  useUnresolvedMentions,
} from "@/features/entities/hooks/use-mentions";
import { ENTITY_TYPES, type EntityType } from "@/features/entities/types";
import { useMe } from "@/features/users/hooks/use-me";
import { Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

export function MentionReviewList({ datasetId }: { datasetId: string }) {
  const { data, isPending } = useUnresolvedMentions(datasetId);

  if (isPending) {
    return (
      <div className="flex items-center gap-2 py-10 text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" /> Loading review queue…
      </div>
    );
  }

  const mentions = data?.data ?? [];
  if (mentions.length === 0) {
    return (
      <p className="py-10 text-center text-xs italic text-muted-foreground">
        Nothing to review — every mention is resolved.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border/60 rounded-xl border border-border">
      {mentions.map((m) => (
        <li key={m.id} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs">
              <span className="rounded bg-annotation/15 px-1 font-mono text-foreground">
                {m.surfaceText}
              </span>{" "}
              {m.entityType && (
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  predicted {m.entityType}
                </span>
              )}
            </p>
            {m.context && (
              <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">…{m.context}…</p>
            )}
            {m.fileId && (
              <Link href={`/entities?file=${m.fileId}`} className="text-[10px] text-primary hover:underline">
                file {m.fileId.slice(0, 8)}
              </Link>
            )}
          </div>
          <MentionResolver
            mentionId={m.id}
            datasetId={datasetId}
            surface={m.surfaceText}
            predictedType={(m.entityType as EntityType) ?? "person"}
          />
        </li>
      ))}
    </ul>
  );
}

function MentionResolver({
  mentionId,
  datasetId,
  surface,
  predictedType,
}: {
  mentionId: string;
  datasetId: string;
  surface: string;
  predictedType: EntityType;
}) {
  const [open, setOpen] = useState(false);
  const [entityType, setEntityType] = useState<EntityType>(predictedType);
  const [query, setQuery] = useState(surface.trim().slice(0, 80));
  const me = useMe().data;
  const reviewedBy = me?.name ?? me?.id ?? "analyst";

  const { data: results, isFetching } = useEntitySearch({ datasetId, q: query }, open);
  const resolve = useResolveMention(() => setOpen(false));
  const remove = useDeleteMention(() => setOpen(false));

  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button size="sm" className="h-7 gap-1 bg-primary text-[11px] hover:bg-primary">
            Resolve
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 border-border bg-popover p-2" align="end">
          <Select value={entityType} onValueChange={(v) => setEntityType(v as EntityType)}>
            <SelectTrigger className="mb-2 h-8 w-full bg-muted/40 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ENTITY_TYPES.map((t) => (
                <SelectItem key={t} value={t} className="text-xs">
                  {ENTITY_TYPE_META[t].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Command shouldFilter={false} className="rounded-md border border-border/60 bg-transparent">
            <CommandInput value={query} onValueChange={setQuery} placeholder="Search entities…" className="text-xs" />
            <CommandList className="max-h-40">
              {isFetching && (
                <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-muted-foreground">
                  <Loader2 size={12} className="animate-spin" /> Searching…
                </div>
              )}
              {!isFetching && (results?.length ?? 0) === 0 && (
                <CommandEmpty className="py-3 text-[11px] text-muted-foreground">No matches.</CommandEmpty>
              )}
              <CommandGroup>
                {results?.map((r) => {
                  const meta = ENTITY_TYPE_META[r.entityType];
                  return (
                    <CommandItem
                      key={r.id}
                      value={r.id}
                      onSelect={() =>
                        resolve.mutate({ id: mentionId, payload: { entityId: r.id, reviewedBy } })
                      }
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
          <Button
            size="sm"
            disabled={resolve.isPending}
            onClick={() =>
              resolve.mutate({
                id: mentionId,
                payload: {
                  reviewedBy,
                  newEntity: { datasetId, entityType, displayName: surface.trim().slice(0, 200) },
                },
              })
            }
            className="mt-2 h-8 w-full gap-1.5 bg-primary text-xs hover:bg-primary"
          >
            {resolve.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            Create {ENTITY_TYPE_META[entityType].label.toLowerCase()}
          </Button>
        </PopoverContent>
      </Popover>
      <Button
        size="icon"
        variant="ghost"
        disabled={remove.isPending}
        onClick={() => remove.mutate(mentionId)}
        className="h-7 w-7 text-muted-foreground hover:text-destructive"
        aria-label="Dismiss mention"
      >
        <Trash2 size={13} />
      </Button>
    </div>
  );
}
