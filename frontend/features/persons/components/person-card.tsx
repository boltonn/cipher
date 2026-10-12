"use client";

import { facesService } from "@/features/faces/api";
import { usePersonRepresentativeFaces } from "@/features/persons/hooks/use-persons";
import { Person } from "@/features/persons/types";
import { cn } from "@/lib/utils";
import { BadgeCheck, Check, ScanFace, UserRound, UserRoundPen } from "lucide-react";
import Link from "next/link";

interface PersonCardProps {
  person: Person;
  isSelected?: boolean;
  /** Something in the grid is selected: a click toggles selection instead of opening the person. */
  isSelectionActive?: boolean;
  /** `range` = shift-click. */
  onToggleSelect?: (personId: string, range: boolean) => void;
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

/** Square portrait from the person's representative face, falling back to initials, then a glyph. */
function PersonPortrait({ person }: { person: Person }) {
  const { data: faces } = usePersonRepresentativeFaces(person.id);
  const face = faces?.[0];

  return (
    <div className="relative aspect-square w-full overflow-hidden bg-muted">
      {face ? (
        // eslint-disable-next-line @next/next/no-img-element -- small server-cropped face thumbnail
        <img
          src={facesService.getFaceThumbnailUrl(face.id)}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-primary/5 text-primary/70">
          {person.name ? (
            <span className="text-3xl font-semibold tracking-wide">{initials(person.name)}</span>
          ) : (
            <UserRound size={40} strokeWidth={1.25} />
          )}
        </div>
      )}
    </div>
  );
}

export function PersonCard({
  person,
  isSelected,
  isSelectionActive,
  onToggleSelect,
}: PersonCardProps) {
  const isClustered = person.source === "faceClustering";
  const details = [
    person.dateOfBirth && `Born ${new Date(person.dateOfBirth).toLocaleDateString()}`,
    person.sex && person.sex[0].toUpperCase() + person.sex.slice(1),
  ].filter(Boolean);

  return (
    <Link
      href={`/persons/${person.id}`}
      onClick={(e) => {
        if (!onToggleSelect || !(isSelectionActive || e.shiftKey)) return;
        e.preventDefault();
        onToggleSelect(person.id, e.shiftKey);
      }}
      aria-pressed={isSelectionActive ? !!isSelected : undefined}
      className={cn(
        "group relative flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/40",
        isSelected && "border-primary ring-2 ring-primary/40"
      )}
    >
      <PersonPortrait person={person} />

      {onToggleSelect && (
        <button
          type="button"
          aria-label={isSelected ? "Deselect person" : "Select person"}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onToggleSelect(person.id, e.shiftKey);
          }}
          className={cn(
            "absolute top-2 left-2 z-10 flex size-5 items-center justify-center rounded-md border shadow-sm transition-opacity",
            isSelected
              ? "border-primary bg-primary text-primary-foreground opacity-100"
              : "border-border bg-background/90 text-transparent opacity-0 hover:text-muted-foreground group-hover:opacity-100",
            isSelectionActive && "opacity-100"
          )}
        >
          <Check size={12} strokeWidth={3} />
        </button>
      )}

      <div className="flex flex-1 flex-col gap-1 border-t border-border px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-1">
          <span
            className={cn(
              "truncate text-sm font-semibold",
              person.name ? "text-foreground" : "italic text-muted-foreground"
            )}
          >
            {person.name || "Unnamed"}
          </span>
          {person.isVerified && (
            <BadgeCheck size={14} className="shrink-0 text-primary" aria-label="Verified" />
          )}
        </div>

        {person.aliases.length > 0 && (
          <p className="truncate text-[11px] text-muted-foreground" title={person.aliases.join(", ")}>
            a.k.a. {person.aliases.join(", ")}
          </p>
        )}
        {details.length > 0 && (
          <p className="truncate text-[11px] text-muted-foreground">{details.join(" · ")}</p>
        )}

        <div className="mt-auto flex min-w-0 items-center gap-1.5 pt-1.5">
          <span
            className={cn(
              "inline-flex shrink-0 items-center gap-1 text-[11px]",
              isClustered ? "text-annotation" : "text-muted-foreground"
            )}
          >
            {isClustered ? <ScanFace size={12} /> : <UserRoundPen size={12} />}
            {isClustered ? "Face clustering" : "Manual"}
          </span>
          {person.tags.length > 0 && (
            <span
              className="truncate text-[11px] text-muted-foreground"
              title={person.tags.map((t) => `#${t}`).join(" ")}
            >
              · {person.tags.map((t) => `#${t}`).join(" ")}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
