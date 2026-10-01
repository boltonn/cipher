import { HighlightedText } from "@/components/ui/highlighted-text";
import type { MentionSpan } from "../types";

interface MentionMarkedTextProps {
  text: string;
  /** Absolute offset of `text[0]` in the file's extracted text. */
  offset: number;
  spans: MentionSpan[];
  terms: string[];
}

/** `text` with exact entity-mention spans marked in the annotation color; the rest gets keyword term marks. */
export function MentionMarkedText({ text, offset, spans, terms }: MentionMarkedTextProps) {
  const parts: { text: string; mention: boolean }[] = [];
  let cursor = 0;
  for (const span of spans) {
    const start = Math.max(span.startOffset - offset, cursor);
    const end = Math.min(span.endOffset - offset, text.length);
    if (end <= start) continue;
    if (start > cursor) parts.push({ text: text.slice(cursor, start), mention: false });
    parts.push({ text: text.slice(start, end), mention: true });
    cursor = end;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), mention: false });

  return (
    <>
      {parts.map((part, index) =>
        part.mention ? (
          <mark key={index} className="rounded-sm bg-annotation/25 px-0.5 -mx-0.5 font-medium text-inherit ring-1 ring-inset ring-annotation/50 box-decoration-clone">
            {part.text}
          </mark>
        ) : (
          <HighlightedText key={index} text={part.text} terms={terms} />
        )
      )}
    </>
  );
}
