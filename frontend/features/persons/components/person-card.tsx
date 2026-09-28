"use client";

import { Badge } from "@/components/ui/badge";
import { PersonAvatar } from "@/features/persons/components/person-avatar";
import { Person } from "@/features/persons/types";
import { BadgeCheck } from "lucide-react";
import Link from "next/link";

interface PersonCardProps {
  person: Person;
}

export function PersonCard({ person }: PersonCardProps) {
  const secondary =
    person.aliases.length > 0
      ? `a.k.a. ${person.aliases[0]}${person.aliases.length > 1 ? ` +${person.aliases.length - 1}` : ""}`
      : person.dateOfBirth
        ? new Date(person.dateOfBirth).toLocaleDateString()
        : person.source === "manual"
          ? "Added manually"
          : "Clustered from faces";

  return (
    <Link
      href={`/persons/${person.id}`}
      className="group relative flex h-full flex-col items-center gap-3 overflow-hidden rounded-xl border border-border/50 bg-muted/40 p-5 transition-all duration-300 hover:border-primary/40 hover:bg-muted/60"
    >
      <PersonAvatar
        person={person}
        size="lg"
        className="transition-all group-hover:ring-2 group-hover:ring-primary/40"
      />

      <div className="flex w-full min-w-0 flex-col items-center gap-1">
        <div className="flex min-w-0 items-center gap-1">
          <span className="truncate text-sm font-bold text-foreground">
            {person.name || "Unnamed"}
          </span>
          {person.isVerified && (
            <BadgeCheck size={13} className="shrink-0 text-primary" />
          )}
        </div>
        <span className="truncate text-[11px] text-muted-foreground">{secondary}</span>
        {person.tags.length > 0 && (
          <div className="mt-1 flex flex-wrap justify-center gap-1">
            {person.tags.slice(0, 2).map((tag) => (
              <Badge
                key={tag}
                variant="outline"
                className="h-5 border-border bg-muted/40 px-1.5 py-0 text-[10px] text-muted-foreground"
              >
                #{tag}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}
