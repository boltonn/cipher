"use client";

import { useFileText } from "@/features/files/api";
import {
  ENTITY_TYPE_META,
  entityGlyph,
} from "@/features/entities/components/entity-type-meta";
import { EntityHoverCard } from "@/features/entities/components/entity-tooltip-card";
import { EntityMentionPopover } from "@/features/entities/components/entity-mention-popover";
import { useFileMentions } from "@/features/entities/hooks/use-mentions";
import type { Mention } from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { HelpCircle, Loader2 } from "lucide-react";
import { Fragment, useLayoutEffect, useMemo, useRef, useState } from "react";

interface EntityMentionTextProps {
  fileId: string;
  datasetId: string;
  /** char offset to scroll into view on load (e.g. a specific mention) */
  focusOffset?: number;
  className?: string;
}

interface Segment {
  start: number;
  end: number;
  mention?: Mention;
}

function buildSegments(text: string, mentions: Mention[]): Segment[] {
  const spans = mentions
    .filter(
      (m) =>
        typeof m.startOffset === "number" &&
        typeof m.endOffset === "number" &&
        m.endOffset > m.startOffset &&
        m.endOffset <= text.length
    )
    .sort((a, b) => (a.startOffset as number) - (b.startOffset as number));

  const segs: Segment[] = [];
  let cursor = 0;
  for (const m of spans) {
    const s = m.startOffset as number;
    const e = m.endOffset as number;
    if (s < cursor) continue; // drop overlaps, keep the earlier mention
    if (s > cursor) segs.push({ start: cursor, end: s });
    segs.push({ start: s, end: e, mention: m });
    cursor = e;
  }
  if (cursor < text.length) segs.push({ start: cursor, end: text.length });
  return segs;
}

function selectionOffsets(container: HTMLElement) {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const range = sel.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) return null;
  const pre = range.cloneRange();
  pre.selectNodeContents(container);
  pre.setEnd(range.startContainer, range.startOffset);
  const start = pre.toString().length;
  const value = range.toString();
  if (!value.trim()) return null;
  return { start, end: start + value.length, text: value, rect: range.getBoundingClientRect() };
}

export function EntityMentionText({ fileId, datasetId, focusOffset, className }: EntityMentionTextProps) {
  const { data: fileText, isPending: textPending, isError } = useFileText(fileId);
  const { data: mentionsPage, isPending: mentionsPending } = useFileMentions(fileId);
  const preRef = useRef<HTMLPreElement>(null);
  const focusRef = useRef<HTMLSpanElement>(null);

  const [selection, setSelection] = useState<
    | { surface: string; start: number; end: number; rect: DOMRect; existing?: Mention }
    | null
  >(null);

  const segments = useMemo(
    () => (fileText ? buildSegments(fileText.text, mentionsPage?.data ?? []) : []),
    [fileText, mentionsPage]
  );

  useLayoutEffect(() => {
    if (focusOffset != null && focusRef.current) {
      focusRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [focusOffset, segments]);

  if (textPending || mentionsPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading extracted text…
      </div>
    );
  }
  if (isError || !fileText) {
    return (
      <p className="py-10 text-center text-xs italic text-muted-foreground">
        Extracted text unavailable.
      </p>
    );
  }

  const handleMouseUp = () => {
    if (!preRef.current) return;
    const hit = selectionOffsets(preRef.current);
    if (hit) {
      setSelection({ surface: hit.text, start: hit.start, end: hit.end, rect: hit.rect });
    }
  };

  return (
    <div className={cn("relative", className)}>
      <pre
        ref={preRef}
        onMouseUp={handleMouseUp}
        className="max-h-full overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-sm leading-relaxed text-foreground selection:bg-primary/30"
      >
        {segments.map((seg, i) => {
          const slice = fileText.text.slice(seg.start, seg.end);
          const spansFocus =
            focusOffset != null && focusOffset >= seg.start && focusOffset < seg.end;
          if (!seg.mention) {
            return (
              <span key={i} ref={spansFocus ? focusRef : undefined}>
                {slice}
              </span>
            );
          }
          const m = seg.mention;
          const resolved = !!m.entityId;
          const meta = m.entityType ? ENTITY_TYPE_META[m.entityType] : null;
          const Glyph = m.entityType
            ? entityGlyph(m.entityType, m.selectorType)
            : HelpCircle;
          // Inline chip: a small type icon + the surface text in a rounded,
          // tinted pill -- displacy-style, but it stays in the text flow and
          // keeps click-to-annotate + hover-card.
          const mark = (
            <span
              ref={spansFocus ? focusRef : undefined}
              onClick={(e) => {
                e.stopPropagation();
                setSelection({
                  surface: slice,
                  start: seg.start,
                  end: seg.end,
                  rect: (e.currentTarget as HTMLElement).getBoundingClientRect(),
                  existing: m,
                });
              }}
              className={cn(
                "mx-[1px] inline-flex cursor-pointer select-text items-center gap-1 rounded-md border px-1 py-[1px] align-baseline font-sans text-[0.82em] font-medium leading-tight transition-shadow hover:shadow-sm",
                resolved && meta
                  ? cn(meta.bgClass, meta.textClass, meta.borderClass)
                  : "border-dashed border-annotation/50 bg-annotation/10 text-annotation"
              )}
            >
              <Glyph size={10} className="shrink-0 opacity-80" />
              {slice}
            </span>
          );
          return (
            <Fragment key={i}>
              {resolved && m.entityId ? (
                <EntityHoverCard entityId={m.entityId} entityType={m.entityType ?? undefined}>
                  {mark}
                </EntityHoverCard>
              ) : (
                mark
              )}
            </Fragment>
          );
        })}
      </pre>

      {selection && (
        <EntityMentionPopover
          rect={selection.rect}
          surface={selection.surface}
          datasetId={datasetId}
          fileId={fileId}
          textId={fileText.extractedTextId}
          startOffset={selection.start}
          endOffset={selection.end}
          existing={selection.existing}
          onClose={() => {
            setSelection(null);
            window.getSelection()?.removeAllRanges();
          }}
        />
      )}
    </div>
  );
}
