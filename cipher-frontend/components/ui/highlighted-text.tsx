import { Fragment } from "react";

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

interface HighlightedTextProps {
  text: string;
  /** Case-insensitive substring to highlight; empty/whitespace-only renders `text` unchanged. */
  query?: string;
  className?: string;
  markClassName?: string;
}

/** Wraps every case-insensitive occurrence of `query` in `text` with `<mark>`. Mirrors the substring-match behavior of the PDF viewer's own text-layer search, just for plain React text instead of DOM ranges. */
export function HighlightedText({
  text,
  query,
  className,
  markClassName = "bg-amber-400/30 text-inherit rounded-[2px]",
}: HighlightedTextProps) {
  const trimmedQuery = query?.trim();
  if (!trimmedQuery) return <span className={className}>{text}</span>;

  const parts = text.split(new RegExp(`(${escapeRegExp(trimmedQuery)})`, "gi"));

  return (
    <span className={className}>
      {parts.map((part, index) =>
        part.toLowerCase() === trimmedQuery.toLowerCase() ? (
          <mark key={index} className={markClassName}>
            {part}
          </mark>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        )
      )}
    </span>
  );
}
