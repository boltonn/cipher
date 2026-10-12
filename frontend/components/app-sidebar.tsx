"use client";

import { SidebarAdminLauncher } from "@/components/sidebar-admin-launcher";
import { SidebarModelSwitcher } from "@/components/sidebar-model-switcher";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar";
import { useIsAdmin, useMe } from "@/features/users/hooks/use-me";
import { getInitials } from "@/features/users/utils";
import { NAV, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useState } from "react";

type NavigationItem = NavItem;

function isItemActive(pathname: string, itemUrl: string) {
  if (itemUrl === "/") return pathname === "/";
  return pathname === itemUrl || pathname.startsWith(`${itemUrl}/`);
}

/** Active on its own page, but not while one of its children is the page you're on. */
function isParentActive(pathname: string, item: NavigationItem) {
  const onChild = item.children?.some((child) => isItemActive(pathname, child.url));
  return !onChild && isItemActive(pathname, item.url);
}

function MenuItem({
  item,
  pathname,
}: {
  item: NavigationItem;
  pathname: string;
}) {
  const isActive = isParentActive(pathname, item);
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";
  const hasChildren = !!item.children?.length;
  const [open, setOpen] = useState(hasChildren);

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        data-active={isActive}
        tooltip={item.title}
        className={cn(
          "relative h-9 overflow-hidden transition-colors duration-200 ease-out",
          "group/button cursor-pointer",
          "text-muted-foreground data-[active=true]:text-primary data-[active=true]:font-medium",
          !isActive && "hover:bg-primary/10 hover:text-foreground",
          isActive && !isCollapsed && "bg-transparent!",
          isActive && isCollapsed && "bg-primary/15!",
          "group-data-[collapsible=icon]:size-9! group-data-[collapsible=icon]:p-0!"
        )}
      >
        <a
          href={item.url}
          className="flex items-center gap-2.5 px-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
        >
          <div
            className={cn(
              "absolute left-0 top-0 h-full w-0.5 bg-primary",
              "transition-opacity duration-200 group-data-[collapsible=icon]:hidden",
              isActive ? "opacity-100" : "opacity-0"
            )}
          />
          <item.icon
            className={cn(
              "h-4.5 w-4.5 shrink-0 ml-1.5 group-data-[collapsible=icon]:ml-0",
              isActive ? "text-primary" : "group-hover/button:text-foreground"
            )}
          />
          <span className="text-sm group-data-[collapsible=icon]:hidden">
            {item.title}
          </span>
        </a>
      </SidebarMenuButton>
      {hasChildren && (
        <>
          <SidebarMenuAction
            onClick={() => setOpen((value) => !value)}
            aria-label={open ? `Collapse ${item.title}` : `Expand ${item.title}`}
            aria-expanded={open}
            className="top-2"
          >
            <ChevronRight className={cn("transition-transform", open && "rotate-90")} />
          </SidebarMenuAction>
          {open && (
            <SidebarMenuSub>
              {item.children?.map((child) => {
                const childActive = isItemActive(pathname, child.url);
                return (
                  <SidebarMenuSubItem key={child.url}>
                    <SidebarMenuSubButton
                      href={child.url}
                      isActive={childActive}
                      className={cn(
                        "text-muted-foreground hover:text-foreground",
                        childActive && "font-medium text-primary!"
                      )}
                    >
                      <child.icon className={cn(childActive ? "text-primary!" : "text-muted-foreground!")} />
                      <span>{child.title}</span>
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                );
              })}
            </SidebarMenuSub>
          )}
        </>
      )}
    </SidebarMenuItem>
  );
}

const data = {
  main: [NAV.home],
  groups: [
    { label: "Find", items: NAV.find },
    { label: "Knowledge", items: NAV.knowledge },
    { label: "Manage", items: NAV.manage },
  ],
  settings: NAV.help,
};

const separatorClassName =
  "my-1.5 h-px w-2/3 mx-auto bg-transparent bg-gradient-to-r from-transparent via-primary/25 to-transparent group-data-[collapsible=icon]:w-8";

export function AppSidebar() {
  const pathname = usePathname();
  const { data: user, isLoading } = useMe();
  const isAdmin = useIsAdmin();

  return (
    <Sidebar className="border-r-0" collapsible="icon">
      {/* Header */}
      <SidebarHeader className="h-14 justify-center border-b border-border px-3 bg-sidebar/85 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Link
          href="/"
          className="flex items-center gap-2.5 group transition-opacity hover:opacity-80"
        >
          <div className="relative h-8 w-8 shrink-0">
            <Image
              src="/android-chrome-512x512.png"
              alt="Cipher.ai logo"
              fill
              className="object-contain"
              priority
              sizes="32px"
            />
          </div>
          <span
            className="
        text-base
        font-semibold
        tracking-wide
        text-primary
        relative
        -skew-x-6
        group-data-[collapsible=icon]:hidden
      "
          >
            CIPHER
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent className="gap-0 py-2 bg-sidebar/85 border-border">
        {/* Group 1: Home (Isolated for emphasis) */}
        <SidebarGroup>
          <SidebarMenu>
            {data.main.map((item) => (
              <MenuItem key={item.title} item={item} pathname={pathname} />
            ))}
          </SidebarMenu>
        </SidebarGroup>

        {data.groups.map((group) => (
          <Fragment key={group.label}>
            <SidebarSeparator className={separatorClassName} />
            <SidebarGroup>
              <SidebarGroupLabel className="text-muted-foreground">{group.label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {group.items.map((item) => (
                    <MenuItem key={item.title} item={item} pathname={pathname} />
                  ))}
                  {group.label === "Manage" && isAdmin && <SidebarAdminLauncher pathname={pathname} />}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </Fragment>
        ))}

        {/* Model (quick switcher, mirrors chat's model store) */}
        <SidebarGroup className="mt-auto">
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarModelSwitcher />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator className={separatorClassName} />

        {/* Config & Help */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-muted-foreground">Help</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {data.settings.map((item) => (
                <MenuItem key={item.title} item={item} pathname={pathname} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* Footer */}
      <SidebarFooter className="border-t border-border px-4 py-3 group-data-[collapsible=icon]:px-2">
        <div className="flex items-center gap-3 group-data-[collapsible=icon]:justify-center">
          {isLoading ? (
            <div className="h-8 w-8 rounded-full bg-muted animate-pulse shrink-0" />
          ) : (
            <div className="h-8 w-8 rounded-full bg-linear-to-br from-primary to-purple-600 flex items-center justify-center text-xs font-semibold text-white shrink-0">
              {getInitials(user?.name)}
            </div>
          )}
          <div className="flex flex-col flex-1 min-w-0 group-data-[collapsible=icon]:hidden">
            {isLoading ? (
              <>
                <div className="h-3 w-20 bg-muted animate-pulse rounded mb-1" />
                <div className="h-2 w-24 bg-muted animate-pulse rounded" />
              </>
            ) : (
              <>
                <span className="text-sm font-medium text-foreground truncate">
                  {user?.name || "Unknown User"}
                </span>
                <span className="text-xs text-muted-foreground truncate">
                  {user?.email || "No email linked"}
                </span>
              </>
            )}
          </div>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
