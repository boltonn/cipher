"use client";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import {
  useCreateEntity,
  useEntity,
  useEntitySearch,
} from "@/features/entities/hooks/use-entities";
import {
  useCreateMention,
  useDeleteMention,
  useMentionResolution,
  useResolveMention,
  useResolveNameGroup,
  useUpdateMention,
  useValueResolvedEntities,
} from "@/features/entities/hooks/use-mentions";
import { foldName } from "@/features/entities/lib/fold-name";
import {
  SELECTOR_TYPES,
  SELECTOR_TYPE_LABELS,
  type EntityType,
  type Mention,
  type SelectorType,
} from "@/features/entities/types";
import { mentionSearchHref } from "@/features/search/links";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import { motion } from "motion/react";
import {
  ArrowRight,
  Check,
  Link2Off,
  Loader2,
  MousePointer2,
  Plus,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { createPortal } from "react-dom";

interface EntityMentionPopoverProps {
  /** Viewport rect of the selected / existing span to anchor the panel + highlight to. */
  rect: DOMRect;
  surface: string;
  datasetId: string;
  fileId: string;
  /** extracted_text row id (mention.mentionedId) */
  textId: string;
  startOffset: number;
  endOffset: number;
  /** present when editing an already-created mention rather than a fresh selection */
  existing?: Mention;
  onClose: () => void;
}

interface Suggestion {
  entityId: string;
  /** resolver score (0-1) */
  score?: number;
  /** how many other mentions of the same value already resolve here */
  count?: number;
}

type MentionTypeValue = Exclude<EntityType, "selector"> | `selector:${SelectorType}`;

const NAME_TYPES: { value: MentionTypeValue; label: string }[] = [
  { value: "person", label: "Person name" },
  { value: "organization", label: "Organization name" },
  { value: "location", label: "Location" },
];

function mentionTypeLabel(value: MentionTypeValue) {
  const selector = value.startsWith("selector:") ? (value.slice(9) as SelectorType) : undefined;
  return selector ? SELECTOR_TYPE_LABELS[selector] : NAME_TYPES.find((t) => t.value === value)?.label ?? value;
}

/**
 * Label a span of extracted text: draw a new mention, move an existing one's
 * boundaries ("Nick B |" -> "Nick B"), retype it, and resolve it -- to the
 * resolver's suggestions, to whatever the same value already resolves to
 * elsewhere, to a searched entity, or to a new one. An unresolved mention can
 * resolve its whole name group at once.
 */
export function EntityMentionPopover(props: EntityMentionPopoverProps) {
  const { rect, surface, datasetId, existing, onClose } = props;
  const trimmed = surface.trim();
  const isMove =
    !!existing && (existing.startOffset !== props.startOffset || existing.endOffset !== props.endOffset);

  const [mentionType, setMentionType] = useState<MentionTypeValue>(() =>
    existing?.entityType === "selector"
      ? `selector:${existing.selectorType ?? "email"}`
      : (existing?.entityType ?? "person")
  );
  const [entityType, selectorPart] = mentionType.split(":") as [EntityType, SelectorType | undefined];
  const selectorType = selectorPart ?? "email";
  const [query, setQuery] = useState(trimmed.slice(0, 80));
  const debouncedQuery = useDebounce(query, 250);
  const groupValue = existing && !existing.entityId ? existing.normalizedValue ?? undefined : undefined;
  const [applyToGroup, setApplyToGroup] = useState(false);

  const isSelector = entityType === "selector";
  const lookupValue = existing?.normalizedValue ?? (isSelector ? trimmed : foldName(trimmed));
  const { data: results, isFetching } = useEntitySearch({ datasetId, q: debouncedQuery });
  const { data: resolution } = useMentionResolution(isMove ? undefined : existing?.id);
  const { data: elsewhere } = useValueResolvedEntities(datasetId, isMove ? undefined : lookupValue);

  const suggestions = useMemo(() => {
    const out = new Map<string, Suggestion>();
    for (const c of resolution?.candidates ?? []) {
      if (c.status !== "rejected" && c.entityId !== existing?.entityId) {
        out.set(c.entityId, { entityId: c.entityId, score: c.similarityScore });
      }
    }
    for (const e of elsewhere ?? []) {
      if (e.entityId === existing?.entityId) continue;
      out.set(e.entityId, { ...out.get(e.entityId), entityId: e.entityId, count: e.count });
    }
    return [...out.values()].slice(0, 4);
  }, [resolution, elsewhere, existing?.entityId]);

  const done = () => onClose();
  const createEntity = useCreateEntity();
  const createMention = useCreateMention(done);
  const resolveMention = useResolveMention(done);
  const resolveGroup = useResolveNameGroup(done);
  const updateMention = useUpdateMention(done);
  const deleteMention = useDeleteMention(done);
  const busy =
    createEntity.isPending ||
    createMention.isPending ||
    resolveMention.isPending ||
    resolveGroup.isPending ||
    updateMention.isPending ||
    deleteMention.isPending;

  const span = {
    datasetId,
    mentionedType: "extracted_text" as const,
    mentionedId: props.textId,
    fileId: props.fileId,
    surfaceText: surface,
    entityType,
    selectorType: isSelector ? selectorType : null,
    startOffset: props.startOffset,
    endOffset: props.endOffset,
  };

  const attachExisting = (entityId: string, type: EntityType) => {
    if (existing && applyToGroup && groupValue) {
      resolveGroup.mutate({ datasetId, normalizedValue: groupValue, entityType: type, entityId });
    } else if (existing) {
      updateMention.mutate({ id: existing.id, payload: { entityId, entityType: type } });
    } else {
      createMention.mutate({ ...span, entityId, entityType: type });
    }
  };

  const createAndAttach = async () => {
    const displayName = trimmed.slice(0, 200) || query.trim();
    if (existing && applyToGroup && groupValue) {
      resolveGroup.mutate({ datasetId, normalizedValue: groupValue, entityType, displayName });
    } else if (existing) {
      resolveMention.mutate({ id: existing.id, payload: { newEntity: { datasetId, entityType, displayName } } });
    } else {
      const entity = await createEntity.mutateAsync({ datasetId, entityType, displayName });
      createMention.mutate({ ...span, entityId: entity.id });
    }
  };

  const typeChanged =
    !!existing && (existing.entityType !== entityType || (isSelector && existing.selectorType !== selectorType));

  // Radix owns dismissal (Escape, outside click) and layering, so nested Select menus stack above the panel.
  return (
    <Popover open onOpenChange={(open) => !open && onClose()}>
      {createPortal(
        <>
          <PointerHighlight rect={rect} />
          <PopoverAnchor asChild>
            <div
              className="pointer-events-none"
              style={{ position: "fixed", top: rect.top, left: rect.left, width: rect.width, height: rect.height }}
            />
          </PopoverAnchor>
        </>,
        document.body
      )}
      <PopoverContent
        align="start"
        side="bottom"
        sideOffset={10}
        collisionPadding={12}
        className="w-80 gap-0 p-3"
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        {isMove && existing ? (
          <>
            <p className="text-xs font-medium text-foreground">Adjust mention span</p>
            <div className="mt-2 flex items-center gap-2 rounded-md bg-muted/40 px-2 py-1.5 font-mono text-xs">
              <span className="truncate text-muted-foreground line-through">{existing.surfaceText}</span>
              <ArrowRight size={12} className="shrink-0 text-muted-foreground" />
              <span className="truncate text-foreground">{trimmed}</span>
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Keeps its type{existing.entityId ? " and entity" : ""}; it joins the “{foldName(trimmed)}” name group.
            </p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" variant="ghost" onClick={onClose} className="h-8 flex-1 text-xs">
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={busy || !trimmed}
                onClick={() =>
                  updateMention.mutate({
                    id: existing.id,
                    payload: { startOffset: props.startOffset, endOffset: props.endOffset, surfaceText: surface },
                  })
                }
                className="h-8 flex-1 gap-1.5 text-xs"
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                Move span
              </Button>
            </div>
          </>
        ) : (
          <>
            <MentionHeader existing={existing} surface={trimmed} />

            <Select value={mentionType} onValueChange={(v) => setMentionType(v as MentionTypeValue)}>
              <SelectTrigger className="mt-2 h-8 w-full bg-muted/40 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {NAME_TYPES.map(({ value, label }) => (
                  <SelectItem key={value} value={value} className="text-xs">
                    {label}
                  </SelectItem>
                ))}
                <SelectSeparator />
                <SelectGroup>
                  <SelectLabel className="text-[11px]">Selector</SelectLabel>
                  {SELECTOR_TYPES.map((t) => (
                    <SelectItem key={t} value={`selector:${t}`} className="text-xs">
                      {SELECTOR_TYPE_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            {typeChanged && existing && (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  updateMention.mutate({
                    id: existing.id,
                    payload: { entityType, selectorType: isSelector ? selectorType : null },
                  })
                }
                className="mt-2 h-7 w-full text-xs"
              >
                Change type to {mentionTypeLabel(mentionType).toLowerCase()}
              </Button>
            )}

            {suggestions.length > 0 && (
              <div className="mt-3">
                <p className="mb-1 flex items-center gap-1 text-[11px] font-medium text-annotation">
                  <Sparkles size={11} /> Suggested
                </p>
                <ul className="space-y-1">
                  {suggestions.map((s) => (
                    <SuggestionRow key={s.entityId} suggestion={s} disabled={busy} onPick={attachExisting} />
                  ))}
                </ul>
              </div>
            )}

            <Command shouldFilter={false} className="mt-3 rounded-md border border-border/60 bg-transparent">
              <CommandInput
                value={query}
                onValueChange={setQuery}
                placeholder="Search existing entities…"
                className="text-xs"
              />
              <CommandList className="max-h-36">
                {isFetching && (
                  <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-muted-foreground">
                    <Loader2 size={12} className="animate-spin" /> Searching…
                  </div>
                )}
                {!isFetching && (results?.length ?? 0) === 0 && (
                  <CommandEmpty className="py-3 text-[11px] text-muted-foreground">No matching entities.</CommandEmpty>
                )}
                <CommandGroup>
                  {results?.map((r) => {
                    const meta = ENTITY_TYPE_META[r.entityType];
                    return (
                      <CommandItem
                        key={r.id}
                        value={r.id}
                        onSelect={() => attachExisting(r.id, r.entityType)}
                        className="gap-2 text-xs"
                      >
                        <meta.Icon size={12} className={meta.textClass} />
                        <span className="flex-1 truncate">{r.displayName}</span>
                        <span className="text-[11px] text-muted-foreground">{r.matchReason}</span>
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>

            {groupValue && (
              <label className="mt-2 flex cursor-pointer items-center gap-2 text-[11px] text-muted-foreground">
                <Checkbox checked={applyToGroup} onCheckedChange={(v) => setApplyToGroup(v === true)} />
                Resolve every unresolved “{groupValue}” mention
              </label>
            )}

            <div className="mt-2 flex gap-2">
              {!existing && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy || !trimmed}
                  onClick={() => createMention.mutate(span)}
                  className="h-8 flex-1 text-xs"
                  title="Record the mention now and resolve it later"
                >
                  Save unresolved
                </Button>
              )}
              {!isSelector && (
                <Button
                  size="sm"
                  disabled={busy || !trimmed}
                  onClick={createAndAttach}
                  className="h-8 flex-1 gap-1.5 text-xs"
                >
                  {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                  New {ENTITY_TYPE_META[entityType].label.toLowerCase()}
                </Button>
              )}
            </div>

            <div className="mt-2 flex items-center gap-1 border-t border-border/60 pt-2">
              {lookupValue && (
                <Link
                  href={mentionSearchHref(lookupValue, datasetId)}
                  className="mr-auto flex h-7 items-center gap-1 rounded-md px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                  title="Every file with a mention of this value"
                >
                  <Search size={11} /> Every mention
                </Link>
              )}
              {existing?.entityId && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => updateMention.mutate({ id: existing.id, payload: { entityId: null } })}
                  className="h-7 gap-1 text-[11px] text-muted-foreground"
                >
                  <Link2Off size={11} /> Unresolve
                </Button>
              )}
              {existing && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => deleteMention.mutate(existing.id)}
                  className="h-7 gap-1 text-[11px] text-destructive hover:text-destructive"
                >
                  <Trash2 size={11} /> Delete
                </Button>
              )}
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}

function MentionHeader({ existing, surface }: { existing?: Mention; surface: string }) {
  const { data: entity } = useEntity(existing?.entityId ?? undefined);
  const isAnalyst = existing?.extractor === "manual";
  return (
    <div className="space-y-0.5">
      <p className="truncate text-xs">
        <span className="text-muted-foreground">{existing ? "Mention" : "New mention"}</span>{" "}
        <span className="font-mono text-foreground">“{surface}”</span>
      </p>
      {existing && (
        <p className="flex items-center gap-1.5 truncate text-[11px] text-muted-foreground">
          {existing.entityId ? (
            <Link href={`/entities/${existing.entityId}`} className="truncate text-foreground hover:underline">
              → {entity?.displayName ?? "…"}
            </Link>
          ) : (
            <span>Unresolved</span>
          )}
          <span aria-hidden>·</span>
          <span className={cn(!isAnalyst && "text-annotation")}>
            {isAnalyst ? "added by an analyst" : `found by ${existing.extractor ?? "extraction"}`}
          </span>
        </p>
      )}
    </div>
  );
}

function SuggestionRow({
  suggestion,
  disabled,
  onPick,
}: {
  suggestion: Suggestion;
  disabled: boolean;
  onPick: (entityId: string, type: EntityType) => void;
}) {
  const { data: entity } = useEntity(suggestion.entityId);
  const meta = entity ? ENTITY_TYPE_META[entity.entityType] : undefined;
  return (
    <li>
      <button
        type="button"
        disabled={disabled || !entity}
        onClick={() => entity && onPick(entity.id, entity.entityType)}
        className="flex w-full items-center gap-2 rounded-md border border-annotation/30 bg-annotation/5 px-2 py-1 text-left text-xs transition-colors hover:bg-annotation/10 disabled:opacity-50"
      >
        {meta && <meta.Icon size={12} className={cn("shrink-0", meta.textClass)} />}
        <span className="flex-1 truncate text-foreground">{entity?.displayName ?? "…"}</span>
        {suggestion.score != null && (
          <span className="tabular-nums text-[11px] text-annotation">{Math.round(suggestion.score * 100)}%</span>
        )}
        {suggestion.count != null && (
          <span className="text-[11px] text-muted-foreground" title="Other mentions of this value resolved here">
            {suggestion.count}× elsewhere
          </span>
        )}
      </button>
    </li>
  );
}

/** Aceternity-style pointer highlight: a box that draws itself around the span, a cursor riding its corner. */
function PointerHighlight({ rect }: { rect: DOMRect }) {
  const pad = 3;
  const width = rect.width + pad * 2;
  const height = rect.height + pad * 2;
  return (
    <div
      style={{ position: "fixed", top: rect.top - pad, left: rect.left - pad, width, height }}
      className="pointer-events-none z-[61]"
    >
      <motion.div
        className="absolute left-0 top-0 rounded-[4px] border border-primary bg-primary/10"
        initial={{ width: 0, height: 0 }}
        animate={{ width, height }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      />
      <motion.div
        className="absolute left-0 top-0"
        initial={{ opacity: 0, x: 0, y: 0 }}
        animate={{ opacity: 1, x: width + 2, y: height + 2 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        style={{ rotate: -90 }}
      >
        <MousePointer2 className="h-4 w-4 fill-primary text-primary" />
      </motion.div>
    </div>
  );
}
