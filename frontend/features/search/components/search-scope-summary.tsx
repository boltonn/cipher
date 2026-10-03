"use client";

import { format } from "date-fns";
import { Fragment, type ReactNode } from "react";
import type { SearchFilters, SearchMode } from "../types";
import { EntityName, mentionWhere } from "./search-filters-bar";

interface SearchScopeSummaryProps {
  query: string;
  searchMode: SearchMode;
  filters: SearchFilters;
  /** Exact matching-file count; null when the mode has none (semantic / hybrid rank without a cut-off). */
  total: number | null;
}

function EntityList({ ids, joiner }: { ids: string[]; joiner: string }) {
  return ids.map((id, index) => (
    <Fragment key={id}>
      {index > 0 && ` ${joiner} `}
      <span className="font-medium text-annotation">
        <EntityName entityId={id} />
      </span>
    </Fragment>
  ));
}

const day = (iso: string) => format(new Date(iso), "MMM d, yyyy");

/** One plain-language sentence saying exactly what the result list is. */
export function SearchScopeSummary({ query, searchMode, filters, total }: SearchScopeSummaryProps) {
  const { entityIds = [], mentionValues = [], sentFrom = [], sentTo = [], dateFrom, dateTo } = filters;
  const noun = filters.filetypeGroup === "email" ? "email" : filters.filetypeGroup === "document" ? "document" : "file";
  const trimmed = query.trim();

  const clauses: ReactNode[] = [];
  if (trimmed) {
    clauses.push(
      <>
        matching <span className="font-medium text-foreground">“{trimmed}”</span> ({searchMode})
      </>
    );
  }
  if (entityIds.length) clauses.push(<>with a passage that mentions <EntityList ids={entityIds} joiner="and" /></>);
  if (mentionValues.length) {
    clauses.push(
      <>
        with a mention of{" "}
        {mentionValues.map((value, index) => (
          <Fragment key={value}>
            {index > 0 && " and "}
            <span className="font-medium text-annotation">“{value}”</span>
          </Fragment>
        ))}
        {filters.mentionProvenance && ` ${mentionWhere(filters.mentionProvenance).label.toLowerCase()}`}
      </>
    );
  }
  if (sentFrom.length) clauses.push(<>sent by <EntityList ids={sentFrom} joiner="or" /></>);
  if (sentTo.length) clauses.push(<>sent to <EntityList ids={sentTo} joiner="or" /></>);
  if (dateFrom && dateTo) clauses.push(<>dated {day(dateFrom)} – {day(dateTo)}</>);
  else if (dateFrom) clauses.push(<>dated on or after {day(dateFrom)}</>);
  else if (dateTo) clauses.push(<>dated on or before {day(dateTo)}</>);
  const only = [...(filters.messageStates ?? []), ...(filters.sourceTags ?? [])];
  const hidden = [...(filters.excludeMessageStates ?? []), ...(filters.excludeSourceTags ?? [])];
  if (only.length) clauses.push(<>marked {only.join(" or ")} in the data</>);
  if (hidden.length) clauses.push(<>not marked {hidden.join(" or ")} in the data</>);

  return (
    <p className="px-1 text-xs text-muted-foreground">
      {total === null ? (
        <>Closest {noun}s</>
      ) : (
        <>
          <span className="font-semibold text-foreground">{total.toLocaleString()}</span> {noun}
          {total === 1 ? "" : "s"}
        </>
      )}
      {clauses.map((clause, index) => (
        <Fragment key={index}> {clause}{index < clauses.length - 1 && ","}</Fragment>
      ))}
      {trimmed ? " — best match first." : " — newest first."}
      {!trimmed && (entityIds.length > 0 || mentionValues.length > 0) && " Type a query to search within them."}
    </p>
  );
}
