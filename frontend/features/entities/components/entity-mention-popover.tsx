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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import {
  useCreateEntity,
  useEntitySearch,
} from "@/features/entities/hooks/use-entities";
import {
  useCreateMention,
  useDeleteMention,
  useResolveMention,
  useUpdateMention,
} from "@/features/entities/hooks/use-mentions";
import { ENTITY_TYPES, type EntityType, type Mention } from "@/features/entities/types";
import { useMe } from "@/features/users/hooks/use-me";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import { motion } from "motion/react";
import { Link2Off, Loader2, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { createPortal } from "react-dom";

interface EntityMentionPopoverProps {
  /** Viewport rect of the selected / existing span to anchor the panel + brackets to. */
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

export function EntityMentionPopover(props: EntityMentionPopoverProps) {
  const { rect, surface, datasetId, existing, onClose } = props;
  const me = useMe().data;
  const reviewedBy = me?.name ?? me?.id ?? "analyst";

  const [entityType, setEntityType] = useState<EntityType>(existing?.entityType ?? "person");
  const [query, setQuery] = useState(surface.trim().slice(0, 80));
  const debouncedQuery = useDebounce(query, 250);

  const { data: results, isFetching } = useEntitySearch({ datasetId, q: debouncedQuery });

  const done = () => onClose();
  const createEntity = useCreateEntity();
  const createMention = useCreateMention(done);
  const resolveMention = useResolveMention(done);
  const updateMention = useUpdateMention(done);
  const deleteMention = useDeleteMention(done);

  const busy =
    createEntity.isPending ||
    createMention.isPending ||
    resolveMention.isPending ||
    updateMention.isPending ||
    deleteMention.isPending;

  const attachExisting = async (entityId: string, type: EntityType) => {
    if (existing) {
      updateMention.mutate({ id: existing.id, payload: { entityId, entityType: type } });
      return;
    }
    createMention.mutate({
      datasetId,
      entityId,
      mentionedType: "extracted_text",
      mentionedId: props.textId,
      fileId: props.fileId,
      surfaceText: surface,
      entityType: type,
      startOffset: props.startOffset,
      endOffset: props.endOffset,
    });
  };

  const createAndAttach = async () => {
    const displayName = surface.trim().slice(0, 200) || query.trim();
    if (existing) {
      resolveMention.mutate({
        id: existing.id,
        payload: {
          reviewedBy,
          newEntity: { datasetId, entityType, displayName },
        },
      });
      return;
    }
    const entity = await createEntity.mutateAsync({ datasetId, entityType, displayName });
    createMention.mutate({
      datasetId,
      entityId: entity.id,
      mentionedType: "extracted_text",
      mentionedId: props.textId,
      fileId: props.fileId,
      surfaceText: surface,
      entityType,
      startOffset: props.startOffset,
      endOffset: props.endOffset,
    });
  };

  const panelStyle = useMemo(() => {
    const top = Math.min(rect.bottom + 8, window.innerHeight - 340);
    const left = Math.min(Math.max(rect.left, 12), window.innerWidth - 320);
    return { top, left };
  }, [rect]);

  return createPortal(
    <>
      {/* dismiss layer */}
      <div className="fixed inset-0 z-[60]" onMouseDown={onClose} />

      <PointerBrackets rect={rect} />

      <motion.div
        initial={{ opacity: 0, y: 6, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 340, damping: 26 }}
        style={{ position: "fixed", ...panelStyle }}
        className="z-[61] w-[19rem] rounded-lg border border-border bg-popover p-3 text-sm shadow-xl ring-1 ring-foreground/10"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <p className="mb-2 truncate text-[11px] text-muted-foreground">
          Label <span className="font-mono text-foreground">&ldquo;{surface.trim()}&rdquo;</span>
        </p>

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
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Search existing entities…"
            className="text-xs"
          />
          <CommandList className="max-h-40">
            {isFetching && (
              <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-muted-foreground">
                <Loader2 size={12} className="animate-spin" /> Searching…
              </div>
            )}
            {!isFetching && (results?.length ?? 0) === 0 && (
              <CommandEmpty className="py-3 text-[11px] text-muted-foreground">
                No matches. Create a new one below.
              </CommandEmpty>
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
                    <span className="text-[9px] uppercase text-muted-foreground">
                      {r.matchReason}
                    </span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>

        <Button
          size="sm"
          disabled={busy}
          onClick={createAndAttach}
          className="mt-2 h-8 w-full gap-1.5 bg-primary text-xs hover:bg-primary"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          Create {ENTITY_TYPE_META[entityType].label.toLowerCase()}
        </Button>

        {existing && (
          <div className="mt-2 flex gap-2">
            {existing.entityId && (
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() =>
                  updateMention.mutate({ id: existing.id, payload: { entityId: null } })
                }
                className="h-7 flex-1 gap-1 text-[11px] text-muted-foreground"
              >
                <Link2Off size={11} /> Unlink
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => deleteMention.mutate(existing.id)}
              className="h-7 flex-1 gap-1 text-[11px] text-destructive hover:text-destructive"
            >
              <Trash2 size={11} /> Delete
            </Button>
          </div>
        )}
      </motion.div>
    </>,
    document.body
  );
}

/** The aceternity "pointer highlight" motif: animated corner brackets around a rect. */
function PointerBrackets({ rect }: { rect: DOMRect }) {
  const pad = 3;
  const box = {
    position: "fixed" as const,
    top: rect.top - pad,
    left: rect.left - pad,
    width: rect.width + pad * 2,
    height: rect.height + pad * 2,
  };
  const corner = "absolute h-3 w-3 border-primary";
  return (
    <motion.div
      style={box}
      className="pointer-events-none z-[61]"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 400, damping: 28 }}
    >
      <span className={cn(corner, "left-0 top-0 border-l-2 border-t-2")} />
      <span className={cn(corner, "right-0 top-0 border-r-2 border-t-2")} />
      <span className={cn(corner, "bottom-0 left-0 border-b-2 border-l-2")} />
      <span className={cn(corner, "bottom-0 right-0 border-b-2 border-r-2")} />
    </motion.div>
  );
}
