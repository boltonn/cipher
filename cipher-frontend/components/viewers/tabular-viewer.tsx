"use client";

import {
  MinusSignCircleIcon,
  PlusSignCircleIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp } from "lucide-react";
import Papa from "papaparse";
import * as React from "react";

import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const ZOOM_OPTIONS = [0.75, 1, 1.25, 1.5, 2] as const;
const COLUMN_WIDTH_PX = 160;
const ROW_HEIGHT_PX = 34;
const HEADER_HEIGHT_PX = 36;

export interface TabularSheet {
  name?: string;
  columns: string[];
  rows: string[][];
  /** Only set for backend-extracted sheets -- the client-side CSV/TSV
   * fallback parses whatever text it fetched with nothing held back. */
  totalRows?: number;
  truncated?: boolean;
}

interface TabularViewerProps {
  sheets: TabularSheet[];
  className?: string;
  /** Lets the truncated-rows notice offer a full-file download. */
  downloadUrl?: string;
  downloadFileName?: string;
}

function toDisplayString(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function normalizeHeaderTitle(header: string, index: number): string {
  const trimmed = header.trim();
  return trimmed.length > 0 ? trimmed : `Column ${index + 1}`;
}

/**
 * Client-side fallback parse for CSV/TSV that hasn't been through the
 * backend extraction pipeline yet -- same `{columns, rows}` shape as the
 * backend's `/files/{id}/table` response, so both feed the same
 * `TabularViewer` without it needing to know which source it came from.
 */
export function parseDelimitedText(text: string): {
  columns: string[];
  rows: string[][];
  error: string | null;
} {
  const results = Papa.parse<Record<string, unknown>>(text, {
    header: true,
    skipEmptyLines: "greedy",
  });

  const objectRows = Array.isArray(results.data)
    ? results.data.filter(
        (row): row is Record<string, unknown> =>
          !!row && typeof row === "object" && !Array.isArray(row)
      )
    : [];
  const metaFields = Array.isArray(results.meta.fields)
    ? results.meta.fields.map((field) => String(field))
    : [];
  const fieldKeys =
    metaFields.length > 0
      ? metaFields
      : Object.keys(objectRows[0] ?? {}).filter(
          (key) => key !== "__parsed_extra"
        );
  const columns = fieldKeys.map((field, index) =>
    normalizeHeaderTitle(field, index)
  );
  const rows = objectRows.map((row) =>
    fieldKeys.map((fieldKey) => toDisplayString(row[fieldKey]))
  );

  const firstError =
    Array.isArray(results.errors) && results.errors.length > 0
      ? results.errors[0]
      : null;

  return {
    columns,
    rows,
    error:
      rows.length === 0 && firstError
        ? String(firstError.message ?? "Could not parse file.")
        : null,
  };
}

function ToolbarTooltip({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">{children}</span>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}

/**
 * Flat tabular data viewer (CSV/TSV/JSON/JSONL/...), row-virtualized with
 * TanStack Virtual so wide/long files stay smooth without paginating --
 * the same virtualization pattern as `components/data-table`, minus that
 * component's backend-paginated sort/filter, since this data is always
 * already fully in memory (sorting is local/client-side).
 */
export function TabularViewer({
  sheets,
  className,
  downloadUrl,
  downloadFileName,
}: TabularViewerProps) {
  const [activeSheetIndex, setActiveSheetIndex] = React.useState(0);
  const [zoom, setZoom] = React.useState<(typeof ZOOM_OPTIONS)[number]>(1);
  const [sort, setSort] = React.useState<{
    columnIndex: number;
    direction: "asc" | "desc";
  } | null>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const sheet = sheets[Math.min(activeSheetIndex, sheets.length - 1)];

  React.useEffect(() => {
    setSort(null);
  }, [activeSheetIndex]);

  const sortedRows = React.useMemo(() => {
    if (!sort) return sheet.rows;
    const collator = new Intl.Collator(undefined, {
      numeric: true,
      sensitivity: "base",
    });
    const sign = sort.direction === "asc" ? 1 : -1;
    return [...sheet.rows].sort(
      (a, b) =>
        sign *
        collator.compare(a[sort.columnIndex] ?? "", b[sort.columnIndex] ?? "")
    );
  }, [sheet.rows, sort]);

  const scale = React.useCallback(
    (value: number) => Math.round(value * zoom),
    [zoom]
  );
  const columnWidth = scale(COLUMN_WIDTH_PX);
  const gridTemplateColumns = `repeat(${sheet.columns.length}, ${columnWidth}px)`;

  const rowVirtualizer = useVirtualizer({
    count: sortedRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => scale(ROW_HEIGHT_PX),
    overscan: 8,
  });

  function toggleSort(columnIndex: number) {
    setSort((current) => {
      if (current?.columnIndex !== columnIndex)
        return { columnIndex, direction: "asc" };
      if (current.direction === "asc")
        return { columnIndex, direction: "desc" };
      return null;
    });
  }

  function stepZoom(direction: -1 | 1) {
    const index = ZOOM_OPTIONS.indexOf(zoom);
    const nextIndex = Math.min(
      ZOOM_OPTIONS.length - 1,
      Math.max(0, index + direction)
    );
    setZoom(ZOOM_OPTIONS[nextIndex]);
  }

  return (
    <div
      className={cn(
        "flex h-[560px] w-full flex-col overflow-hidden bg-background",
        className
      )}
    >
      <div className="flex min-h-12 flex-wrap items-center justify-between gap-2 border-b bg-background px-3 py-2">
        {sheets.length > 1 ? (
          <Tabs
            value={String(activeSheetIndex)}
            onValueChange={(value) => setActiveSheetIndex(Number(value))}
          >
            <TabsList>
              {sheets.map((sheetOption, index) => (
                <TabsTrigger key={index} value={String(index)}>
                  {sheetOption.name ?? `Sheet ${index + 1}`}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        ) : (
          <div />
        )}
        <TooltipProvider>
          <div className="flex flex-none items-center gap-1">
            <ToolbarTooltip label="Zoom out">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Zoom out"
                disabled={zoom <= ZOOM_OPTIONS[0]}
                onClick={() => stepZoom(-1)}
              >
                <HugeiconsIcon icon={MinusSignCircleIcon} className="size-4" />
              </Button>
            </ToolbarTooltip>
            <Select
              value={zoom.toString()}
              onValueChange={(value) =>
                setZoom(Number(value) as (typeof ZOOM_OPTIONS)[number])
              }
            >
              <SelectTrigger
                size="sm"
                className="w-21 min-w-21"
                aria-label="Zoom level"
              >
                <SelectValue>{Math.round(zoom * 100)}%</SelectValue>
              </SelectTrigger>
              <SelectContent align="end">
                {ZOOM_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option.toString()}>
                    {Math.round(option * 100)}%
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ToolbarTooltip label="Zoom in">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Zoom in"
                disabled={zoom >= ZOOM_OPTIONS[ZOOM_OPTIONS.length - 1]}
                onClick={() => stepZoom(1)}
              >
                <HugeiconsIcon icon={PlusSignCircleIcon} className="size-4" />
              </Button>
            </ToolbarTooltip>
          </div>
        </TooltipProvider>
      </div>

      {sheet.truncated ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/60 px-3 py-1.5 text-xs text-muted-foreground">
          <span>
            Showing first {sheet.rows.length.toLocaleString()} of{" "}
            {(sheet.totalRows ?? sheet.rows.length).toLocaleString()} rows.
          </span>
          {downloadUrl && (
            <a href={downloadUrl} download={downloadFileName}>
              <Button variant="ghost" size="sm" className="h-6 gap-1.5 px-2 text-xs">
                <Download className="size-3" /> Download full file
              </Button>
            </a>
          )}
        </div>
      ) : null}

      {sheet.rows.length === 0 ? (
        <div className="grid h-full place-items-center bg-muted/30 p-4">
          <div className="max-w-md rounded-lg border bg-background p-4 text-center text-sm shadow-xs">
            <p className="font-medium">No data to preview</p>
          </div>
        </div>
      ) : (
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
          <div style={{ width: columnWidth * sheet.columns.length }}>
            <div
              className="sticky top-0 z-10 grid border-b bg-muted"
              style={{ gridTemplateColumns }}
            >
              {sheet.columns.map((column, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => toggleSort(index)}
                  className="flex items-center gap-1 truncate border-r px-2 py-2 text-left text-xs font-semibold last:border-r-0 hover:bg-accent"
                  style={{ height: scale(HEADER_HEIGHT_PX) }}
                  title={column}
                >
                  <span className="truncate">{column}</span>
                  {sort?.columnIndex === index &&
                    (sort.direction === "asc" ? (
                      <ArrowUp className="size-3 shrink-0" />
                    ) : (
                      <ArrowDown className="size-3 shrink-0" />
                    ))}
                </button>
              ))}
            </div>
            <div
              style={{
                height: rowVirtualizer.getTotalSize(),
                position: "relative",
              }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const row = sortedRows[virtualRow.index];
                return (
                  <div
                    key={virtualRow.key}
                    className="absolute top-0 left-0 grid w-full border-b"
                    style={{
                      gridTemplateColumns,
                      height: virtualRow.size,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    {sheet.columns.map((_, colIndex) => (
                      <div
                        key={colIndex}
                        className="truncate border-r px-2 py-1.5 last:border-r-0"
                        style={{ fontSize: `${scale(13)}px` }}
                        title={row[colIndex]}
                      >
                        {row[colIndex] ?? ""}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
