"use client";

import {
  useXlsxViewer,
  useXlsxViewerController,
  useXlsxViewerThumbnails,
  useXlsxViewerZoom,
  XlsxViewer,
  XlsxViewerProvider,
  type XlsxScrollerRenderProps,
  type XlsxTableHeaderMenuRenderProps,
} from "@extend-ai/react-xlsx";
import {
  MinusSignCircleIcon,
  Moon02Icon,
  MoreHorizontalIcon,
  PlusSignCircleIcon,
  Sun03Icon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import Image from "next/image";
import { ScrollArea as ScrollAreaPrimitive } from "radix-ui";
import * as React from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const XLSX_LOADING_INDICATOR_DELAY_MS = 300;
const XLSX_DROPDOWN_Z_INDEX_CLASS = "z-40";
const ZOOM_OPTIONS = [10, 25, 50, 75, 100, 125, 150, 175, 200, 400] as const;

const SHEET_TAB_PREVIEW_WIDTH = 220;
const SHEET_TAB_PREVIEW_HEIGHT = (SHEET_TAB_PREVIEW_WIDTH * 7) / 11;
const SHEET_TAB_PREVIEW_GAP = 12;
const SHEET_TAB_PREVIEW_OPEN_DELAY_MS = 500;

// Stable reference so the thumbnails memo isn't invalidated on every render
// (e.g. by selection changes), which would recompute every sheet thumbnail.
const XLSX_SHEET_TAB_THUMBNAIL_OPTIONS = {
  resolution: {
    maxHeight: 360,
    maxWidth: 560,
  },
} as const;

function formatWorkbookName(fileName: string | undefined, url: string) {
  if (fileName?.trim()) return fileName;

  const pathname = url.split("?")[0] ?? "";
  const rawName = pathname.split("/").pop() ?? "workbook.xlsx";

  try {
    return decodeURIComponent(rawName);
  } catch {
    return rawName;
  }
}

function useDelayedLoadingIndicator(isLoading: boolean, delayMs: number) {
  const [timerFired, setTimerFired] = React.useState(false);

  React.useEffect(() => {
    if (!isLoading) return;
    const timeoutId = window.setTimeout(() => setTimerFired(true), delayMs);
    return () => {
      window.clearTimeout(timeoutId);
      setTimerFired(false);
    };
  }, [delayMs, isLoading]);

  return isLoading && timerFired;
}

export function useControllableDarkMode({
  defaultIsDark = false,
  isDark,
  onIsDarkChange,
}: {
  defaultIsDark?: boolean;
  isDark?: boolean;
  onIsDarkChange?: (isDark: boolean) => void;
}) {
  const [uncontrolledIsDark, setUncontrolledIsDark] =
    React.useState(defaultIsDark);
  const resolvedIsDark = isDark ?? uncontrolledIsDark;

  const setIsDark = React.useCallback(
    (nextIsDark: boolean) => {
      if (isDark === undefined) {
        setUncontrolledIsDark(nextIsDark);
      }

      onIsDarkChange?.(nextIsDark);
    },
    [isDark, onIsDarkChange]
  );

  return [resolvedIsDark, setIsDark] as const;
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

function ViewerLoadingSurface({
  showSpinner = true,
}: {
  showSpinner?: boolean;
}) {
  return (
    <div className="grid h-full min-h-52 w-full min-w-full place-items-center bg-transparent">
      {showSpinner ? <Spinner className="size-4" /> : null}
    </div>
  );
}

function renderXlsxScroller({
  children,
  viewportProps,
}: XlsxScrollerRenderProps) {
  const { className: viewportClassName, key, style, ...restViewportProps } = viewportProps;
  // Radix's Viewport applies its own overflowX/overflowY inline; keeping the
  // library's shorthand `overflow` alongside those longhands is what trips
  // React's "conflicting style property" warning on rerender.
  const restStyle = { ...style };
  delete restStyle.overflow;

  return (
    <ScrollAreaPrimitive.Root
      data-slot="scroll-area"
      className="relative h-full min-h-0 w-full min-w-0 flex-1"
    >
      <ScrollAreaPrimitive.Viewport
        key={key}
        {...restViewportProps}
        style={restStyle}
        data-slot="scroll-area-viewport"
        className={cn(
          "size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1",
          viewportClassName
        )}
      >
        {children}
      </ScrollAreaPrimitive.Viewport>
      <ScrollBar />
      <ScrollAreaPrimitive.Corner />
    </ScrollAreaPrimitive.Root>
  );
}

export function WorkbookTableHeaderMenu({
  direction,
  sortAscending,
  sortDescending,
  triggerIcon,
  triggerProps,
}: XlsxTableHeaderMenuRenderProps) {
  const [open, setOpen] = React.useState(false);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          {...triggerProps}
          type="button"
          variant="ghost"
          size="icon-sm"
          className={cn("size-6 rounded-sm", triggerProps.className)}
          aria-label="Column menu"
        >
          {triggerIcon ? (
            triggerIcon
          ) : (
            <HugeiconsIcon icon={MoreHorizontalIcon} className="size-3.5" />
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className={cn("w-40", XLSX_DROPDOWN_Z_INDEX_CLASS)}
      >
        <DropdownMenuRadioGroup
          value={direction ?? ""}
          onValueChange={(value) => {
            if (value === "ascending") {
              sortAscending();
            } else {
              sortDescending();
            }
            setOpen(false);
          }}
        >
          <DropdownMenuRadioItem value="ascending">
            Sort ascending
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="descending">
            Sort descending
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function WorkbookToolbar({
  isDark,
  onIsDarkChange,
  showNightRenderToggle,
  workbookIdentity,
}: {
  isDark: boolean;
  onIsDarkChange: (checked: boolean) => void;
  showNightRenderToggle: boolean;
  workbookIdentity: string;
}) {
  const { canZoomIn, canZoomOut, setZoomScale, zoomIn, zoomOut, zoomScale } =
    useXlsxViewerZoom();
  const currentZoom = Math.round(zoomScale);

  React.useEffect(() => {
    setZoomScale(100);
  }, [setZoomScale, workbookIdentity]);

  return (
    <div className="flex min-h-12 flex-wrap items-center justify-end gap-2 border-b bg-background px-3 py-2">
      <TooltipProvider>
        <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-1">
          {showNightRenderToggle ? (
            <ToolbarTooltip
              label={isDark ? "Use light workbook" : "Use dark workbook"}
            >
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={isDark ? "Use light workbook" : "Use dark workbook"}
                onClick={() => onIsDarkChange(!isDark)}
              >
                <HugeiconsIcon
                  icon={isDark ? Sun03Icon : Moon02Icon}
                  className="size-4"
                />
              </Button>
            </ToolbarTooltip>
          ) : null}
          <Separator orientation="vertical" className="mx-1 h-4 self-center" />
          <div className="flex flex-none items-center gap-1">
            <ToolbarTooltip label="Zoom out">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                disabled={!canZoomOut}
                aria-label="Zoom out"
                onClick={zoomOut}
              >
                <HugeiconsIcon icon={MinusSignCircleIcon} className="size-4" />
              </Button>
            </ToolbarTooltip>
            <Select
              value={currentZoom.toString()}
              onValueChange={(value) => setZoomScale(Number(value))}
            >
              <SelectTrigger
                size="sm"
                className="w-21 min-w-21"
                aria-label="Zoom level"
              >
                <SelectValue>{currentZoom}%</SelectValue>
              </SelectTrigger>
              <SelectContent
                align="end"
                className={XLSX_DROPDOWN_Z_INDEX_CLASS}
              >
                {ZOOM_OPTIONS.map((value) => (
                  <SelectItem key={value} value={value.toString()}>
                    {value}%
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ToolbarTooltip label="Zoom in">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                disabled={!canZoomIn}
                aria-label="Zoom in"
                onClick={zoomIn}
              >
                <HugeiconsIcon icon={PlusSignCircleIcon} className="size-4" />
              </Button>
            </ToolbarTooltip>
          </div>
        </div>
      </TooltipProvider>
    </div>
  );
}

type WorkbookSheetTab = {
  name: string;
  workbookSheetIndex: number;
};

type WorkbookSheetTabsInnerProps = {
  activeSheetIndex: number;
  onActiveSheetIndexChange: (index: number) => void;
  sheets: WorkbookSheetTab[];
  workbookIdentity: string;
};

export function WorkbookSheetTabs({
  workbookIdentity,
}: {
  workbookIdentity: string;
}) {
  const { activeSheetIndex, setActiveSheetIndex, sheets } = useXlsxViewer();

  const handleActiveSheetIndexChange = React.useCallback(
    (index: number) => setActiveSheetIndex(index),
    [setActiveSheetIndex]
  );

  return (
    <WorkbookSheetTabsInner
      key={workbookIdentity}
      activeSheetIndex={activeSheetIndex}
      onActiveSheetIndexChange={handleActiveSheetIndexChange}
      sheets={sheets}
      workbookIdentity={workbookIdentity}
    />
  );
}

const WorkbookSheetTabsInner = React.memo(function WorkbookSheetTabsInner({
  activeSheetIndex,
  onActiveSheetIndexChange,
  sheets,
  workbookIdentity,
}: WorkbookSheetTabsInnerProps) {
  const [visiblePreviewIndex, setVisiblePreviewIndex] = React.useState<
    number | null
  >(null);
  const [previewPosition, setPreviewPosition] = React.useState({
    left: 0,
    top: 0,
  });
  const { thumbnails } = useXlsxViewerThumbnails(
    XLSX_SHEET_TAB_THUMBNAIL_OPTIONS
  );
  const [thumbnailUrls, setThumbnailUrls] = React.useState<
    Record<number, string>
  >({});
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const itemRefs = React.useRef<Record<number, HTMLButtonElement | null>>({});
  const openTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const closeTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null
  );

  const clearOpenTimeout = React.useCallback(() => {
    if (openTimeoutRef.current) {
      clearTimeout(openTimeoutRef.current);
      openTimeoutRef.current = null;
    }
  }, []);

  const clearCloseTimeout = React.useCallback(() => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
  }, []);

  const getPreviewPosition = React.useCallback((sheetIndex: number) => {
    const item = itemRefs.current[sheetIndex];
    if (!item || typeof window === "undefined") {
      return { left: 0, top: 0 };
    }

    const itemRect = item.getBoundingClientRect();
    const centeredLeft =
      itemRect.left + itemRect.width / 2 - SHEET_TAB_PREVIEW_WIDTH / 2;
    const minLeft = 8;
    const maxLeft = Math.max(
      minLeft,
      window.innerWidth - SHEET_TAB_PREVIEW_WIDTH - 8
    );
    const left = Math.max(minLeft, Math.min(centeredLeft, maxLeft));
    const top = Math.max(
      8,
      itemRect.top - SHEET_TAB_PREVIEW_HEIGHT - SHEET_TAB_PREVIEW_GAP
    );

    return { left, top };
  }, []);

  const updatePreviewPosition = React.useCallback(
    (sheetIndex: number) => {
      setPreviewPosition(getPreviewPosition(sheetIndex));
    },
    [getPreviewPosition]
  );
  const updatePreviewPositionRef = React.useRef(updatePreviewPosition);
  React.useLayoutEffect(() => {
    updatePreviewPositionRef.current = updatePreviewPosition;
  });

  const handleItemEnter = React.useCallback(
    (sheetIndex: number) => {
      clearCloseTimeout();
      const nextPreviewPosition = getPreviewPosition(sheetIndex);

      if (visiblePreviewIndex !== null) {
        clearOpenTimeout();
        setPreviewPosition(nextPreviewPosition);
        setVisiblePreviewIndex(sheetIndex);
        return;
      }

      clearOpenTimeout();
      openTimeoutRef.current = setTimeout(() => {
        setPreviewPosition(nextPreviewPosition);
        setVisiblePreviewIndex(sheetIndex);
      }, SHEET_TAB_PREVIEW_OPEN_DELAY_MS);
    },
    [
      clearCloseTimeout,
      clearOpenTimeout,
      getPreviewPosition,
      visiblePreviewIndex,
    ]
  );

  const handleContainerLeave = React.useCallback(() => {
    clearOpenTimeout();
    clearCloseTimeout();
    closeTimeoutRef.current = setTimeout(() => {
      setVisiblePreviewIndex(null);
    }, 80);
  }, [clearCloseTimeout, clearOpenTimeout]);

  React.useEffect(() => {
    return () => {
      clearOpenTimeout();
      clearCloseTimeout();
    };
  }, [clearCloseTimeout, clearOpenTimeout]);

  React.useEffect(() => {
    thumbnails.forEach((thumbnail) => {
      setThumbnailUrls((current) => {
        if (current[thumbnail.sheetIndex]) return current;

        const canvas = document.createElement("canvas");
        canvas.width = thumbnail.width;
        canvas.height = thumbnail.height;

        if (!thumbnail.paint(canvas)) return current;

        return {
          ...current,
          [thumbnail.sheetIndex]: canvas.toDataURL("image/png"),
        };
      });
    });
  }, [thumbnails]);

  React.useEffect(() => {
    if (visiblePreviewIndex === null) return;

    const handleReposition = () =>
      updatePreviewPositionRef.current(visiblePreviewIndex);
    handleReposition();

    const scrollElement = scrollRef.current;
    window.addEventListener("resize", handleReposition);
    scrollElement?.addEventListener("scroll", handleReposition, {
      passive: true,
    });

    return () => {
      window.removeEventListener("resize", handleReposition);
      scrollElement?.removeEventListener("scroll", handleReposition);
    };
  }, [visiblePreviewIndex]);

  if (sheets.length <= 1) return null;

  const previewSheet =
    visiblePreviewIndex === null ? null : sheets[visiblePreviewIndex];
  const previewUrl =
    visiblePreviewIndex === null
      ? null
      : (thumbnailUrls[visiblePreviewIndex] ?? null);

  return (
    <div
      className="border-t bg-muted/40 px-3 py-2"
      onMouseLeave={handleContainerLeave}
    >
      <Tabs
        value={String(activeSheetIndex)}
        onValueChange={(value) => onActiveSheetIndexChange(Number(value))}
        className="gap-0"
      >
        <ScrollArea
          orientation="horizontal"
          scrollbarGutter
          className="h-10 w-full has-[[data-slot=scroll-area-viewport][data-has-overflow-x]]:h-12.5"
          viewportClassName="overflow-y-hidden"
          viewportRef={scrollRef}
        >
          <div className="flex h-full items-center">
            <TabsList className="shrink-0">
              {sheets.map((sheet, index) => (
                <TabsTrigger
                  key={`${sheet.workbookSheetIndex}-${sheet.name}`}
                  ref={(node) => {
                    itemRefs.current[index] = node;
                  }}
                  value={String(index)}
                  className="max-w-48 flex-none"
                  onMouseEnter={() => handleItemEnter(index)}
                >
                  <span className="truncate">{sheet.name}</span>
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
        </ScrollArea>
      </Tabs>
      {typeof document !== "undefined" &&
      previewSheet &&
      visiblePreviewIndex !== null &&
      previewUrl
        ? createPortal(
            <div
              className="pointer-events-none fixed z-40 translate-y-0 overflow-hidden rounded-lg border bg-background/95 opacity-100 shadow-xl backdrop-blur-md transition-[opacity,transform] duration-100"
              style={{
                left: previewPosition.left,
                top: previewPosition.top,
                width: SHEET_TAB_PREVIEW_WIDTH,
              }}
            >
              <div className="relative aspect-11/7 w-full overflow-hidden bg-muted/60">
                <Image
                  key={`${workbookIdentity}-${visiblePreviewIndex}-${previewUrl}`}
                  src={previewUrl}
                  alt={`${previewSheet.name} preview`}
                  fill
                  sizes="320px"
                  unoptimized
                  className="object-cover object-top-left"
                />
              </div>
            </div>,
            document.body
          )
        : null}
    </div>
  );
});

export function XlsxWorkbookSurface({
  className,
  isDark,
  onIsDarkChange,
  renderTableHeaderMenu,
  rounded,
  showNightRenderToggle,
  workbookIdentity,
}: {
  className?: string;
  isDark: boolean;
  onIsDarkChange: (checked: boolean) => void;
  renderTableHeaderMenu: (
    props: XlsxTableHeaderMenuRenderProps
  ) => React.ReactNode;
  rounded: boolean;
  showNightRenderToggle: boolean;
  workbookIdentity: string;
}) {
  const { error } = useXlsxViewer();

  const fileTooLargeState = React.useMemo(
    () => (
      <div className="grid h-full w-full min-w-full place-items-center p-6">
        <div className="max-w-sm rounded-lg border bg-background p-4 text-sm">
          <p className="font-medium">File too large</p>
          <p className="mt-1 text-muted-foreground">
            This workbook exceeds the display limit. Download it to view the
            full file.
          </p>
        </div>
      </div>
    ),
    []
  );
  const loadingState = React.useMemo(() => <ViewerLoadingSurface />, []);
  const errorState = React.useMemo(
    () => (
      <div className="grid h-full w-full min-w-full place-items-center p-6 text-sm text-destructive">
        {error?.message ?? "Unable to display workbook."}
      </div>
    ),
    [error?.message]
  );

  return (
    <div
      className={cn(
        "flex h-160 min-h-0 flex-col overflow-hidden bg-background",
        className,
        rounded && "rounded-lg"
      )}
    >
      <WorkbookToolbar
        isDark={isDark}
        onIsDarkChange={onIsDarkChange}
        showNightRenderToggle={showNightRenderToggle}
        workbookIdentity={workbookIdentity}
      />
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 bg-muted/20">
          <XlsxViewer
            experimentalCanvas
            allowResizeInReadOnly
            className="h-full min-h-0 min-w-0"
            height="100%"
            isDark={isDark}
            readOnly
            rounded={false}
            showDefaultToolbar={false}
            showImages
            fileTooLargeState={fileTooLargeState}
            loadingState={loadingState}
            renderScroller={renderXlsxScroller}
            errorState={errorState}
            renderTableHeaderMenu={renderTableHeaderMenu}
          />
        </div>
        <WorkbookSheetTabs workbookIdentity={workbookIdentity} />
      </div>
    </div>
  );
}

export function XlsxViewerPreview({
  className,
  defaultIsDark = false,
  fileName,
  isDark: controlledIsDark,
  onIsDarkChange,
  rounded = false,
  src,
}: {
  className?: string;
  defaultIsDark?: boolean;
  fileName?: string;
  isDark?: boolean;
  onIsDarkChange?: (isDark: boolean) => void;
  rounded?: boolean;
  src?: string;
}) {
  const [effectiveIsDark, setIsDark] = useControllableDarkMode({
    defaultIsDark,
    isDark: controlledIsDark,
    onIsDarkChange,
  });

  return (
    <XlsxViewerContent
      className={className}
      effectiveIsDark={effectiveIsDark}
      fileName={fileName}
      rounded={rounded}
      setNightRenderEnabled={setIsDark}
      shouldRenderNightMode
      url={src}
    />
  );
}

function XlsxViewerContent({
  className,
  effectiveIsDark,
  fileName,
  rounded,
  setNightRenderEnabled,
  shouldRenderNightMode,
  url,
}: {
  className?: string;
  effectiveIsDark: boolean;
  fileName?: string;
  rounded: boolean;
  setNightRenderEnabled: (checked: boolean) => void;
  shouldRenderNightMode: boolean;
  url?: string;
}) {
  const displayFileName = React.useMemo(
    () => (url ? formatWorkbookName(fileName, url) : (fileName ?? "workbook.xlsx")),
    [fileName, url]
  );
  const workbookIdentity = React.useMemo(
    () => `${url ?? "empty"}::${displayFileName}`,
    [displayFileName, url]
  );
  const [workbookBuffer, setWorkbookBuffer] =
    React.useState<ArrayBuffer | null>(null);
  const [loadError, setLoadError] = React.useState<string>();
  const shouldShowLoadingSpinner = useDelayedLoadingIndicator(
    !workbookBuffer && !loadError,
    XLSX_LOADING_INDICATOR_DELAY_MS
  );

  React.useEffect(() => {
    let isCurrent = true;

    async function loadWorkbook(): Promise<void> {
      if (!url) {
        setWorkbookBuffer(null);
        setLoadError(undefined);
        return;
      }

      setWorkbookBuffer(null);
      setLoadError(undefined);

      try {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`Failed to fetch XLSX (${response.status})`);
        }

        if (!isCurrent) return;
        const nextWorkbookBuffer = await response.arrayBuffer();

        setWorkbookBuffer(nextWorkbookBuffer);
      } catch (error) {
        if (!isCurrent) return;

        setLoadError(
          error instanceof Error ? error.message : "Unknown XLSX load error"
        );
      }
    }

    void loadWorkbook();

    return () => {
      isCurrent = false;
    };
  }, [url]);

  if (!url) {
    return (
      <div
        className={cn(
          "flex h-160 min-h-0 flex-col overflow-hidden bg-background",
          className
        )}
      >
        <div className="grid min-h-0 flex-1 place-items-center bg-muted/30 p-4">
          <div className="max-w-md rounded-lg border bg-background p-4 text-center text-sm shadow-xs">
            <p className="font-medium">No workbook to preview</p>
            <p className="mt-1 text-muted-foreground">
              Pass an XLSX URL with the <code>src</code> prop.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (loadError && !workbookBuffer) {
    return (
      <div
        className={cn(
          "flex h-160 min-h-0 flex-col overflow-hidden bg-background",
          className
        )}
      >
        <div className="grid min-h-0 flex-1 place-items-center bg-muted/30 p-4">
          <div className="max-w-md rounded-lg border bg-background p-4 text-sm">
            <p className="font-medium">Unable to display workbook</p>
            <p className="mt-1 text-muted-foreground">{loadError}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!workbookBuffer) {
    return (
      <div
        className={cn(
          "flex h-160 min-h-0 flex-col overflow-hidden bg-background",
          className
        )}
      >
        <ViewerLoadingSurface showSpinner={shouldShowLoadingSpinner} />
      </div>
    );
  }

  return (
    <div className={cn("overflow-hidden", className)}>
      <XlsxWorkbookLoadedViewer
        fileName={displayFileName}
        isDark={effectiveIsDark}
        onIsDarkChange={setNightRenderEnabled}
        renderTableHeaderMenu={(props) => (
          <WorkbookTableHeaderMenu {...props} />
        )}
        rounded={rounded}
        showNightRenderToggle={shouldRenderNightMode}
        workbookBuffer={workbookBuffer}
        workbookIdentity={workbookIdentity}
      />
    </div>
  );
}

function XlsxWorkbookLoadedViewer({
  fileName,
  isDark,
  onIsDarkChange,
  renderTableHeaderMenu,
  rounded,
  showNightRenderToggle,
  workbookBuffer,
  workbookIdentity,
}: {
  fileName: string;
  isDark: boolean;
  onIsDarkChange: (checked: boolean) => void;
  renderTableHeaderMenu: (
    props: XlsxTableHeaderMenuRenderProps
  ) => React.ReactNode;
  rounded: boolean;
  showNightRenderToggle: boolean;
  workbookBuffer: ArrayBuffer;
  workbookIdentity: string;
}) {
  const controller = useXlsxViewerController(
    React.useMemo(
      () => ({
        allowResizeInReadOnly: true,
        file: workbookBuffer,
        fileName,
        readOnly: true,
        useWorker: true,
      }),
      [fileName, workbookBuffer]
    )
  );

  return (
    <XlsxViewerProvider controller={controller} isDark={isDark}>
      <XlsxWorkbookSurface
        isDark={isDark}
        onIsDarkChange={onIsDarkChange}
        renderTableHeaderMenu={renderTableHeaderMenu}
        rounded={rounded}
        showNightRenderToggle={showNightRenderToggle}
        workbookIdentity={workbookIdentity}
      />
    </XlsxViewerProvider>
  );
}
