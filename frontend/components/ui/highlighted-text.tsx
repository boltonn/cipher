import { Fragment, useMemo } from "react";

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

interface HighlightedTextProps {
  text: string;
  /** Case-insensitive substring to highlight; ignored when `terms` is non-empty. */
  query?: string;
  /** Exact words/phrases to highlight (e.g. Elasticsearch highlight matches). Takes priority over `query`. */
  terms?: string[];
  className?: string;
  markClassName?: string;
}

/**
 * Wraps every case-insensitive occurrence of `terms` (or `query` as fallback)
 * in `text` with `<mark>`. Cyan (the `--highlight` token), deliberately not
 * amber -- amber (`--annotation`) is reserved for AI/ML output -- and not
 * indigo (`--primary`), which marks the semantic chunk region; a keyword match
 * is its own kind of mark. The wash is translucent so the text keeps its own
 * contrast; `box-decoration-clone` keeps the rounded pill intact when a match
 * wraps across lines, and runs of adjacent matches are merged into one
 * `<mark>` so no seam shows where the alpha would otherwise double up.
 */
export function HighlightedText({
  text,
  query,
  terms,
  className,
  markClassName = "rounded-sm bg-highlight/35 px-0.5 -mx-0.5 font-medium text-inherit box-decoration-clone",
}: HighlightedTextProps) {
  const pattern = useMemo(() => {
    const active = (terms?.length ? terms : [query?.trim() ?? ""]).filter(Boolean);
    if (active.length === 0) return null;
    // Longest-first so a phrase match wins over one of its own words.
    const alternation = [...new Set(active)]
      .sort((a, b) => b.length - a.length)
      .map(escapeRegExp)
      .join("|");
    return new RegExp(`(${alternation})`, "gi");
  }, [terms, query]);

  // Split on the single capture group -> matches land at odd indices. Drop the
  // empty fragments that sit between back-to-back matches and coalesce runs of
  // the same kind so touching marks render as one continuous pill.
  const segments = useMemo(() => {
    if (!pattern) return null;
    const out: { text: string; mark: boolean }[] = [];
    text.split(pattern).forEach((part, index) => {
      if (part === "") return;
      const mark = index % 2 === 1;
      const last = out.at(-1);
      if (last && last.mark === mark) last.text += part;
      else out.push({ text: part, mark });
    });
    return out;
  }, [text, pattern]);

  if (!segments) return <span className={className}>{text}</span>;

  return (
    <span className={className}>
      {segments.map((segment, index) =>
        segment.mark ? (
          <mark key={index} className={markClassName}>
            {segment.text}
          </mark>
        ) : (
          <Fragment key={index}>{segment.text}</Fragment>
        )
      )}
    </span>
  );
}
