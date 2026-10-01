"use client";

import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { EntityMergeList } from "@/features/entities/components/entity-merge-list";
import { EntityPicker } from "@/features/entities/components/entity-picker";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntityList } from "@/features/entities/hooks/use-entities";
import {
  useMergeEntities,
  usePromoteEntities,
  usePromoteEntity,
  useRetypeEntities,
} from "@/features/entities/hooks/use-entity-matches";
import type { EntityListItem, EntityType } from "@/features/entities/types";
import { cn } from "@/lib/utils";
import {
  BadgeCheck,
  ChevronDown,
  GitMerge,
  Loader2,
  Pencil,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

const PAGE_SIZE = 25;
const TYPES: { value: EntityType | undefined; label: string }[] = [
  { value: undefined, label: "All" },
  { value: "person", label: "People" },
  { value: "organization", label: "Organizations" },
  { value: "location", label: "Locations" },
];

/**
 * The Verify step -- auto-created (provisional) entities, biggest first. The resolver
 * creates one when a typed name group matches nothing; verify it before resolving more
 * names to it: keep it (Verify), fix its name, or merge it into the entity it duplicates.
 * Tick rows (across pages) to Verify them all or merge them into one.
 */
export function EntityVerifyList({ datasetId }: { datasetId: string }) {
  const [query, setQuery] = useState("");
  const [entityType, setEntityType] = useState<EntityType | undefined>();
  const [page, setPage] = useState(1);
  const { data, isPending, isFetching } = useEntityList({
    datasetId,
    provisional: true,
    query: query || undefined,
    entityType,
    // searching ranks real hits (exact, prefix, substring) above fuzzy typo matches
    sortBy: query ? "relevance" : "mention_count",
    sortOrder: "desc",
    limit: PAGE_SIZE,
    page,
  });
  const entities = data?.data ?? [];
  const [selected, setSelected] = useState<Record<string, EntityListItem>>({});
  const selectedList = Object.values(selected);
  const allOnPage =
    entities.length > 0 && entities.every((e) => selected[e.id]);
  const someOnPage = entities.some((e) => selected[e.id]);
  const clearSelection = () => setSelected({});
  const toggle = (entity: EntityListItem, checked: boolean) =>
    setSelected((prev) => {
      const next = { ...prev };
      if (checked) next[entity.id] = entity;
      else delete next[entity.id];
      return next;
    });
  const togglePage = (checked: boolean) =>
    setSelected((prev) => {
      const next = { ...prev };
      for (const e of entities) {
        if (checked) next[e.id] = e;
        else delete next[e.id];
      }
      return next;
    });

  return (
    <div className="space-y-3">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        <b>Auto-created entities</b> were made by the resolver for names that
        matched nothing. Check the big ones before resolving more names to them:{" "}
        <b>Verify</b> keeps it as a real entity, <b>Edit</b> fixes its name, and
        a <b>merge</b> folds a duplicate (e.g. “Dell Inc” into “Dell”) into the
        entity it repeats. Tick rows to <b>Verify</b> or <b>Merge</b> several at
        once — search “Dell” to gather its variants.
      </p>

      <EntityMergeList datasetId={datasetId} />

      <div className="flex flex-wrap items-center gap-2">
        <SearchBarShell
          isActive={isFetching}
          icon={<Search size={16} strokeWidth={1.5} />}
          className="w-auto min-w-64 flex-1"
        >
          <SearchInput
            value={query}
            onSearch={(value) => {
              setQuery(value);
              setPage(1);
            }}
            ariaLabel="Search auto-created entities"
            placeholder="Search auto-created entities…"
          />
        </SearchBarShell>
        <ButtonGroup>
          {TYPES.map((t) => (
            <Button
              key={t.label}
              size="sm"
              variant={entityType === t.value ? "default" : "outline"}
              className="h-7 text-[11px]"
              onClick={() => {
                setEntityType(t.value);
                setPage(1);
              }}
            >
              {t.label}
            </Button>
          ))}
        </ButtonGroup>
      </div>

      {selectedList.length > 0 && (
        <SelectionBar
          selected={selectedList}
          datasetId={datasetId}
          onDone={clearSelection}
        />
      )}

      {isPending ? (
        <div className="flex items-center gap-2 py-10 text-xs text-muted-foreground">
          <Loader2 size={14} className="animate-spin" /> Loading entities…
        </div>
      ) : entities.length === 0 ? (
        <p className="py-10 text-center text-xs italic text-muted-foreground">
          {query || entityType
            ? "No auto-created entities match."
            : "Nothing to verify — no auto-created entities."}
        </p>
      ) : (
        <>
          <ul className="divide-y divide-border/60 rounded-xl border border-border">
            <li className="flex items-center gap-3 bg-muted/40 px-3 py-1.5 text-[11px] text-muted-foreground">
              <Checkbox
                checked={
                  allOnPage ? true : someOnPage ? "indeterminate" : false
                }
                onCheckedChange={(checked) => togglePage(checked === true)}
                aria-label="Select all on this page"
              />
              Select all on this page
            </li>
            {entities.map((entity) => (
              <VerifyRow
                key={entity.id}
                entity={entity}
                checked={!!selected[entity.id]}
                onCheckedChange={(checked) => toggle(entity, checked)}
              />
            ))}
          </ul>
          <Pagination
            currentPage={page}
            totalItems={data?.total ?? 0}
            itemsPerPage={PAGE_SIZE}
            onPageChange={setPage}
            isLoading={isFetching}
          />
        </>
      )}
    </div>
  );
}

function SelectionBar({
  selected,
  datasetId,
  onDone,
}: {
  selected: EntityListItem[];
  datasetId: string;
  onDone: () => void;
}) {
  const verify = usePromoteEntities(onDone);
  const merge = useMergeEntities(onDone);
  const [mergeOpen, setMergeOpen] = useState(false);
  const types = new Set(selected.map((e) => e.entityType));
  const mergeType = types.size === 1 ? selected[0].entityType : undefined;
  const busy = verify.isPending || merge.isPending;
  const mergeInto = (targetId: string, targetName: string) => {
    setMergeOpen(false);
    merge.mutate(
      {
        targetId,
        sourceIds: selected.map((e) => e.id).filter((id) => id !== targetId),
      },
      { onSuccess: () => toast.success(`Merged into ${targetName}`) }
    );
  };

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-1.5 text-[11px]">
      <b className="text-foreground">
        {selected.length.toLocaleString()} selected
      </b>
      <Button
        size="sm"
        variant="ghost"
        className="h-6 gap-1 px-2 text-[11px]"
        onClick={onDone}
        disabled={busy}
      >
        <X size={11} /> Clear
      </Button>
      <div className="ml-auto flex items-center gap-1.5">
        <Popover open={mergeOpen} onOpenChange={setMergeOpen}>
          <PopoverTrigger asChild>
            <Button
              size="sm"
              variant="outline"
              disabled={busy || !mergeType}
              className="h-7 gap-1 text-[11px]"
              title={
                mergeType
                  ? "Fold the selected entities into one"
                  : "Select entities of one type to merge"
              }
            >
              <GitMerge size={12} /> Merge {selected.length}…
            </Button>
          </PopoverTrigger>
          <PopoverContent
            className="w-80 space-y-2 border-border bg-popover p-3 text-xs"
            align="end"
          >
            <p className="text-[11px] text-muted-foreground">
              Keep which one? The others fold into it — their mentions move over
              and their names become aliases.
            </p>
            <ul className="max-h-48 space-y-1 overflow-y-auto">
              {[...selected]
                .sort((a, b) => b.mentionCount - a.mentionCount)
                .map((e) => (
                  <li key={e.id}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-muted"
                      onClick={() => mergeInto(e.id, e.displayName)}
                    >
                      <span className="flex-1 truncate font-medium">
                        {e.displayName}
                      </span>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {e.mentionCount.toLocaleString()} mentions
                      </span>
                    </button>
                  </li>
                ))}
            </ul>
            {mergeType && (
              <div className="space-y-1 border-t border-border/60 pt-2">
                <p className="text-[11px] text-muted-foreground">
                  Or merge all into an existing entity
                </p>
                <EntityPicker
                  datasetId={datasetId}
                  entityTypes={[mergeType]}
                  onSelect={(id, name) => mergeInto(id, name ?? "entity")}
                  placeholder="Find an entity…"
                />
              </div>
            )}
          </PopoverContent>
        </Popover>
        <ChangeTypeMenu entities={selected} onDone={onDone}>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            className="h-7 gap-1 text-[11px]"
          >
            Change type <ChevronDown size={12} />
          </Button>
        </ChangeTypeMenu>
        <Button
          size="sm"
          disabled={busy}
          onClick={() =>
            verify.mutate(
              selected.map((e) => e.id),
              {
                onSuccess: ({ promoted }) =>
                  toast.success(`Verified ${promoted.toLocaleString()}`),
              }
            )
          }
          className="h-7 gap-1 text-[11px]"
          title="Keep each as a real entity; dismisses their possible-duplicate suggestions"
        >
          <BadgeCheck size={12} /> Verify {selected.length}
        </Button>
      </div>
    </div>
  );
}

const RETYPE_TARGETS: EntityType[] = ["person", "organization"];

/** Person <-> organization for auto-created entities -- e.g. `Idylwood Towers` minted as a person. */
function ChangeTypeMenu({
  entities,
  onDone,
  children,
}: {
  entities: EntityListItem[];
  onDone?: () => void;
  children: React.ReactNode;
}) {
  const retype = useRetypeEntities(onDone);
  const current = new Set(entities.map((e) => e.entityType));

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={retype.isPending}>
        {children}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="text-xs">
        <DropdownMenuLabel className="text-[11px] text-muted-foreground">
          Change type to
        </DropdownMenuLabel>
        {RETYPE_TARGETS.filter(
          (type) => !(current.size === 1 && current.has(type))
        ).map((type) => {
          const { Icon, label, textClass } = ENTITY_TYPE_META[type];
          return (
            <DropdownMenuItem
              key={type}
              className="gap-2 text-xs"
              onSelect={() =>
                retype.mutate(
                  { entityIds: entities.map((e) => e.id), entityType: type },
                  {
                    onSuccess: ({ retyped }) =>
                      toast.success(
                        retyped === 1
                          ? `${entities[0].displayName} is now ${label.toLowerCase()}`
                          : `Changed ${retyped} to ${label.toLowerCase()}`
                      ),
                  }
                )
              }
            >
              <Icon size={12} className={textClass} /> {label}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function VerifyRow({
  entity,
  checked,
  onCheckedChange,
}: {
  entity: EntityListItem;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  const verify = usePromoteEntity();
  const meta = ENTITY_TYPE_META[entity.entityType];

  return (
    <li
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-1.5 p-3",
        checked && "bg-primary/5"
      )}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={(value) => onCheckedChange(value === true)}
        aria-label={`Select ${entity.displayName}`}
      />
      <div className="flex min-w-0 flex-1 items-center gap-2 text-xs">
        {meta?.Icon && (
          <meta.Icon
            size={13}
            className={cn("shrink-0", meta.textClass)}
            aria-hidden
          />
        )}
        <Link
          href={`/entities/${entity.id}`}
          className="truncate font-medium text-foreground hover:underline"
        >
          {entity.displayName}
        </Link>
        <ChangeTypeMenu entities={[entity]}>
          <button
            type="button"
            className="inline-flex shrink-0 items-center gap-0.5 rounded px-1 text-[11px] uppercase tracking-wide text-muted-foreground/70 hover:bg-muted hover:text-foreground"
            title="Change type"
          >
            {meta?.label} <ChevronDown size={10} />
          </button>
        </ChangeTypeMenu>
        <span className="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-annotation/40 px-1 text-[11px] text-annotation">
          <Sparkles size={9} /> auto-created
        </span>
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {entity.mentionCount.toLocaleString()} mention
          {entity.mentionCount === 1 ? "" : "s"} ·{" "}
          {entity.fileCount.toLocaleString()} file
          {entity.fileCount === 1 ? "" : "s"}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button
          asChild
          size="sm"
          variant="outline"
          className="h-7 gap-1 text-[11px]"
        >
          <Link href={`/entities/${entity.id}`}>
            <Pencil size={12} /> Edit
          </Link>
        </Button>
        <Button
          size="sm"
          disabled={verify.isPending}
          onClick={() => verify.mutate(entity.id)}
          className="h-7 gap-1 text-[11px]"
          title="Keep it as a real entity; dismisses its possible-duplicate suggestions"
        >
          <BadgeCheck size={12} /> Verify
        </Button>
      </div>
    </li>
  );
}
