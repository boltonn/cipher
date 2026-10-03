import type { IconComponent } from "@/types/common";
import {
  BookOpen,
  Building2,
  CalendarDays,
  Database,
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
}

/**
 * The one navigation map for the app. The sidebar and the Home launcher both
 * read from this, so a group can never drift between the two surfaces.
 *
 * Grouping rule:
 *  - `workspace`  — corpus-level operations you *run* (ingest, search, ask).
 *  - `explore`    — the knowledge graph and its derived layers, as analytical
 *                   surfaces you read and annotate.
 *  - `media`      — raw visual assets you browse directly.
 *  - `admin`      — admin-only pages (`adminPages`), nested under the
 *                   sidebar's Admin entry (rendered only for admins).
 */
export const NAV = {
  home: {
    title: "Home",
    url: "/",
    icon: Home,
    blurb: "Where you left off — recent datasets and running enrichment.",
  } as NavItem,

  workspace: [
    {
      title: "Datasets",
      url: "/datasets",
      icon: Database,
      blurb: "Create and manage the raw ingests everything else is triaged from.",
    },
    {
      title: "Search",
      url: "/search",
      icon: Search,
      blurb: "Text, semantic, and hybrid search across every indexed record.",
    },
    {
      title: "Chat",
      url: "/chat",
      icon: MessageSquare,
      blurb: "Ask questions over a dataset and get answers cited back to source.",
    },
  ] as NavItem[],

  explore: [
    {
      title: "Entities",
      url: "/entities",
      icon: Waypoints,
      blurb: "People, organizations, selectors — resolve, review, and manage them.",
    },
    {
      title: "Graph",
      url: "/graph",
      icon: Share2,
      blurb: "The same entities as a network — seed it, expand outward, follow links.",
    },
    {
      title: "Organizations",
      url: "/organizations",
      icon: Building2,
      blurb: "Org charts — click a unit to see who works there or is connected to it.",
    },
    {
      title: "Persons",
      url: "/persons",
      icon: User,
      blurb: "Identities clustered from faces and selectors across a dataset.",
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

  media: [
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
  ] as NavItem[],

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
