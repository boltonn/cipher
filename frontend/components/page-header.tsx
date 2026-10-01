"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { PAGE_CONTAINER } from "@/lib/layout";
import { cn } from "@/lib/utils";

type PageHeaderContextValue = {
  leftEl: HTMLElement | null;
  rightEl: HTMLElement | null;
  sidebarAccentClassName?: string;
  setLeftEl: (el: HTMLElement | null) => void;
  setRightEl: (el: HTMLElement | null) => void;
  setSidebarAccentClassName: (className: string | undefined) => void;
};

const PageHeaderContext = React.createContext<PageHeaderContextValue | null>(null);

/**
 * Wraps the app shell. Owns the two DOM containers inside `PageHeaderSlot`
 * that each page portals its header content into.
 *
 * Earlier this held the header content itself as React state and every page's
 * `PageHeader` pushed a fresh node tree into it from a dependency-less effect
 * on every render. On a page that re-renders often (React Query loading flips)
 * and puts a stateful Radix widget in `actions`, that re-mounted the widget on
 * every render and tripped React's "state update on a component that hasn't
 * mounted yet" warning. Portalling drops the state round-trip: the slot
 * renders once, pages render straight into it and update it in place.
 */
export function PageHeaderProvider({ children }: { children: React.ReactNode }) {
  const [leftEl, setLeftEl] = React.useState<HTMLElement | null>(null);
  const [rightEl, setRightEl] = React.useState<HTMLElement | null>(null);
  const [sidebarAccentClassName, setSidebarAccentClassName] = React.useState<
    string | undefined
  >(undefined);

  const value = React.useMemo<PageHeaderContextValue>(
    () => ({
      leftEl,
      rightEl,
      sidebarAccentClassName,
      setLeftEl,
      setRightEl,
      setSidebarAccentClassName,
    }),
    [leftEl, rightEl, sidebarAccentClassName]
  );

  return <PageHeaderContext value={value}>{children}</PageHeaderContext>;
}

/**
 * The single, real sidebar-trigger + header bar for the app. Rendered once
 * in the root layout so its position never moves between pages or with the
 * sidebar's expanded/collapsed width -- pages only ever feed it content via
 * `PageHeader`, which portals into the `left`/`right` containers here.
 */
export function PageHeaderSlot({ className }: { className?: string }) {
  const ctx = React.use(PageHeaderContext);

  return (
    <div
      className={cn(
        "sticky top-0 z-30 flex h-14 shrink-0 items-center bg-sidebar/85 backdrop-blur-xl border-b border-border",
        className
      )}
    >
      <div className={cn(PAGE_CONTAINER, "flex items-center justify-between gap-4")}>
        <div className="flex min-w-0 items-center gap-3">
          <SidebarTrigger
            className={cn(
              "h-8 w-8 shrink-0 text-muted-foreground",
              ctx?.sidebarAccentClassName ?? "hover:text-primary"
            )}
          />
          <div ref={ctx?.setLeftEl} className="flex min-w-0 items-center gap-3" />
        </div>
        <div ref={ctx?.setRightEl} className="flex shrink-0 items-center gap-2" />
      </div>
    </div>
  );
}

interface PageHeaderProps {
  /** Page title, e.g. "Images". Omit and use `children` for a fully custom left side instead. */
  eyebrow?: string;
  /** Value shown under the eyebrow, e.g. "738 Results". */
  value?: React.ReactNode;
  /** Optional icon shown next to `value`. */
  icon?: React.ReactNode;
  /** Color class for `value` text. Defaults to muted; pass `text-annotation` only on AI/ML surfaces. */
  accentClassName?: string;
  /** Hover color class for the shared SidebarTrigger while this page is active. Defaults to indigo. */
  sidebarAccentClassName?: string;
  /** Extra content appended after the eyebrow, inside the left cluster (e.g. a "clear similarity" pill). */
  extra?: React.ReactNode;
  /** Right-side content (mode toggles, buttons). */
  actions?: React.ReactNode;
  /** Fully custom left-side content (e.g. a breadcrumb), used in place of the baked-in eyebrow layout. */
  children?: React.ReactNode;
}

/**
 * Reports this page's header content to the shared `PageHeaderSlot` by
 * portalling into its containers -- it renders nothing in place. Mount once
 * per page, anywhere in its tree; unmount (route change) clears the slot back
 * to just the bare trigger.
 */
export function PageHeader({
  eyebrow,
  value,
  icon,
  accentClassName = "text-muted-foreground",
  sidebarAccentClassName,
  extra,
  actions,
  children,
}: PageHeaderProps) {
  const ctx = React.use(PageHeaderContext);

  const left =
    children ?? (
      <>
        {eyebrow && (
          <div className="flex min-w-0 flex-col leading-tight">
            <h1 className="truncate text-sm font-semibold text-foreground">{eyebrow}</h1>
            {value != null && (
              <div className="flex min-w-0 items-center gap-1.5 [&_svg]:size-3 [&_svg]:shrink-0 [&_svg]:text-muted-foreground">
                {icon}
                <span className={cn("truncate text-xs tabular-nums", accentClassName)}>{value}</span>
              </div>
            )}
          </div>
        )}
        {extra}
      </>
    );

  const setSidebarAccent = ctx?.setSidebarAccentClassName;
  React.useEffect(() => {
    setSidebarAccent?.(sidebarAccentClassName);
    return () => setSidebarAccent?.(undefined);
  }, [setSidebarAccent, sidebarAccentClassName]);

  if (!ctx) return null;

  return (
    <>
      {ctx.leftEl ? createPortal(left, ctx.leftEl) : null}
      {ctx.rightEl && actions ? createPortal(actions, ctx.rightEl) : null}
    </>
  );
}
