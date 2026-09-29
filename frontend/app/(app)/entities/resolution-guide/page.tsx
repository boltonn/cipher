"use client";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import {
  Carousel,
  type CarouselApi,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "@/components/ui/carousel";
import { RESOLUTION_FEATURE_META } from "@/features/entities/lib/resolution-features";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  FileText,
  Mail,
  Sparkles,
  User,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

/* --- little mock primitives, styled like the real Resolve/Review UI --------- */

function NameChip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded bg-annotation/15 px-1 font-mono text-[11px] text-foreground">
      {children}
    </span>
  );
}

function Chip({
  children,
  conflict,
}: {
  children: ReactNode;
  conflict?: boolean;
}) {
  return (
    <span
      className={cn(
        "rounded-full border px-1.5 py-0.5 text-[9px]",
        conflict
          ? "border-destructive/40 bg-destructive/10 text-destructive"
          : "border-annotation/30 bg-annotation/10 text-annotation-foreground dark:text-annotation"
      )}
    >
      {children}
    </span>
  );
}

function MiniCandidate({
  name,
  score,
  Icon,
  chips,
  dim,
}: {
  name: string;
  score: string;
  Icon: typeof User;
  chips: { label: string; conflict?: boolean }[];
  dim?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border/60 p-2",
        dim && "opacity-50"
      )}
    >
      <div className="flex items-center gap-2 text-xs">
        <Icon size={13} className="shrink-0 text-sky-400" />
        <span className="font-medium">{name}</span>
        <span className="text-[9px] uppercase tracking-widest text-muted-foreground/70">
          entity
        </span>
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground">
          {score}
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {chips.map((c) => (
          <Chip key={c.label} conflict={c.conflict}>
            {c.label}
          </Chip>
        ))}
      </div>
    </div>
  );
}

/* --- slides ---------------------------------------------------------------- */

const SLIDES: { title: string; body: ReactNode }[] = [
  {
    title: "Three things: a mention, a name group, an entity",
    body: (
      <div className="space-y-3 text-xs leading-relaxed text-muted-foreground">
        <p>
          A <b className="text-foreground">mention</b> is one occurrence of a
          name in the evidence — a <code>From:</code> line, a signature, a
          sentence. Extraction produces thousands of them and none are tied to
          anyone yet.
        </p>
        <p>
          Every mention of the same spelling is bucketed into a{" "}
          <b className="text-foreground">name group</b>:{" "}
          <NameChip>Nick Bolton</NameChip> across 4,493 emails is{" "}
          <i>one</i> group.
        </p>
        <p>
          An <b className="text-foreground">entity</b> is the real person /
          organisation / location that mentions get attached to. Resolution is
          the act of deciding which entity a name group belongs to — or that it
          needs a new one.
        </p>
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/30 p-3">
          <span className="flex items-center gap-1 text-[11px]">
            <FileText size={12} className="text-muted-foreground" /> 4,493
            mentions
          </span>
          <ArrowRight size={12} className="text-muted-foreground/50" />
          <NameChip>Nick Bolton</NameChip>
          <ArrowRight size={12} className="text-muted-foreground/50" />
          <span className="flex items-center gap-1 text-[11px]">
            <User size={12} className="text-sky-400" /> entity “Nick B”
          </span>
        </div>
      </div>
    ),
  },
  {
    title: "Step 1 — Extraction makes mentions",
    body: (
      <div className="space-y-3 text-xs leading-relaxed text-muted-foreground">
        <p>
          Names and identifiers are pulled from email headers
          (<code>From / To / Cc / Bcc</code>), signatures, contact cards, and
          body text. Email addresses and phone numbers become{" "}
          <b className="text-foreground">selector</b> entities; the display names
          beside them become unresolved <b className="text-foreground">name</b>{" "}
          mentions.
        </p>
        <p>
          Nothing is a person or an organisation yet — a header name is
          genuinely ambiguous between the two.
        </p>
        <div className="rounded-lg border border-border bg-muted/30 p-3 font-mono text-[10px] text-muted-foreground">
          From: &quot;Nick Bolton&quot; &lt;bolton213@yahoo.com&gt;
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Chip>name mention · “Nick Bolton”</Chip>
            <Chip>selector · bolton213@yahoo.com</Chip>
          </div>
        </div>
      </div>
    ),
  },
  {
    title: "Step 2 — Blocking and scoring",
    body: (
      <div className="space-y-3 text-xs leading-relaxed text-muted-foreground">
        <p>
          For each name group the resolver gathers a short list of existing
          entities that <i>could</i> be a match (same address, same or similar
          name, a name-key hit) and scores each one. Every score is a sum of
          explainable signals — the chips you see on the cards:
        </p>
        <div className="flex flex-wrap gap-1">
          {Object.values(RESOLUTION_FEATURE_META).map((m) => (
            <Chip key={m.label}>{m.label}</Chip>
          ))}
        </div>
        <p>
          Positive signals add to the score; a{" "}
          <span className="text-destructive">conflict</span> (person vs
          organisation, a date-of-birth clash, same surname but a clearly
          different first name) <b className="text-foreground">vetoes</b> that
          candidate outright.
        </p>
      </div>
    ),
  },
  {
    title: "Step 3 — Auto, review, or unmatched",
    body: (
      <div className="space-y-3 text-xs leading-relaxed text-muted-foreground">
        <p>The score decides where a name group goes:</p>
        <ul className="space-y-2">
          <li className="rounded-lg border border-border/60 p-2">
            <span className="inline-flex items-center gap-1 font-medium text-foreground">
              <Sparkles size={11} className="text-annotation" /> Auto-attached
            </span>{" "}
            — one safe rule only: an exact shared identifier on a structured
            field <i>plus</i> a real name match, with a clear margin over any
            runner-up. These land in <b className="text-foreground">Resolve →
            Confirmed</b> with an “auto” tag; you can undo them.
          </li>
          <li className="rounded-lg border border-border/60 p-2">
            <span className="font-medium text-foreground">Review</span> — one or
            more plausible candidates, but not safe enough to auto-attach. These
            fill the <b className="text-foreground">Resolve</b> tab.
          </li>
          <li className="rounded-lg border border-border/60 p-2">
            <span className="font-medium text-foreground">Unmatched</span> — no
            candidate cleared the bar. These go to the{" "}
            <b className="text-foreground">Review</b> tab for classification from
            scratch.
          </li>
        </ul>
      </div>
    ),
  },
  {
    title: "The Resolve tab — confirm or reject a match",
    body: (
      <div className="space-y-3 text-xs leading-relaxed text-muted-foreground">
        <p>
          Each card is one name group: the amber box is the{" "}
          <b className="text-foreground">name</b>, the rows beneath are existing{" "}
          <b className="text-foreground">entities</b> it might be, best first. A
          row tagged <b className="text-foreground">provisional</b> is an entity
          the resolver minted on an earlier pass — it has no Persons-tab entry
          or face gallery yet; confirming folds the mentions into it.
        </p>
        <div className="rounded-xl border border-border p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[9px] uppercase tracking-widest text-muted-foreground/70">
              name
            </span>
            <NameChip>Nick Bolton</NameChip>
            <span className="text-[10px] text-muted-foreground">
              14,856 mentions · 4,493 files
            </span>
          </div>
          <div className="space-y-1.5">
            <MiniCandidate
              name="Nick B"
              score="0.99"
              Icon={User}
              chips={[
                { label: "shared identifier +6.0" },
                { label: "name structure +1.2" },
                { label: "co-mentioned +1.2" },
              ]}
            />
            <MiniCandidate
              name="Edmond Bolton"
              score="—"
              Icon={User}
              dim
              chips={[
                { label: "shared identifier" },
                { label: "name structure", conflict: true },
              ]}
            />
          </div>
        </div>
        <ul className="space-y-1.5">
          <li>
            <span className="inline-flex items-center gap-1 font-medium text-foreground">
              <Check size={11} /> Confirm
            </span>{" "}
            on a row → attaches <i>every</i> mention of “Nick Bolton” to that
            entity.
          </li>
          <li>
            <span className="inline-flex items-center gap-1 font-medium text-foreground">
              <X size={11} /> Reject
            </span>{" "}
            → drops just that candidate.
          </li>
          <li>
            <b className="text-foreground">None of these</b> → rejects them all;
            the name moves to the Review tab.
          </li>
          <li>
            Tick the clean cards and use{" "}
            <b className="text-foreground">Confirm all</b> to clear them in one
            go.
          </li>
        </ul>
      </div>
    ),
  },
  {
    title: "The Review tab — classify from scratch",
    body: (
      <div className="space-y-3 text-xs leading-relaxed text-muted-foreground">
        <p>
          Names with <b className="text-foreground">no candidate</b>. There is
          nothing to confirm — you say what each one is:
        </p>
        <div className="rounded-xl border border-border p-3">
          <div className="mb-2 flex items-center gap-2">
            <NameChip>Pumpkin Pet Care Team</NameChip>
            <span className="text-[10px] text-muted-foreground">
              31 mentions · 12 files
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[10px]">
              <User size={11} /> Person
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[10px]">
              <Building2 size={11} /> Organization
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[10px]">
              <Mail size={11} /> Location
            </span>
            <span className="rounded-md border border-border px-2 py-1 text-[10px]">
              Attach…
            </span>
            <span className="rounded-md px-2 py-1 text-[10px] text-muted-foreground">
              Not an entity
            </span>
          </div>
        </div>
        <ul className="space-y-1.5">
          <li>
            <b className="text-foreground">Person / Organization / Location</b> —
            creates a <i>new</i> entity of that type and attaches every mention
            of the name to it.
          </li>
          <li>
            <b className="text-foreground">Attach…</b> — opens a search box; pick
            an entity that <i>already exists</i> and link the name&apos;s
            mentions to it instead of making a duplicate.
          </li>
          <li>
            <b className="text-foreground">Not an entity</b> — discard the
            mentions (a subject-line fragment, a mailing-list footer, parser
            junk).
          </li>
        </ul>
      </div>
    ),
  },
  {
    title: "After resolution",
    body: (
      <div className="space-y-3 text-xs leading-relaxed text-muted-foreground">
        <p>Once a name group is resolved:</p>
        <ul className="space-y-1.5">
          <li>Its mentions now point at the entity and show on the entity dossier.</li>
          <li>
            Graph edges get built — <code>has_selector</code> (person ↔ address),{" "}
            <code>emailed</code> (who emailed whom).
          </li>
          <li>
            Auto-attached rows carry a{" "}
            <span className="inline-flex items-center gap-0.5 text-annotation">
              <Sparkles size={9} /> auto
            </span>{" "}
            tag, are listed under <b className="text-foreground">Confirmed</b>,
            and can be reverted.
          </li>
          <li>
            Every Confirm / Reject you make is kept as labelled training data —
            it&apos;s what re-tunes the signal weights over time.
          </li>
        </ul>
      </div>
    ),
  },
];

export default function ResolutionGuidePage() {
  const [api, setApi] = useState<CarouselApi>();
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    if (!api) return;
    const onSelect = () => setCurrent(api.selectedScrollSnap());
    api.on("select", onSelect).on("reInit", onSelect);
    return () => {
      api.off("select", onSelect).off("reInit", onSelect);
    };
  }, [api]);

  return (
    <div className="mx-auto max-w-3xl px-6 pb-16 pt-5">
      <PageHeader>
        <div className="flex min-w-0 items-center gap-1.5 text-xs">
          <Link
            href="/entities"
            className="font-mono text-muted-foreground hover:text-primary"
          >
            Entities
          </Link>
          <span className="text-muted-foreground/50">/</span>
          <span className="font-mono text-primary/80">How resolution works</span>
        </div>
      </PageHeader>

      <Link
        href="/entities"
        className="inline-flex w-fit items-center gap-1.5 text-[11px] font-semibold text-primary hover:underline"
      >
        <ArrowLeft size={12} /> Back to entities
      </Link>

      <h1 className="mt-4 text-lg font-semibold">
        How entity resolution works
      </h1>
      <p className="mt-1 text-xs text-muted-foreground">
        What the <b>Resolve</b> and <b>Review</b> tabs do, and what happens when
        you click.
      </p>

      <Carousel
        setApi={setApi}
        opts={{ align: "start" }}
        className="mt-6"
      >
        <CarouselContent>
          {SLIDES.map((s, i) => (
            <CarouselItem key={i}>
              <div className="min-h-72 rounded-xl border border-border bg-card p-5">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Step {i + 1} of {SLIDES.length}
                </p>
                <h2 className="mt-1 text-sm font-semibold">{s.title}</h2>
                <div className="mt-3">{s.body}</div>
              </div>
            </CarouselItem>
          ))}
        </CarouselContent>
        <div className="mt-4 flex items-center justify-between">
          <CarouselPrevious className="static translate-y-0" />
          <div className="flex gap-1.5">
            {SLIDES.map((_, i) => (
              <button
                key={i}
                aria-label={`Go to step ${i + 1}`}
                onClick={() => api?.scrollTo(i)}
                className={cn(
                  "h-1.5 rounded-full transition-all",
                  i === current
                    ? "w-4 bg-primary"
                    : "w-1.5 bg-border hover:bg-muted-foreground/50"
                )}
              />
            ))}
          </div>
          <CarouselNext className="static translate-y-0" />
        </div>
      </Carousel>

      <h2 className="mt-12 text-sm font-semibold">Signal glossary</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        The chips on every candidate row. Hover one in the queue to see the same
        text.
      </p>
      <dl className="mt-3 divide-y divide-border/60 rounded-xl border border-border">
        {Object.values(RESOLUTION_FEATURE_META).map((m) => (
          <div key={m.label} className="flex flex-col gap-1 p-3 sm:flex-row sm:gap-4">
            <dt className="sm:w-40 sm:shrink-0">
              <span className="rounded-full border border-annotation/30 bg-annotation/10 px-1.5 py-0.5 text-[10px] text-annotation-foreground dark:text-annotation">
                {m.label}
              </span>
              {m.veto && (
                <span className="ml-1 text-[9px] uppercase tracking-widest text-destructive">
                  can veto
                </span>
              )}
            </dt>
            <dd className="text-xs leading-relaxed text-muted-foreground">
              {m.blurb}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mt-8 flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline" className="h-8 text-xs">
          <Link href="/entities">
            Go to the Resolve tab <ArrowRight size={12} className="ml-1" />
          </Link>
        </Button>
      </div>
    </div>
  );
}
