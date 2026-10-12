"use client";

import { Button } from "@/components/ui/button";
import type { ApiErrorCode } from "@/lib/api-errors";
import { NAV, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import { ArrowLeft, ArrowRight, CloudOff, FileQuestion, House, LogIn, RotateCw, ShieldX, TriangleAlert } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

export type StatusKind = "notFound" | "forbidden" | "unauthorized" | "serverError" | "network";

const STATUS: Record<StatusKind, { label: string; badge: string; icon: IconComponent; title: string; body: string; tone: string }> = {
  notFound: {
    label: "404",
    badge: "Page not found",
    icon: FileQuestion,
    title: "We couldn’t find that",
    body: "This page or the item it points to doesn’t exist. It may have been deleted, or the link is out of date.",
    tone: "border-border bg-muted/60 text-muted-foreground",
  },
  forbidden: {
    label: "403",
    badge: "No access",
    icon: ShieldX,
    title: "You don’t have access",
    body: "This belongs to a dataset you’re not a member of. Ask an admin to add you if you need it.",
    tone: "border-destructive/30 bg-destructive/10 text-destructive",
  },
  unauthorized: {
    label: "401",
    badge: "Signed out",
    icon: LogIn,
    title: "You’re signed out",
    body: "Your session has expired or you’re not signed in. Sign in again to keep going.",
    tone: "border-primary/30 bg-primary/10 text-primary",
  },
  serverError: {
    label: "500",
    badge: "Server error",
    icon: TriangleAlert,
    title: "This screen ran into a problem",
    body: "Something failed while loading this page. It’s usually temporary, so try again.",
    tone: "border-destructive/30 bg-destructive/10 text-destructive",
  },
  network: {
    label: "Offline",
    badge: "Connection lost",
    icon: CloudOff,
    title: "Can’t reach the server",
    body: "The API isn’t responding. Check that it’s running and your connection is up, then try again.",
    tone: "border-border bg-muted/60 text-muted-foreground",
  },
};

const SUGGESTED_PAGES: NavItem[] = [NAV.home, ...NAV.find, ...NAV.manage, ...NAV.knowledge].slice(0, 4);

const fadeUp = (delay: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.35, ease: "easeOut" as const, delay },
});

/** The status page to show for an API error code. */
export function statusKindFor(code: ApiErrorCode | undefined): StatusKind {
  if (code === "notFound" || code === "forbidden" || code === "unauthorized" || code === "network") return code;
  return "serverError";
}

interface StatusPageProps {
  kind: StatusKind;
  /** Replaces the default sentence, e.g. naming what wasn't found. */
  body?: string;
  /** Retry in place (error boundaries pass `reset`); otherwise "Try again" reloads. */
  onRetry?: () => void;
  className?: string;
}

/** Full-page status for not found / no access / signed out / server errors, in the app's shell. */
export function StatusPage({ kind, body, onRetry, className }: StatusPageProps) {
  const status = STATUS[kind];
  const Icon = status.icon;
  const retry = onRetry ?? (() => window.location.reload());

  return (
    <div className={cn("relative isolate flex h-full min-h-[60vh] flex-col items-center justify-center overflow-y-auto px-4 py-12 text-center", className)}>
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-[linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] bg-size-[44px_44px] opacity-60 mask-[radial-gradient(ellipse_55%_50%_at_50%_45%,black,transparent)]"
      />

      <motion.p
        {...fadeUp(0)}
        aria-hidden
        className="bg-linear-to-b from-foreground/70 to-foreground/0 bg-clip-text font-mono text-[clamp(5.5rem,16vw,10rem)] leading-none font-semibold tracking-tighter text-transparent select-none"
      >
        {status.label}
      </motion.p>

      <motion.div {...fadeUp(0.05)} className={cn("-mt-3 inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium backdrop-blur", status.tone)}>
        <Icon className="size-3.5" />
        {status.badge}
      </motion.div>

      <motion.div {...fadeUp(0.1)} className="mt-6 max-w-md">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{status.title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{body ?? status.body}</p>
      </motion.div>

      <motion.div {...fadeUp(0.15)} className="mt-8 flex flex-wrap items-center justify-center gap-2">
        {kind === "unauthorized" ? (
          <Button className="gap-1.5" onClick={() => window.location.reload()}>
            <LogIn className="size-4" />
            Sign in again
          </Button>
        ) : kind === "serverError" || kind === "network" ? (
          <Button className="gap-1.5" onClick={retry}>
            <RotateCw className="size-4" />
            Try again
          </Button>
        ) : (
          <Button asChild className="gap-1.5">
            <Link href="/">
              <House className="size-4" />
              Go home
            </Link>
          </Button>
        )}
        <Button variant="outline" className="gap-1.5" onClick={() => window.history.back()}>
          <ArrowLeft className="size-4" />
          Go back
        </Button>
      </motion.div>

      {kind === "notFound" && (
        <motion.div {...fadeUp(0.2)} className="mt-12 w-full max-w-xl">
          <p className="mb-3 text-xs font-medium text-muted-foreground">Or head to one of these</p>
          <div className="grid gap-2 text-left sm:grid-cols-2">
            {SUGGESTED_PAGES.map(({ title, url, icon: PageIcon, blurb }) => (
              <Link
                key={url}
                href={url}
                className="group flex items-start gap-3 rounded-xl border border-border/60 bg-card/60 p-3 backdrop-blur transition-colors hover:border-primary/40 hover:bg-primary/5"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <PageIcon className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1 text-sm font-medium text-foreground">
                    {title}
                    <ArrowRight className="size-3.5 -translate-x-1 opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
                  </span>
                  <span className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{blurb}</span>
                </span>
              </Link>
            ))}
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Or press{" "}
            <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">⌘K</kbd>{" "}
            to search everything.
          </p>
        </motion.div>
      )}
    </div>
  );
}
