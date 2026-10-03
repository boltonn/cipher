"use client";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { useIsAdmin } from "@/features/users/hooks/use-me";
import { NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { useState } from "react";

/** Admin-only sidebar entry: a rose launcher that pops out the admin sub-pages (`NAV.admin`). */
export function SidebarAdminLauncher({ pathname }: { pathname: string }) {
  const isAdmin = useIsAdmin();
  const [open, setOpen] = useState(false);
  if (!isAdmin) return null;

  const { icon: AdminIcon, title } = NAV.adminHome;
  const isActive = pathname.startsWith(NAV.adminHome.url);

  return (
    <SidebarMenuItem>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <SidebarMenuButton
            tooltip={title}
            data-active={isActive}
            className={cn(
              "h-9 cursor-pointer text-admin hover:bg-admin/10 hover:text-admin",
              "data-[active=true]:bg-admin/15 data-[active=true]:font-medium",
              "group-data-[collapsible=icon]:size-9! group-data-[collapsible=icon]:p-0!"
            )}
          >
            <span className="flex items-center gap-2.5 px-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
              <AdminIcon className="ml-1.5 h-4.5 w-4.5 shrink-0 group-data-[collapsible=icon]:ml-0" />
              <span className="text-sm group-data-[collapsible=icon]:hidden">
                {title}
              </span>
            </span>
          </SidebarMenuButton>
        </PopoverTrigger>
        <PopoverContent side="right" align="end" className="w-64 gap-1 p-1.5">
          <p className="px-2 pt-1 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-admin">
            Admin
          </p>
          {NAV.admin.map((item) => (
            <Link
              key={item.url}
              href={item.url}
              onClick={() => setOpen(false)}
              className={cn(
                "flex items-start gap-2.5 rounded-md px-2 py-2 hover:bg-admin/10",
                pathname.startsWith(item.url) && "bg-admin/10"
              )}
            >
              <item.icon className="mt-0.5 h-4 w-4 shrink-0 text-admin" />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">
                  {item.title}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {item.blurb}
                </span>
              </span>
            </Link>
          ))}
        </PopoverContent>
      </Popover>
    </SidebarMenuItem>
  );
}
