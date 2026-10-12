"use client";

import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { StatusPage } from "@/components/status-page";
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
    return <StatusPage kind="forbidden" body="Only an admin can open this page." />;
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
