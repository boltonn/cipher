"use client";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

/** Admin entry in the rose `admin` color, expanding into the admin pages. The sidebar renders it only for admins. */
export function SidebarAdminLauncher({ pathname }: { pathname: string }) {
  const router = useRouter();
  const { state } = useSidebar();
  const { icon: AdminIcon, title, url } = NAV.admin;
  const isActive = pathname.startsWith(url);

  return (
    <Collapsible asChild defaultOpen={isActive} className="group/admin">
      <SidebarMenuItem>
        <CollapsibleTrigger asChild>
          <SidebarMenuButton
            tooltip={title}
            data-active={isActive}
            // Collapsed to icons there's no room for the sub-pages, so go straight to the first one.
            onClick={() => state === "collapsed" && router.push(url)}
            className={cn(
              "h-9 cursor-pointer text-admin hover:bg-admin/10 hover:text-admin",
              "data-[active=true]:font-medium data-[active=true]:text-admin",
              "group-data-[collapsible=icon]:size-9! group-data-[collapsible=icon]:p-0!"
            )}
          >
            <span className="flex w-full items-center gap-2.5 group-data-[collapsible=icon]:justify-center">
              <AdminIcon className="ml-1.5 h-4.5 w-4.5 shrink-0 group-data-[collapsible=icon]:ml-0" />
              <span className="text-sm group-data-[collapsible=icon]:hidden">{title}</span>
              <ChevronRight className="ml-auto h-3.5 w-3.5 transition-transform group-data-[state=open]/admin:rotate-90 group-data-[collapsible=icon]:hidden" />
            </span>
          </SidebarMenuButton>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <SidebarMenuSub className="border-admin/25">
            {NAV.adminPages.map((page) => (
              <SidebarMenuSubItem key={page.url}>
                <SidebarMenuSubButton
                  asChild
                  isActive={pathname.startsWith(page.url)}
                  className="text-muted-foreground hover:bg-admin/10 hover:text-admin data-[active=true]:bg-admin/15 data-[active=true]:text-admin [&>svg]:text-current"
                >
                  <Link href={page.url}>
                    <page.icon />
                    <span>{page.title}</span>
                  </Link>
                </SidebarMenuSubButton>
              </SidebarMenuSubItem>
            ))}
          </SidebarMenuSub>
        </CollapsibleContent>
      </SidebarMenuItem>
    </Collapsible>
  );
}
