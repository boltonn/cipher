"use client";

import type * as GlideDataGrid from "@glideapps/glide-data-grid";
import type {
  GridCell,
  GridCellKind,
  GridColumn,
  Item,
  Rectangle,
  Theme,
} from "@glideapps/glide-data-grid";
import * as React from "react";
import { createPortal } from "react-dom";

import "@glideapps/glide-data-grid/dist/index.css";

import {
  MinusSignCircleIcon,
  PlusSignCircleIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import Papa from "papaparse";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const ZOOM_OPTIONS = [0.75, 1, 1.25, 1.5, 2] as const;

type GlideDataGridModule = typeof GlideDataGrid;
type CsvViewerProps = {
  className?: string;
  data?: string;
};

function toDisplayString(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function normalizeHeaderTitle(header: string, index: number): string {
  const trimmed = header.trim();
  return trimmed.length > 0 ? trimmed : `Column ${index + 1}`;
}

function parseDelimitedText(text: string): {
  headers: string[];
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
  const extraColumnCount = objectRows.reduce((maxCount, row) => {
    const extras = row.__parsed_extra;
    return Array.isArray(extras) ? Math.max(maxCount, extras.length) : maxCount;
  }, 0);
  const headers = [
    ...fieldKeys.map((field, index) => normalizeHeaderTitle(field, index)),
    ...Array.from(
      { length: extraColumnCount },
      (_, index) => `Extra ${index + 1}`
    ),
  ];

  const rows = objectRows.map((row) => {
    const baseValues = fieldKeys.map((fieldKey) =>
      toDisplayString(row[fieldKey])
    );
    const extras = Array.isArray(row.__parsed_extra)
      ? row.__parsed_extra.map((value) => toDisplayString(value))
      : [];
    const paddedExtras =
      extras.length >= extraColumnCount
        ? extras.slice(0, extraColumnCount)
        : [
            ...extras,
            ...Array.from(
              { length: extraColumnCount - extras.length },
              () => ""
            ),
          ];

    return [...baseValues, ...paddedExtras];
  });

  const firstError =
    Array.isArray(results.errors) && results.errors.length > 0
      ? results.errors[0]
      : null;

  return {
    headers,
    rows,
    error:
      rows.length === 0 && firstError
        ? String(firstError.message ?? "Could not parse CSV file.")
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

function readIsDarkTheme() {
  return (
    typeof document !== "undefined" &&
    document.documentElement.classList.contains("dark")
  );
}

function useIsDarkTheme() {
  const [isDark, setIsDark] = React.useState(readIsDarkTheme);

  React.useEffect(() => {
    if (typeof document === "undefined") return;

    const updateTheme = () => setIsDark(readIsDarkTheme());

    if (typeof MutationObserver === "undefined") return;

    const observer = new MutationObserver(updateTheme);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, []);

  return isDark;
}

export function CsvViewer({ className, data }: CsvViewerProps) {
  const isDark = useIsDarkTheme();
  const [glide, setGlide] = React.useState<GlideDataGridModule | null>(null);
  const [zoom, setZoom] = React.useState<(typeof ZOOM_OPTIONS)[number]>(1);
  const parsed = React.useMemo(
    () => (data ? parseDelimitedText(data) : { headers: [], rows: [], error: null }),
    [data]
  );
  const headerKey = React.useMemo(
    () => parsed.headers.join("\u0001"),
    [parsed.headers]
  );
  const [gridStateByHeader, setGridStateByHeader] = React.useState<
    Record<
      string,
      {
        columnWidths: Record<number, number>;
        sort: {
          columnIndex: number;
          direction: "ascending" | "descending";
        } | null;
        sortMenu: {
          columnIndex: number;
          bounds: Rectangle;
        } | null;
      }
    >
  >({});
  const { columnWidths, sort, sortMenu } = gridStateByHeader[headerKey] ?? {
    columnWidths: {},
    sort: null,
    sortMenu: null,
  };

  const updateGridState = React.useCallback(
    (
      updater: (current: {
        columnWidths: Record<number, number>;
        sort: { columnIndex: number; direction: "ascending" | "descending" } | null;
        sortMenu: { columnIndex: number; bounds: Rectangle } | null;
      }) => Partial<{
        columnWidths: Record<number, number>;
        sort: { columnIndex: number; direction: "ascending" | "descending" } | null;
        sortMenu: { columnIndex: number; bounds: Rectangle } | null;
      }>
    ) => {
      setGridStateByHeader((prev) => {
        const current = prev[headerKey] ?? {
          columnWidths: {},
          sort: null,
          sortMenu: null,
        };
        return { ...prev, [headerKey]: { ...current, ...updater(current) } };
      });
    },
    [headerKey]
  );

  const sortedRowIndices = React.useMemo(() => {
    const indices = parsed.rows.map((_, index) => index);
    if (!sort) return indices;

    const collator = new Intl.Collator(undefined, {
      numeric: true,
      sensitivity: "base",
    });
    const sign = sort.direction === "ascending" ? 1 : -1;
    return indices.sort(
      (a, b) =>
        sign *
        collator.compare(
          parsed.rows[a]?.[sort.columnIndex] ?? "",
          parsed.rows[b]?.[sort.columnIndex] ?? ""
        )
    );
  }, [parsed.rows, sort]);

  React.useEffect(() => {
    let mounted = true;

    void import("@glideapps/glide-data-grid").then((module) => {
      if (mounted) {
        setGlide(module);
      }
    });

    return () => {
      mounted = false;
    };
  }, []);

  const columnCount = Math.max(1, parsed.headers.length);
  const scale = React.useCallback(
    (value: number) => Math.round(value * zoom),
    [zoom]
  );

  const theme = React.useMemo<Partial<Theme>>(
    () => ({
      accentColor: isDark ? "#60a5fa" : "#2563eb",
      accentLight: isDark ? "#1d4ed826" : "#dbeafe",
      accentFg: "#ffffff",
      textDark: isDark ? "#e5e5e5" : "#171717",
      textMedium: isDark ? "#a3a3a3" : "#525252",
      textLight: isDark ? "#737373" : "#a3a3a3",
      textBubble: isDark ? "#f5f5f5" : "#171717",
      textHeader: isDark ? "#f5f5f5" : "#171717",
      textGroupHeader: isDark ? "#a3a3a3" : "#525252",
      bgCell: isDark ? "#0a0a0a" : "#ffffff",
      bgCellMedium: isDark ? "#171717" : "#fafafa",
      bgHeader: isDark ? "#171717" : "#fafafa",
      bgHeaderHasFocus: isDark ? "#262626" : "#f5f5f5",
      bgHeaderHovered: isDark ? "#262626" : "#f5f5f5",
      borderColor: isDark ? "#262626" : "#e5e5e5",
      horizontalBorderColor: isDark ? "#262626" : "#e5e5e5",
      cellHorizontalPadding: scale(8),
      cellVerticalPadding: Math.max(2, scale(3)),
      headerIconSize: scale(18),
      baseFontStyle: `${scale(13)}px`,
      headerFontStyle: `600 ${scale(13)}px`,
      markerFontStyle: `${scale(11)}px`,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      editorFontSize: `${scale(13)}px`,
    }),
    [isDark, scale]
  );

  const columns = React.useMemo<GridColumn[]>(
    () =>
      Array.from({ length: columnCount }, (_, index) => {
        const baseTitle = parsed.headers[index] ?? `Column ${index + 1}`;
        const title =
          sort?.columnIndex === index
            ? `${baseTitle} ${sort.direction === "ascending" ? "▲" : "▼"}`
            : baseTitle;

        return {
          id: `column-${index}`,
          title,
          width: columnWidths[index] ?? scale(index === 0 ? 180 : 160),
          hasMenu: true,
          menuIcon: "dots",
        };
      }),
    [columnCount, columnWidths, parsed.headers, scale, sort]
  );

  const getCellContent = React.useCallback(
    ([col, row]: Item): GridCell => {
      const rowIndex = sortedRowIndices[row] ?? row;
      const value = parsed.rows[rowIndex]?.[col] ?? "";
      const textKind = glide?.GridCellKind.Text as GridCellKind.Text;

      return {
        kind: textKind,
        data: value,
        displayData: value,
        allowOverlay: true,
        readonly: true,
      };
    },
    [glide, parsed.rows, sortedRowIndices]
  );

  const handleColumnResize = React.useCallback(
    (_column: GridColumn, newSize: number, colIndex: number) => {
      updateGridState((current) => ({
        columnWidths: { ...current.columnWidths, [colIndex]: newSize },
      }));
    },
    [updateGridState]
  );

  const handleHeaderMenuClick = React.useCallback(
    (col: number, bounds: Rectangle) => {
      // Not a toggle: glide-data-grid can fire this more than once for a
      // single click, and toggling on identical (col, bounds) would flip the
      // menu straight back to closed on the second call.
      updateGridState(() => ({ sortMenu: { columnIndex: col, bounds } }));
    },
    [updateGridState]
  );

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
      <div className="flex min-h-12 flex-wrap items-center justify-end gap-2 border-b bg-background px-3 py-2">
        <TooltipProvider>
          <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-1">
            <div className="flex flex-none items-center gap-1">
              <ToolbarTooltip label="Zoom out">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Zoom out"
                  disabled={zoom <= ZOOM_OPTIONS[0]}
                  onClick={() => stepZoom(-1)}
                >
                  <HugeiconsIcon
                    icon={MinusSignCircleIcon}
                    className="size-4"
                  />
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
          </div>
        </TooltipProvider>
      </div>
      <div className="min-h-0 flex-1">
        {parsed.error ? (
          <div className="flex h-full items-center justify-center px-4 text-center text-sm text-destructive">
            {parsed.error}
          </div>
        ) : parsed.rows.length === 0 ? (
          <div className="grid h-full place-items-center bg-muted/30 p-4">
            <div className="max-w-md rounded-lg border bg-background p-4 text-center text-sm shadow-xs">
              <p className="font-medium">No data to preview</p>
              <p className="mt-1 text-muted-foreground">
                Pass delimited text with the <code>data</code> prop.
              </p>
            </div>
          </div>
        ) : !glide ? (
          <div className="grid h-full place-items-center bg-background">
            <Spinner className="size-4" />
          </div>
        ) : (
          <glide.DataEditor
            key={zoom}
            columns={columns}
            rows={parsed.rows.length}
            getCellContent={getCellContent}
            rowMarkers="number"
            rowSelectionMode="multi"
            keybindings={{ search: true }}
            smoothScrollX
            smoothScrollY
            getCellsForSelection
            width="100%"
            height="100%"
            theme={theme}
            rowHeight={scale(34)}
            headerHeight={scale(36)}
            onColumnResize={handleColumnResize}
            onHeaderMenuClick={handleHeaderMenuClick}
          />
        )}
      </div>
      {sortMenu ? (
        <ColumnSortMenu
          bounds={sortMenu.bounds}
          currentDirection={
            sort?.columnIndex === sortMenu.columnIndex
              ? sort.direction
              : undefined
          }
          onClose={() => updateGridState(() => ({ sortMenu: null }))}
          onSort={(direction) => {
            updateGridState(() => ({
              sort: direction ? { columnIndex: sortMenu.columnIndex, direction } : null,
              sortMenu: null,
            }));
          }}
        />
      ) : null}
    </div>
  );
}

function ColumnSortMenu({
  bounds,
  currentDirection,
  onClose,
  onSort,
}: {
  bounds: Rectangle;
  currentDirection?: "ascending" | "descending";
  onClose: () => void;
  onSort: (direction: "ascending" | "descending" | null) => void;
}) {
  const menuRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node))
        onClose();
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  const itemClass = (active: boolean) =>
    cn(
      "flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground",
      active && "bg-accent text-accent-foreground"
    );

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-50 w-40 rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
      style={{ left: bounds.x, top: bounds.y + bounds.height }}
    >
      <button
        type="button"
        className={itemClass(currentDirection === "ascending")}
        onClick={() => onSort("ascending")}
      >
        Sort ascending
      </button>
      <button
        type="button"
        className={itemClass(currentDirection === "descending")}
        onClick={() => onSort("descending")}
      >
        Sort descending
      </button>
      {currentDirection ? (
        <button
          type="button"
          className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          onClick={() => onSort(null)}
        >
          Clear sort
        </button>
      ) : null}
    </div>,
    document.body
  );
}
