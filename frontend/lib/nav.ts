import type { IconComponent } from "@/types/common";
import {
  BookOpen,
  Building2,
  CalendarDays,
  Database,
  FileText,
  HelpCircle,
  Home,
  Image as ImageIcon,
  MapPin,
  MessageSquare,
  Search,
  Settings,
  Share2,
  ShieldCheck,
  Smile,
  Tags,
  User,
  Users,
  Waypoints,
} from "lucide-react";

export interface NavItem {
  title: string;
  url: string;
  icon: IconComponent;
  /** One-line description, used by the Home launcher tiles. */
  blurb: string;
  /** Sub-pages shown nested (and expandable) under this item in the sidebar. */
  children?: NavItem[];
}

/**
 * The one navigation map for the app. The sidebar, the Home launcher and quick
 * search all read from this, so a group can never drift between surfaces.
 *
 * Grouping rule (review is built into every page, so it has no group of its own):
 *  - `find`       — ways to ask: Search (one box; its children are the per-type
 *                   searches it hands off to) and Chat.
 *  - `knowledge`  — the record types built from the data: people, organizations,
 *                   places, events.
 *  - `manage`     — what you own and keep: datasets.
 *  - `graph`      — no sidebar entry; opened from Entities, an entity, or quick search.
 *  - `admin`      — admin-only pages (`adminPages`), nested under the sidebar's Admin entry.
 */
export const NAV = {
  home: {
    title: "Home",
    url: "/",
    icon: Home,
    blurb: "Where you left off — recent datasets and running enrichment.",
  } as NavItem,

  find: [
    {
      title: "Search",
      url: "/search",
      icon: Search,
      blurb: "One box for everything — or start from an overview of what's in a dataset.",
      children: [
        {
          title: "Emails & documents",
          url: "/search/text",
          icon: FileText,
          blurb: "Keyword, semantic, and hybrid search over every email and document.",
        },
        {
          title: "Images",
          url: "/images",
          icon: ImageIcon,
          blurb: "Browse and search images by content or visual similarity.",
        },
        {
          title: "Faces",
          url: "/faces",
          icon: Smile,
          blurb: "Detected faces awaiting review or matched to a person.",
        },
        {
          title: "Entities",
          url: "/entities",
          icon: Waypoints,
          blurb: "People, organizations, selectors — find, resolve and verify them; open any in the graph.",
        },
      ],
    },
    {
      title: "Chat",
      url: "/chat",
      icon: MessageSquare,
      blurb: "Ask questions over a dataset and get answers cited back to source.",
    },
  ] as NavItem[],

  knowledge: [
    {
      title: "Persons",
      url: "/persons",
      icon: User,
      blurb: "Identities clustered from faces and selectors across a dataset.",
    },
    {
      title: "Organizations",
      url: "/organizations",
      icon: Building2,
      blurb: "Org charts — click a unit to see who works there or is connected to it.",
    },
    {
      title: "Locations",
      url: "/locations",
      icon: MapPin,
      blurb: "Every geolocated record on one map, filtered by dataset and date.",
    },
    {
      title: "Events",
      url: "/events",
      icon: CalendarDays,
      blurb: "Travel, meetings, and gatherings on a calendar, pulled from files.",
    },
  ] as NavItem[],

  manage: [
    {
      title: "Datasets",
      url: "/datasets",
      icon: Database,
      blurb: "Create and manage the raw ingests everything else is triaged from.",
    },
  ] as NavItem[],

  graph: {
    title: "Graph",
    url: "/graph",
    icon: Share2,
    blurb: "Entities as a network — seed it, expand outward, follow links.",
  } as NavItem,

  admin: {
    title: "Admin",
    url: "/admin",
    icon: ShieldCheck,
    blurb: "Admin-only management.",
  } as NavItem,

  adminPages: [
    {
      title: "Users",
      url: "/admin/users",
      icon: Users,
      blurb: "Who can sign in, who is an admin, and which datasets each user can access.",
    },
    {
      title: "Database",
      url: "/admin/database",
      icon: Database,
      blurb: "Postgres size by table and by dataset.",
    },
    {
      title: "Tag training",
      url: "/admin/tag-training",
      icon: Tags,
      blurb: "Analyst labels per image tag, and which tags are ready to train a classifier.",
    },
  ] as NavItem[],

  help: [
    {
      title: "Settings",
      url: "/settings",
      icon: Settings,
      blurb: "Default model, API keys, and browsing preferences.",
    },
    {
      title: "Documentation",
      url: "/docs",
      icon: BookOpen,
      blurb: "How a file becomes a record — pipeline, schemas, and services.",
    },
    {
      title: "FAQ",
      url: "/faq",
      icon: HelpCircle,
      blurb: "Short answers to the questions that come up most.",
    },
  ] as NavItem[],
} as const;
