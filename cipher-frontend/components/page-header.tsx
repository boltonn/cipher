"use client";

import * as React from "react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

type PageHeaderState = {
  left: React.ReactNode;
  right: React.ReactNode;
  sidebarAccentClassName?: string;
} | null;

const PageHeaderStateContext = React.createContext<PageHeaderState>(null);
const PageHeaderSetterContext =
  React.createContext<React.Dispatch<React.SetStateAction<PageHeaderState>> | null>(null);

/**
 * Wraps the app shell. Holds the "current page's header content" as state so
 * `PageHeaderSlot` (rendered once, at a fixed spot in the shell) can display
 * whatever the active page's `PageHeader` last reported, instead of every
 * page rendering (and repositioning) its own copy of the sidebar trigger.
 */
export function PageHeaderProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<PageHeaderState>(null);

  return (
    <PageHeaderSetterContext value={setState}>
      <PageHeaderStateContext value={state}>{children}</PageHeaderStateContext>
    </PageHeaderSetterContext>
  );
}

/**
 * The single, real sidebar-trigger + header bar for the app. Rendered once
 * in the root layout so its position never moves between pages or with the
 * sidebar's expanded/collapsed width -- pages only ever feed it content via
 * `PageHeader`.
 */
export function PageHeaderSlot({ className }: { className?: string }) {
  const state = React.use(PageHeaderStateContext);

  return (
    <div
      className={cn(
        "sticky top-0 z-30 flex items-center justify-between px-6 pt-6 pb-2 bg-transparent",
        className
      )}
    >
      <div className="flex items-center gap-4">
        <SidebarTrigger
          className={cn(
            "h-9 w-9 text-slate-400",
            state?.sidebarAccentClassName ?? "hover:text-indigo-400"
          )}
        />
        {state?.left}
      </div>
      {state?.right && <div className="flex items-center gap-2">{state.right}</div>}
    </div>
  );
}

interface PageHeaderProps {
  /** Eyebrow label, e.g. "Images". Omit and use `children` for a fully custom left side instead. */
  eyebrow?: string;
  /** Value shown under the eyebrow, e.g. "738 Results". */
  value?: React.ReactNode;
  /** Optional icon shown next to `value`. */
  icon?: React.ReactNode;
  /** Color class for `value` text. Defaults to indigo, the app's standard accent. */
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
 * Reports this page's header content to the shared `PageHeaderSlot` -- it
 * renders nothing itself. Mount once per page, anywhere in its tree; unmount
 * (route change) clears the slot back to just the bare trigger.
 */
export function PageHeader({
  eyebrow,
  value,
  icon,
  accentClassName = "text-indigo-400/80",
  sidebarAccentClassName,
  extra,
  actions,
  children,
}: PageHeaderProps) {
  const setState = React.use(PageHeaderSetterContext);

  const left =
    children ?? (
      <>
        {eyebrow && (
          <div className="flex flex-col">
            <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">
              {eyebrow}
            </span>
            <div className="flex items-center gap-2">
              {icon}
              <span className={cn("text-xs font-mono", accentClassName)}>{value}</span>
            </div>
          </div>
        )}
        {extra}
      </>
    );

  React.useEffect(() => {
    setState?.({ left, right: actions, sidebarAccentClassName });
  });

  React.useEffect(() => {
    return () => setState?.(null);
  }, [setState]);

  return null;
}
