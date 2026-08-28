"use client";

import { PageHeader } from "@/components/page-header";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import { useReducedMotion } from "motion/react";
import {
  BookOpen,
  ChevronRight,
  Database,
  Home,
  Image as ImageIcon,
  Mail,
  MessageSquare,
  Search,
  Smile,
  User,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL;
const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL;

const DECODE_LINE = "files · mail · images · messages -> typed & searchable";
const DECODE_GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&*+=<>/\\|~^";

/**
 * A short, one-time decode: the line resolves left-to-right from noise into
 * the real string, unresolved characters shown in the app's existing
 * AI/ML-annotation color. Literalizes what Cipher does (unknown -> typed)
 * with the same color the rest of the app already uses for "model output,
 * not yet confirmed" -- not a decorative effect.
 */
const DECODE_TOTAL_FRAMES = 18;

function scrambleFrame(text: string, revealed: number) {
  return text
    .split("")
    .map((ch, i) => {
      if (ch === " " || i < revealed) return ch;
      return DECODE_GLYPHS[Math.floor(Math.random() * DECODE_GLYPHS.length)];
    })
    .join("");
}

function DecodeLine({ text }: { text: string }) {
  const prefersReducedMotion = useReducedMotion();
  const [display, setDisplay] = useState(text);
  const [done, setDone] = useState(false);
  const settled = Boolean(prefersReducedMotion) || done;

  useEffect(() => {
    if (prefersReducedMotion) return;
    let frame = 0;
    const id = setInterval(() => {
      frame += 1;
      setDisplay(scrambleFrame(text, Math.floor((frame / DECODE_TOTAL_FRAMES) * text.length)));
      if (frame >= DECODE_TOTAL_FRAMES) {
        clearInterval(id);
        setDone(true);
      }
    }, 40);
    return () => clearInterval(id);
  }, [text, prefersReducedMotion]);

  return (
    <p
      className={cn(
        "font-mono text-xs tracking-tight transition-colors duration-300",
        settled ? "text-muted-foreground" : "text-annotation"
      )}
    >
      {settled ? text : display}
    </p>
  );
}

interface NavTile {
  title: string;
  description: string;
  url: string;
  icon: IconComponent;
}

const WORKSPACE: NavTile[] = [
  {
    title: "Datasets",
    description: "Create and manage the raw ingests everything else is triaged from.",
    url: "/datasets",
    icon: Database,
  },
  {
    title: "Search",
    description: "Text, semantic, and hybrid search across every indexed record.",
    url: "/search",
    icon: Search,
  },
  {
    title: "Chat",
    description: "Ask questions over a dataset and get answers cited back to source.",
    url: "/chat",
    icon: MessageSquare,
  },
  {
    title: "Documentation",
    description: "How a file becomes a record -- pipeline, schemas, and services.",
    url: "/docs",
    icon: BookOpen,
  },
];

const VIEWERS: NavTile[] = [
  {
    title: "Images",
    description: "Browse and search images by content or visual similarity.",
    url: "/images",
    icon: ImageIcon,
  },
  {
    title: "Faces",
    description: "Detected faces awaiting review or matched to a person.",
    url: "/faces",
    icon: Smile,
  },
  {
    title: "Persons",
    description: "Identities clustered from faces across a dataset.",
    url: "/persons",
    icon: User,
  },
];

function NavCard({ tile }: { tile: NavTile }) {
  return (
    <Link
      href={tile.url}
      className={cn(
        "group relative flex items-start gap-3 overflow-hidden rounded-lg border border-border bg-white/[0.02] p-4 pl-5",
        "transition-colors hover:border-primary/40 hover:bg-primary/5"
      )}
    >
      {/* Echoes the active-item indicator in the sidebar, so a home tile
          reads as the same destination the sidebar links to, just larger. */}
      <div
        className="absolute left-0 top-0 h-full w-0.5 origin-top scale-y-0 bg-primary shadow-[0_0_10px_rgba(99,102,241,0.8)] transition-transform duration-300 group-hover:scale-y-100"
      />
      <tile.icon className="mt-0.5 h-4.5 w-4.5 shrink-0 text-primary" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-semibold text-foreground">{tile.title}</span>
          <ChevronRight
            size={13}
            className="text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
          />
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{tile.description}</p>
      </div>
    </Link>
  );
}

function NavSection({ label, tiles }: { label: string; tiles: NavTile[] }) {
  return (
    <section>
      <span className="text-[10px] font-black text-muted-foreground uppercase tracking-[0.2em]">
        {label}
      </span>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {tiles.map((tile) => (
          <NavCard key={tile.title} tile={tile} />
        ))}
      </div>
    </section>
  );
}

function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.373 0 12c0 5.303 3.438 9.8 8.205 11.387.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.385-1.333-1.755-1.333-1.755-1.09-.744.083-.729.083-.729 1.205.084 1.84 1.237 1.84 1.237 1.07 1.834 2.807 1.304 3.492.997.108-.775.42-1.305.763-1.605-2.665-.303-5.466-1.332-5.466-5.93 0-1.31.468-2.38 1.235-3.22-.123-.303-.535-1.523.117-3.176 0 0 1.008-.322 3.301 1.23a11.5 11.5 0 013.003-.404c1.02.005 2.047.138 3.006.404 2.29-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.873.118 3.176.77.84 1.233 1.91 1.233 3.22 0 4.61-2.807 5.624-5.48 5.92.43.372.823 1.102.823 2.222 0 1.604-.014 2.896-.014 3.286 0 .32.216.694.825.576C20.565 21.796 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  );
}

export default function Page() {
  return (
    <div className="max-w-4xl mx-auto px-6 relative pb-20">
      <PageHeader eyebrow="Home" value="Cipher" icon={<Home className="h-3.5 w-3.5 text-primary/80" />} />

      <div className="pt-4 pb-10">
        <DecodeLine text={DECODE_LINE} />
        <h1
          className={cn(
            "mt-3 max-w-xl text-4xl font-bold tracking-tight text-foreground sm:text-5xl",
            "animate-in fade-in-0 slide-in-from-bottom-2 duration-700 motion-reduce:animate-none"
          )}
        >
          Turn unknown data into something you can search.
        </h1>
        <p
          className={cn(
            "mt-3 max-w-xl text-base text-muted-foreground",
            "animate-in fade-in-0 slide-in-from-bottom-2 duration-700 delay-150 motion-reduce:animate-none"
          )}
        >
          Point Cipher at whatever you&apos;ve got -- files, mail, images, message exports -- and it
          types, enriches, and indexes it automatically. Pick up where you left off, or jump into a
          section below.
        </p>
      </div>

      <div
        className={cn(
          "flex flex-col gap-8",
          "animate-in fade-in-0 slide-in-from-bottom-1 duration-700 delay-300 motion-reduce:animate-none"
        )}
      >
        <NavSection label="Workspace" tiles={WORKSPACE} />
        <NavSection label="Viewers" tiles={VIEWERS} />
      </div>

      {(REPO_URL || CONTACT_EMAIL) && (
        <>
          <Separator className="mt-12 mb-5 bg-white/10" />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <span className="text-[10px] font-black text-muted-foreground uppercase tracking-[0.2em]">
                Get in touch
              </span>
              <p className="mt-1 text-sm text-muted-foreground">
                Questions, feedback, or want a walkthrough? Reach out.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {REPO_URL && (
                <a
                  href={REPO_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/50 hover:bg-primary/10 hover:text-primary"
                >
                  <GithubMark className="h-3.5 w-3.5" />
                  Source
                </a>
              )}
              {CONTACT_EMAIL && (
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/50 hover:bg-primary/10 hover:text-primary"
                >
                  <Mail size={13} />
                  {CONTACT_EMAIL}
                </a>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
