"use client";

import { useFileText } from "@/features/files/api";
import { EntityHoverCard } from "@/features/entities/components/entity-tooltip-card";
import { EntityMentionPopover } from "@/features/entities/components/entity-mention-popover";
import {
  labelText,
  MentionChip,
  MentionLabelToolbar,
} from "@/features/entities/components/mention-chip";
import { useFileMentions } from "@/features/entities/hooks/use-mentions";
import { foldName } from "@/features/entities/lib/fold-name";
import type { Mention } from "@/features/entities/types";
import { textOffsets, type TextOffsets } from "@/lib/text-offsets";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import {
  Fragment,
  type ReactNode,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

interface EntityMentionTextProps {
  fileId: string;
  datasetId: string;
  /** Only mark these entities' mentions (e.g. search's entity filter); omit for all. */
  entityIds?: string[];
  /** Only mark mentions of these values (search's mention filter); combines with `entityIds` as either-or. */
  mentionValues?: string[];
  /** char offset to scroll into view on load (e.g. a specific mention) */
  focusOffset?: number;
  /** Show only this slice of the text (offsets stay absolute), e.g. an email signature. */
  range?: { start: number; end: number };
  /** Ring these mentions (e.g. the two ends of a hovered relationship). */
  activeMentionIds?: string[];
  className?: string;
}

/** Spans in UTF-16 indices of the displayed text (mention offsets are converted on the way in). */
interface Segment {
  start: number;
  end: number;
  mention?: Mention;
  /** other labels of this name: the same span, or the same name key overlapping it (two extractors) */
  duplicates?: Mention[];
  /** mentions inside this one (a city inside an address), shown as chips within it */
  inner?: Segment[];
}

/** Resolved first, then analyst-drawn: which of several labels on one span to show. */
function preference(m: Mention) {
  return (m.entityId ? 2 : 0) + (m.extractor === "manual" ? 1 : 0);
}

function buildSegments(
  mentions: Mention[],
  offsets: TextOffsets,
  from: number,
  to: number
): Segment[] {
  const spans = mentions
    .filter(
      (m) =>
        typeof m.startOffset === "number" &&
        typeof m.endOffset === "number" &&
        m.endOffset > m.startOffset
    )
    .map((m) => ({
      m,
      s: offsets.toUtf16(m.startOffset as number),
      e: offsets.toUtf16(m.endOffset as number),
    }))
    .filter(({ s, e }) => s >= from && e <= to)
    .sort(
      (a, b) => a.s - b.s || b.e - a.e || preference(b.m) - preference(a.m)
    );

  const segs: Segment[] = [];
  let cursor = from;
  for (const { m, s, e } of spans) {
    const last = segs.at(-1);
    const isTwin =
      last?.mention &&
      ((last.start === s && last.end === e) ||
        (s < last.end &&
          !!m.normalizedValue &&
          m.normalizedValue === last.mention.normalizedValue &&
          m.entityType === last.mention.entityType));
    if (last?.mention && isTwin) {
      // show the twin that says the most (resolved, analyst-drawn); the chip keeps the wider span
      const [shown, other] =
        preference(m) > preference(last.mention)
          ? [m, last.mention]
          : [last.mention, m];
      last.mention = shown;
      last.duplicates = [...(last.duplicates ?? []), other];
      continue;
    }
    if (last?.mention && last.start <= s && e <= last.end) {
      // nested one level; twins of an inner label share its chip
      const twin = last.inner?.find((i) => i.start === s && i.end === e);
      if (twin?.mention) {
        const [shown, other] =
          preference(m) > preference(twin.mention)
            ? [m, twin.mention]
            : [twin.mention, m];
        twin.mention = shown;
        twin.duplicates = [...(twin.duplicates ?? []), other];
      } else
        last.inner = [...(last.inner ?? []), { start: s, end: e, mention: m }];
      continue;
    }
    if (s < cursor) continue; // drop overlaps, keep the earlier mention
    if (s > cursor) segs.push({ start: cursor, end: s });
    segs.push({ start: s, end: e, mention: m });
    cursor = e;
  }
  if (cursor < to) segs.push({ start: cursor, end: to });
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
  return {
    start,
    end: start + value.length,
    text: value,
    rect: range.getBoundingClientRect(),
  };
}

/** The one displayed mention a selection overlaps -- selecting inside/across a chip adjusts that mention's span. */
function overlappingMention(segments: Segment[], start: number, end: number) {
  const hits = segments.filter(
    (seg) => seg.mention && seg.start < end && start < seg.end
  );
  return hits.length === 1 ? hits[0].mention : undefined;
}

export function EntityMentionText({
  fileId,
  datasetId,
  entityIds,
  mentionValues,
  focusOffset,
  range,
  activeMentionIds,
  className,
}: EntityMentionTextProps) {
  const {
    data: fileText,
    isPending: textPending,
    isError,
  } = useFileText(fileId);
  const { data: mentionsPage, isPending: mentionsPending } =
    useFileMentions(fileId);
  const preRef = useRef<HTMLPreElement>(null);
  const focusRef = useRef<HTMLSpanElement>(null);

  const [selection, setSelection] = useState<{
    surface: string;
    start: number;
    end: number;
    rect: DOMRect;
    existing?: Mention;
    full?: boolean;
  } | null>(null);
  // backend offsets count code points; the DOM counts UTF-16 units (an emoji is two)
  const offsets = useMemo(() => textOffsets(fileText?.text ?? ""), [fileText]);
  const from = offsets.toUtf16(range?.start ?? 0);
  const rangeEnd = range?.end;
  const focus = focusOffset != null ? offsets.toUtf16(focusOffset) : undefined;

  const segments = useMemo(() => {
    if (!fileText) return [];
    const mentions = mentionsPage?.data ?? [];
    const to =
      rangeEnd != null ? offsets.toUtf16(rangeEnd) : fileText.text.length;
    if (!entityIds?.length && !mentionValues?.length)
      return buildSegments(mentions, offsets, from, to);
    const values = new Set(
      (mentionValues ?? []).flatMap((v) => [v, foldName(v)])
    );
    // Analyst-drawn mentions stay visible so a fresh edit doesn't vanish under the filter.
    const shown = mentions.filter(
      (m) =>
        (m.entityId && entityIds?.includes(m.entityId)) ||
        (m.normalizedValue && values.has(m.normalizedValue)) ||
        m.extractor === "manual"
    );
    return buildSegments(shown, offsets, from, to);
  }, [
    fileText,
    mentionsPage,
    entityIds,
    mentionValues,
    offsets,
    from,
    rangeEnd,
  ]);

  useLayoutEffect(() => {
    if (focus != null && focusRef.current) {
      focusRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [focus, segments]);

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
      const start = hit.start + from;
      const end = hit.end + from;
      const existing = overlappingMention(segments, start, end);
      setSelection({
        surface: hit.text,
        start: offsets.toCodePoint(start),
        end: offsets.toCodePoint(end),
        rect: hit.rect,
        existing,
        full: !!existing,
      });
    }
  };

  const isActive = (mention: Mention, duplicates?: Mention[]) =>
    !!activeMentionIds?.some(
      (id) => id === mention.id || duplicates?.some((d) => d.id === id)
    );

  const renderInner = (seg: Segment) => {
    const parts: ReactNode[] = [];
    let cursor = seg.start;
    for (const { start, end, mention: inner, duplicates } of seg.inner ?? []) {
      if (!inner || start < cursor) continue;
      if (start > cursor)
        parts.push(labelText(fileText.text.slice(cursor, start)));
      const innerText = fileText.text.slice(start, end);
      parts.push(
        <span
          key={inner.id}
          className={cn(
            isActive(inner, duplicates) &&
              "rounded-md ring-2 ring-primary ring-offset-1 ring-offset-background"
          )}
        >
          <MentionChip
            mention={inner}
            duplicates={duplicates}
            text={innerText}
            onOpen={(rect) =>
              setSelection({
                surface: innerText,
                start: inner.startOffset as number,
                end: inner.endOffset as number,
                rect,
                existing: inner,
                full: true,
              })
            }
          />
        </span>
      );
      cursor = end;
    }
    if (cursor < seg.end)
      parts.push(labelText(fileText.text.slice(cursor, seg.end)));
    return parts;
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
            focus != null && focus >= seg.start && focus < seg.end;
          if (!seg.mention) {
            return (
              <span key={i} ref={spansFocus ? focusRef : undefined}>
                {slice}
              </span>
            );
          }
          const m = seg.mention;
          const resolved = !!m.entityId;
          const mark = (
            <span
              className={cn(
                isActive(m, seg.duplicates) &&
                  "rounded-md ring-2 ring-primary ring-offset-1 ring-offset-background"
              )}
            >
              <MentionChip
                ref={spansFocus ? focusRef : undefined}
                mention={m}
                duplicates={seg.duplicates}
                text={slice}
                onOpen={(rect) =>
                  setSelection({
                    surface: slice,
                    start: m.startOffset as number,
                    end: m.endOffset as number,
                    rect,
                    existing: m,
                    full: true,
                  })
                }
              >
                {seg.inner && renderInner(seg)}
              </MentionChip>
            </span>
          );
          return (
            <Fragment key={i}>
              {resolved && m.entityId ? (
                <EntityHoverCard
                  entityId={m.entityId}
                  entityType={m.entityType ?? undefined}
                  disabled={!!selection}
                >
                  {mark}
                </EntityHoverCard>
              ) : (
                mark
              )}
            </Fragment>
          );
        })}
      </pre>

      {selection && !selection.full && (
        <MentionLabelToolbar
          key={`${selection.start}:${selection.end}`}
          rect={selection.rect}
          span={{
            datasetId,
            fileId,
            textId: fileText.extractedTextId,
            surfaceText: selection.surface,
            startOffset: selection.start,
            endOffset: selection.end,
          }}
          onMore={() => setSelection({ ...selection, full: true })}
          onClose={() => {
            setSelection(null);
            window.getSelection()?.removeAllRanges();
          }}
        />
      )}
      {selection?.full && (
        <EntityMentionPopover
          key={`${selection.start}:${selection.end}`}
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
