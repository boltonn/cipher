"use client";

import { Badge } from "@/components/ui/badge";
import { facesService } from "@/features/faces/api";
import { usePersonRepresentativeFaces } from "@/features/persons/hooks/use-persons";
import { Person } from "@/features/persons/types";
import { BadgeCheck, UserRound } from "lucide-react";
import Link from "next/link";

interface PersonCardProps {
  person: Person;
}

export function PersonCard({ person }: PersonCardProps) {
  const { data: faces } = usePersonRepresentativeFaces(person.id);
  const primaryFace = faces?.[0];

  return (
    <Link
      href={`/persons/${person.id}`}
      className="group relative rounded-xl overflow-hidden bg-muted/40 border border-border/50 transition-all duration-300 hover:border-primary/40 hover:bg-muted/60 p-4 flex flex-col items-center gap-3 h-full"
    >
      <div className="h-16 w-16 rounded-full shrink-0 overflow-hidden bg-primary/10 text-primary text-lg font-black flex items-center justify-center group-hover:ring-2 group-hover:ring-primary/40 transition-all">
        {primaryFace ? (
          // eslint-disable-next-line @next/next/no-img-element -- tiny same-origin avatar, server already crops/downscales
          <img
            src={facesService.getFaceThumbnailUrl(primaryFace.id)}
            alt=""
            className="h-full w-full object-cover"
          />
        ) : person.name ? (
          person.name[0].toUpperCase()
        ) : (
          <UserRound size={24} />
        )}
      </div>

      <div className="flex flex-col items-center gap-1.5 min-w-0 w-full">
        <div className="flex items-center gap-1 min-w-0">
          <span className="text-xs font-bold text-foreground truncate">
            {person.name || "Unnamed"}
          </span>
          {person.isVerified && (
            <BadgeCheck size={12} className="text-primary shrink-0" />
          )}
        </div>
        {person.tags.length > 0 && (
          <div className="flex flex-wrap justify-center gap-1">
            {person.tags.slice(0, 2).map((tag) => (
              <Badge
                key={tag}
                variant="outline"
                className="h-5 text-[10px] px-1.5 py-0 bg-muted/40 border-border text-muted-foreground"
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
