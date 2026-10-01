"use client";

import { facesService } from "@/features/faces/api";
import { usePersonRepresentativeFaces } from "@/features/persons/hooks/use-persons";
import type { Person } from "@/features/persons/types";
import { cn } from "@/lib/utils";
import { UserRound } from "lucide-react";

const SIZES = {
  sm: { box: "h-7 w-7 text-[11px]", icon: 13 },
  md: { box: "h-10 w-10 text-sm", icon: 18 },
  lg: { box: "h-20 w-20 text-xl", icon: 28 },
} as const;

interface PersonAvatarProps {
  person: Pick<Person, "id" | "name">;
  size?: keyof typeof SIZES;
  className?: string;
}

/** Representative face thumbnail, falling back to the name initial, then a glyph. */
export function PersonAvatar({ person, size = "md", className }: PersonAvatarProps) {
  const { data: faces } = usePersonRepresentativeFaces(person.id);
  const primaryFace = faces?.[0];
  const s = SIZES[size];

  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/10 font-semibold text-primary",
        s.box,
        className
      )}
    >
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
        <UserRound size={s.icon} />
      )}
    </div>
  );
}
