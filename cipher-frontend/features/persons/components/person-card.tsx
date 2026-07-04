"use client";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { facesService } from "@/features/faces/api";
import { getFaceCropStyle } from "@/features/faces/components/face-crop";
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
  const cropStyle = primaryFace
    ? getFaceCropStyle(primaryFace.boundingBox, facesService.getFaceViewUrl(primaryFace.id))
    : undefined;

  return (
    <Link href={`/persons/${person.id}`}>
      <Card className="group relative rounded-xl overflow-hidden bg-[#0a0c10] border-white/5 transition-all duration-300 hover:border-indigo-500/40 p-4 flex flex-col items-center gap-3 h-full">
        <div
          className="h-16 w-16 rounded-full shrink-0 overflow-hidden bg-indigo-500/10 bg-cover bg-center text-indigo-300 text-lg font-black flex items-center justify-center group-hover:ring-2 group-hover:ring-indigo-500/40 transition-all"
          style={cropStyle}
        >
          {!primaryFace && (person.name ? person.name[0].toUpperCase() : <UserRound size={24} />)}
        </div>

        <div className="flex flex-col items-center gap-1.5 min-w-0 w-full">
          <div className="flex items-center gap-1 min-w-0">
            <span className="text-xs font-bold text-slate-200 truncate">
              {person.name || "Unnamed"}
            </span>
            {person.isVerified && (
              <BadgeCheck size={12} className="text-indigo-400 shrink-0" />
            )}
          </div>
          {person.tags.length > 0 && (
            <div className="flex flex-wrap justify-center gap-1">
              {person.tags.slice(0, 2).map((tag) => (
                <Badge
                  key={tag}
                  variant="outline"
                  className="h-5 text-[10px] px-1.5 py-0 bg-slate-900/40 border-white/10 text-slate-400"
                >
                  #{tag}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </Card>
    </Link>
  );
}
