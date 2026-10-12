"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  ENTITY_TYPE_META,
  SELECTOR_TYPE_META,
} from "@/features/entities/components/entity-type-meta";
import {
  useCreateMention,
  useDeleteMention,
  useUpdateMention,
} from "@/features/entities/hooks/use-mentions";
import {
  SELECTOR_TYPES,
  type EntityType,
  type Mention,
  type SelectorType,
} from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { Check, HelpCircle, Link2, Loader2, X } from "lucide-react";
import { forwardRef, Fragment, useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Text inside a label: blank lines show as one line break, so an address over several
 * lines reads as one label instead of a row of empty boxes. The hidden breaks stay in
 * the DOM, keeping selection offsets true to the text.
 */
export function labelText(text: string): ReactNode {
  const parts = text.split(/(\n[ \t]*(?:\n[ \t]*)+)/);
  if (parts.length === 1) return text;
  return parts.map((part, i) =>
    i % 2 ? (
      <Fragment key={i}>
        {"\n"}
        <span className="hidden">{part.slice(1)}</span>
      </Fragment>
    ) : (
      part
    )
  );
}

/** A label: a name type, or a selector kind. */
export interface MentionLabel {
  entityType: EntityType;
  selectorType: SelectorType | null;
}

const NAME_LABELS: {
  entityType: Exclude<EntityType, "selector">;
  key: string;
}[] = [
  { entityType: "person", key: "1" },
  { entityType: "organization", key: "2" },
  { entityType: "location", key: "3" },
];

function sameLabel(mention: Mention, label: MentionLabel) {
  return (
    mention.entityType === label.entityType &&
    (label.entityType !== "selector" ||
      mention.selectorType === label.selectorType)
  );
}

/** The type menu: names first (with their 1-2-3 keys), selector kinds in a submenu. */
function LabelMenuItems({
  current,
  onPick,
}: {
  current?: Mention;
  onPick: (label: MentionLabel) => void;
}) {
  return (
    <>
      <DropdownMenuLabel className="text-[11px] text-muted-foreground">
        Label as
      </DropdownMenuLabel>
      {NAME_LABELS.map(({ entityType, key }) => {
        const meta = ENTITY_TYPE_META[entityType];
        const label = { entityType, selectorType: null };
        return (
          <DropdownMenuItem
            key={entityType}
            onSelect={() => onPick(label)}
            className="gap-2 text-xs"
          >
            <meta.Icon size={13} className={meta.textClass} />
            {meta.label}
            {current && sameLabel(current, label) ? (
              <Check size={12} className="ml-auto" />
            ) : (
              <DropdownMenuShortcut>{key}</DropdownMenuShortcut>
            )}
          </DropdownMenuItem>
        );
      })}
      <DropdownMenuSeparator />
      <DropdownMenuSub>
        <DropdownMenuSubTrigger className="gap-2 text-xs">
          <ENTITY_TYPE_META.selector.Icon
            size={13}
            className={ENTITY_TYPE_META.selector.textClass}
          />
          Selector
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent className="max-h-80 overflow-y-auto">
          {SELECTOR_TYPES.map((selectorType) => {
            const meta = SELECTOR_TYPE_META[selectorType];
            const label = { entityType: "selector" as const, selectorType };
            return (
              <DropdownMenuItem
                key={selectorType}
                onSelect={() => onPick(label)}
                className="gap-2 text-xs"
              >
                <meta.Icon
                  size={13}
                  className={ENTITY_TYPE_META.selector.textClass}
                />
                {meta.label}
                {current && sameLabel(current, label) && (
                  <Check size={12} className="ml-auto" />
                )}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuSubContent>
      </DropdownMenuSub>
    </>
  );
}

interface MentionChipProps {
  mention: Mention;
  /** Other mentions on exactly this span (two extractors agreeing); removed together. */
  duplicates?: Mention[];
  text: string;
  /** What to show in place of `text` -- the text with labels nested inside it (a city in an address). */
  children?: ReactNode;
  /** Open the resolve panel for this mention, anchored to the chip. */
  onOpen: (rect: DOMRect) => void;
}

/**
 * One labelled span in running text, the way an NER labelling tool shows it: the type
 * icon (click to relabel), the text (click to resolve it to an entity), and × to say
 * it isn't an entity at all. Resolved spans take their type's colour; unresolved ones
 * stay dashed -- amber when a model proposed them, primary when an analyst drew them.
 */
export const MentionChip = forwardRef<HTMLSpanElement, MentionChipProps>(
  function MentionChip(
    { mention, duplicates = [], text, children, onOpen },
    ref
  ) {
    const update = useUpdateMention();
    const remove = useDeleteMention();
    const resolved = !!mention.entityId;
    const meta = mention.entityType
      ? ENTITY_TYPE_META[mention.entityType]
      : null;
    const Glyph =
      mention.entityType === "selector" && mention.selectorType
        ? SELECTOR_TYPE_META[mention.selectorType].Icon
        : mention.entityType
          ? ENTITY_TYPE_META[mention.entityType].Icon
          : HelpCircle;
    const busy = update.isPending || remove.isPending;

    const relabel = (label: MentionLabel) => {
      if (sameLabel(mention, label)) return;
      for (const m of [mention, ...duplicates]) {
        update.mutate({
          id: m.id,
          payload: {
            entityType: label.entityType,
            selectorType: label.selectorType,
          },
        });
      }
    };
    const open = (target: HTMLElement) =>
      onOpen((target.parentElement ?? target).getBoundingClientRect());
    const notAnEntity = () => {
      for (const m of [mention, ...duplicates]) remove.mutate(m.id);
    };

    return (
      <span
        ref={ref}
        className={cn(
          // inline, not inline-flex: a span over a line break wraps like the text it labels
          "group/chip mx-[1px] inline rounded-md border py-[1px] pl-0.5 pr-0.5 align-baseline font-sans text-[0.82em] font-medium leading-tight [box-decoration-break:clone]",
          resolved && meta
            ? cn(meta.bgClass, meta.textClass, meta.borderClass)
            : mention.extractor === "manual"
              ? "border-dashed border-primary/50 bg-primary/10 text-primary"
              : "border-dashed border-annotation/50 bg-annotation/10 text-annotation"
        )}
      >
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              disabled={busy}
              aria-label={`${meta?.label ?? "Unlabelled"} -- change type`}
              title="Change type"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm align-[-0.2em] opacity-80 hover:bg-foreground/10 hover:opacity-100"
            >
              {busy ? (
                <Loader2 size={10} className="animate-spin" />
              ) : (
                <Glyph size={10} />
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-52">
            <LabelMenuItems current={mention} onPick={relabel} />
          </DropdownMenuContent>
        </DropdownMenu>
        {/* a span, not a button: it can hold nested label chips (each with its own buttons) */}
        <span
          role="button"
          tabIndex={0}
          onClick={(e) => {
            e.stopPropagation();
            if (!window.getSelection()?.isCollapsed) return; // a drag inside the chip adjusts the span
            open(e.currentTarget);
          }}
          onKeyDown={(e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            e.preventDefault();
            open(e.currentTarget);
          }}
          title={
            resolved ? "Change the entity it refers to" : "Resolve to an entity"
          }
          className="cursor-pointer select-text whitespace-pre-wrap rounded-sm px-0.5 text-left hover:underline focus-visible:outline-1 focus-visible:outline-ring"
        >
          {children ?? labelText(text)}
        </span>
        {!resolved && (
          <Link2 size={9} aria-hidden className="inline shrink-0 opacity-50" />
        )}
        <button
          type="button"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation();
            notAnEntity();
          }}
          aria-label="Not an entity -- remove this label"
          title="Not an entity"
          className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm align-[-0.2em] opacity-0 transition-opacity hover:bg-destructive/15 hover:text-destructive focus-visible:opacity-100 group-hover/chip:opacity-70"
        >
          <X size={10} />
        </button>
      </span>
    );
  }
);

interface MentionLabelToolbarProps {
  rect: DOMRect;
  span: {
    datasetId: string;
    fileId: string;
    textId: string;
    surfaceText: string;
    startOffset: number;
    endOffset: number;
  };
  /** Open the full panel (label + resolve in one go). */
  onMore: () => void;
  onClose: () => void;
}

/** Floats over a fresh text selection: label it in one click (or 1 / 2 / 3), resolve later. */
export function MentionLabelToolbar({
  rect,
  span,
  onMore,
  onClose,
}: MentionLabelToolbarProps) {
  const create = useCreateMention(onClose);
  const label = ({ entityType, selectorType }: MentionLabel) =>
    create.mutate({
      datasetId: span.datasetId,
      mentionedType: "extractedText",
      mentionedId: span.textId,
      fileId: span.fileId,
      surfaceText: span.surfaceText,
      entityType,
      selectorType,
      startOffset: span.startOffset,
      endOffset: span.endOffset,
    });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation(); // dismiss the toolbar only, not a dialog it sits in
        return onClose();
      }
      const hit = NAME_LABELS.find((l) => l.key === e.key);
      if (hit && !create.isPending) {
        e.preventDefault();
        label({ entityType: hit.entityType, selectorType: null });
      }
    };
    // window capture runs before Radix's document-level Escape-to-close on an enclosing dialog
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  return createPortal(
    <div
      role="toolbar"
      aria-label="Label the selection"
      onMouseDown={(e) => e.preventDefault()}
      style={{ position: "fixed", top: rect.bottom + 6, left: rect.left }}
      className="z-50 flex items-center gap-0.5 rounded-lg border border-border bg-popover p-1 shadow-lg"
    >
      {NAME_LABELS.map(({ entityType, key }) => {
        const meta = ENTITY_TYPE_META[entityType];
        return (
          <Button
            key={entityType}
            size="sm"
            variant="ghost"
            disabled={create.isPending}
            onClick={() => label({ entityType, selectorType: null })}
            className="h-7 gap-1.5 px-2 text-xs"
            title={`${meta.label} (${key})`}
          >
            <meta.Icon size={13} className={meta.textClass} />
            {meta.label}
          </Button>
        );
      })}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            size="sm"
            variant="ghost"
            disabled={create.isPending}
            className="h-7 gap-1.5 px-2 text-xs"
          >
            <ENTITY_TYPE_META.selector.Icon
              size={13}
              className={ENTITY_TYPE_META.selector.textClass}
            />
            Selector
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="max-h-80 overflow-y-auto">
          {SELECTOR_TYPES.map((selectorType) => {
            const meta = SELECTOR_TYPE_META[selectorType];
            return (
              <DropdownMenuItem
                key={selectorType}
                onSelect={() => label({ entityType: "selector", selectorType })}
                className="gap-2 text-xs"
              >
                <meta.Icon
                  size={13}
                  className={ENTITY_TYPE_META.selector.textClass}
                />
                {meta.label}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
      <span className="mx-0.5 h-4 w-px bg-border" />
      <Button
        size="sm"
        variant="ghost"
        onClick={onMore}
        className="h-7 px-2 text-xs text-muted-foreground"
      >
        Label &amp; resolve…
      </Button>
      <Button
        size="icon"
        variant="ghost"
        onClick={onClose}
        aria-label="Cancel"
        className="h-7 w-7 text-muted-foreground"
      >
        {create.isPending ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <X size={12} />
        )}
      </Button>
    </div>,
    document.body
  );
}
