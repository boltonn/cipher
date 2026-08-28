import { PageHeaderSlot } from "@/components/page-header";

/**
 * Applies to every route except /chat (outside this group) -- see
 * `app/layout.tsx` for why chat opts out of the shared title bar.
 *
 * `SidebarInset` is a fixed-height, non-scrolling `h-screen` shell now (see
 * `app/layout.tsx`), so this owns the actual page-level scroll: the slot
 * takes its natural height, and this wrapper gets whatever's left. A page
 * that renders its own `h-screen` (like most normal content pages did
 * before the shared slot existed) would double-count that height against
 * this wrapper's remaining space and get clipped -- pages need `h-full`,
 * not `h-screen`, to fill exactly what this hands them. A page managing its
 * own fixed split-scroll layout (e.g. search) never grows past that `h-full`
 * box, so this wrapper's own scroll never activates for it.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeaderSlot />
      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden [scrollbar-gutter:stable]">{children}</div>
    </>
  );
}
