"use client";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  /** Eyebrow label, e.g. "Images". Omit and use `children` for a fully custom layout instead. */
  eyebrow?: string;
  /** Value shown under the eyebrow, e.g. "738 Results". */
  value?: React.ReactNode;
  /** Optional icon shown next to `value`. */
  icon?: React.ReactNode;
  /** Color class for `value` text. Defaults to indigo, the app's standard accent. */
  accentClassName?: string;
  /** Hover color class for the built-in SidebarTrigger. Defaults to indigo. */
  sidebarAccentClassName?: string;
  /** Extra content appended after the eyebrow, inside the left cluster (e.g. a "clear similarity" pill). */
  extra?: React.ReactNode;
  /** Right-side content (mode toggles, buttons). */
  actions?: React.ReactNode;
  /** Fully custom content, used in place of the baked-in SidebarTrigger + eyebrow layout. */
  children?: React.ReactNode;
  className?: string;
}

/**
 * Shared sticky top bar for every top-level page (Images, Faces, Persons,
 * Datasets, and their detail pages). Bakes in the SidebarTrigger + eyebrow
 * assembly that was previously hand-duplicated per page -- most pages only
 * need to pass `eyebrow`/`value`/`actions`. Pages with a genuinely different
 * layout (e.g. a clickable breadcrumb instead of a plain label) can skip the
 * props entirely and pass fully custom `children` instead.
 *
 * Background is intentionally `bg-transparent`: an earlier version tinted
 * this with `bg-background/90`, which reads as a solid dark bar wherever the
 * page's ambient glow isn't directly behind it (i.e. most of the header's
 * width) -- flat transparency is what actually blends with the page.
 */
export function PageHeader({
  eyebrow,
  value,
  icon,
  accentClassName = "text-indigo-400/80",
  sidebarAccentClassName = "hover:text-indigo-400",
  extra,
  actions,
  children,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "sticky top-0 z-30 flex items-center justify-between pt-6 pb-2 bg-transparent",
        className
      )}
    >
      {children ?? (
        <>
          <div className="flex items-center gap-4">
            <SidebarTrigger className={cn("h-9 w-9 text-slate-400", sidebarAccentClassName)} />
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
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </>
      )}
    </div>
  );
}
