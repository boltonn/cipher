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
 * in `text` with `<mark>`. Cyan, deliberately not amber -- amber is reserved
 * for AI/ML annotation surfaces (scores, model output), and a keyword match
 * is not an annotation.
 */
export function HighlightedText({
  text,
  query,
  terms,
  className,
  markClassName = "bg-cyan-400/30 text-inherit rounded-[2px]",
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

  if (!pattern) return <span className={className}>{text}</span>;

  // Splitting on a single capture group interleaves matches at odd indices.
  const parts = text.split(pattern);

  return (
    <span className={className}>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
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
