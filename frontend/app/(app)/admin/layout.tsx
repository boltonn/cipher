"use client";

import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { useMe } from "@/features/users/hooks/use-me";
import { NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

/** Shell for every admin sub-page: the admin header, a tab per `NAV.admin` entry, and an admin-only guard. */
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

  const current = NAV.admin.find((item) => pathname.startsWith(item.url));
  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20 pt-5">
      <PageHeader
        eyebrow="Admin"
        value={current?.title}
        icon={<ShieldCheck className="h-3.5 w-3.5 text-admin" />}
      />
      <nav className="mb-6 flex gap-1 border-b border-border">
        {NAV.admin.map((item) => (
          <Link
            key={item.url}
            href={item.url}
            className={cn(
              "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground",
              item === current
                ? "border-admin text-foreground"
                : "border-transparent"
            )}
          >
            <item.icon className="h-3.5 w-3.5" />
            {item.title}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
