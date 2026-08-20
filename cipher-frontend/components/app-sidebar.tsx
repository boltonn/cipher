"use client";

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
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { useMe } from "@/features/users/hooks/use-me";
import { getInitials } from "@/features/users/utils";
import { cn } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import {
  BookOpen,
  Database,
  HelpCircle,
  Home,
  Image as ImageIcon,
  MessageSquare,
  Search,
  Settings,
  Smile,
  User,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavigationItem {
  icon: IconComponent;
  title: string;
  url: string;
}

function isItemActive(pathname: string, itemUrl: string) {
  if (itemUrl === "/") return pathname === "/";
  return pathname.startsWith(itemUrl);
}

function MenuItem({
  item,
  pathname,
}: {
  item: NavigationItem;
  pathname: string;
}) {
  const isActive = isItemActive(pathname, item.url);
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        data-active={isActive}
        tooltip={item.title}
        className={cn(
          "relative h-12 overflow-hidden transition-all duration-300 ease-out",
          "group/button cursor-pointer my-0.5",
          "text-zinc-400 data-[active=true]:text-indigo-300 data-[active=true]:font-medium",
          !isActive && "hover:border-2 hover:border-indigo-500 hover:bg-indigo-600/10",
          isActive && !isCollapsed && "bg-transparent!",
          isActive && isCollapsed && "bg-indigo-500/15!",
          "group-data-[collapsible=icon]:size-12! group-data-[collapsible=icon]:p-0!"
        )}
      >
        <a
          href={item.url}
          className="flex items-center gap-3 px-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
        >
          <div
            className={`
            absolute left-0 top-0 h-full w-0.5 bg-indigo-500 shadow-[0_0_10px_rgba(99,102,241,0.8)]
            transition-all duration-300 group-data-[collapsible=icon]:hidden
            ${isActive ? "opacity-100 translate-x-0" : "opacity-0 -translate-x-full"}
          `}
          />
          <item.icon
            className={`
            h-6 w-6 shrink-0 transition-transform duration-300 ml-2 group-data-[collapsible=icon]:ml-0
            ${isActive ? "text-indigo-400 scale-110" : "group-hover/button:text-zinc-100"}
          `}
          />
          <span className="group-data-[collapsible=icon]:hidden">
            {item.title}
          </span>
        </a>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

const data = {
  main: [{ title: "Home", url: "/", icon: Home }],
  workspace: [
    { title: "Datasets", url: "/datasets", icon: Database },
    { title: "Search", url: "/search", icon: Search },
    { title: "Chat", url: "/chat", icon: MessageSquare },
    { title: "Documentation", url: "/docs", icon: BookOpen },
  ],
  media: [
    { title: "Images", url: "/images", icon: ImageIcon },
    // { title: "Documents", url: "/documents", icon: FileText },
    // { title: "Messages", url: "/messages", icon: MessagesSquare },
    // { title: "Contacts", url: "/contacts", icon: Users },
    // { title: "Calendar", url: "/calendar", icon: Calendar },
    // { title: "Locations", url: "/locations", icon: MapPin },
    // { title: "Video", url: "/video", icon: Video },
    // { title: "Email", url: "/email", icon: Mail },
    { title: "Faces", url: "/faces", icon: Smile },
    { title: "Persons", url: "/persons", icon: User },
  ],
  settings: [
    { title: "Settings", url: "/settings", icon: Settings },
    { title: "FAQ", url: "/faq", icon: HelpCircle },
  ],
};

export function AppSidebar() {
  const pathname = usePathname();
  const { data: user, isLoading } = useMe();

  return (
    <Sidebar className="border-r-0" collapsible="icon">
      {/* Header */}
      <SidebarHeader className="border-b border-slate-800 px-4 py-4 bg-sidebar/85 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Link
          href="/"
          className="flex items-center gap-3 group transition-opacity hover:opacity-80"
        >
          <div className="relative h-16 w-16 shrink-0">
            <Image
              src="/android-chrome-512x512.png"
              alt="Cipher.ai logo"
              fill
              className="object-contain"
              priority
              sizes="(max-width: 64px) 64px, 512px"
            />
          </div>
          <span
            className="
        text-lg
        font-semibold
        tracking-[0.18em]
        text-indigo-400
        relative
        -skew-x-6
        drop-shadow-[0_0_6px_rgba(99,102,241,0.45)]
        group-data-[collapsible=icon]:hidden
      "
          >
            CIPHER
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent className="gap-0 py-2 bg-sidebar/85 border-slate-800">
        {/* Group 1: Home (Isolated for emphasis) */}
        <SidebarGroup>
          <SidebarMenu>
            {data.main.map((item) => (
              <MenuItem key={item.title} item={item} pathname={pathname} />
            ))}
          </SidebarMenu>
        </SidebarGroup>

        {/* Group 2: Workspace */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-zinc-600">
            Workspace
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {data.workspace.map((item) => (
                <MenuItem key={item.title} item={item} pathname={pathname} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Group 3: Media & Assets */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-zinc-600">
            Viewers
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {data.media.map((item) => (
                <MenuItem key={item.title} item={item} pathname={pathname} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Group 4: Model (quick switcher, mirrors chat's model store) */}
        <SidebarGroup className="mt-auto">
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarModelSwitcher />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Group 5: Config */}
        <SidebarGroup>
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
      <SidebarFooter className="border-t border-slate-800 px-4 py-3 group-data-[collapsible=icon]:px-2">
        <div className="flex items-center gap-3 group-data-[collapsible=icon]:justify-center">
          {isLoading ? (
            <div className="h-8 w-8 rounded-full bg-slate-800 animate-pulse shrink-0" />
          ) : (
            <div className="h-8 w-8 rounded-full bg-linear-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-xs font-semibold text-white shadow-[0_0_10px_rgba(99,102,241,0.3)] shrink-0">
              {getInitials(user?.name)}
            </div>
          )}
          <div className="flex flex-col flex-1 min-w-0 group-data-[collapsible=icon]:hidden">
            {isLoading ? (
              <>
                <div className="h-3 w-20 bg-slate-800 animate-pulse rounded mb-1" />
                <div className="h-2 w-24 bg-slate-900 animate-pulse rounded" />
              </>
            ) : (
              <>
                <span className="text-sm font-medium text-slate-200 truncate">
                  {user?.name || "Unknown User"}
                </span>
                <span className="text-xs text-slate-500 truncate">
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
