"use client";

import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { useMe } from "@/features/users/hooks/use-me";
import { NAV } from "@/lib/nav";
import { ShieldCheck } from "lucide-react";
import { usePathname } from "next/navigation";

/** Admin-only guard and header for every admin page (navigation lives in the sidebar). */
export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { data: me, isPending } = useMe();

  if (isPending) return <PageLoading icon={ShieldCheck} label="Loading…" />;
  if (!me?.isAdmin) {
    return (
      <div className="mx-auto max-w-md px-6 pt-24 text-center">
        <ShieldCheck className="mx-auto mb-3 h-8 w-8 text-admin" />
        <p className="text-sm text-muted-foreground">
          Only an admin can open this page.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20 pt-5">
      <PageHeader
        eyebrow="Admin"
        value={NAV.adminPages.find((page) => pathname.startsWith(page.url))?.title}
        icon={<ShieldCheck className="h-3.5 w-3.5 text-admin" />}
      />
      {children}
    </div>
  );
}
