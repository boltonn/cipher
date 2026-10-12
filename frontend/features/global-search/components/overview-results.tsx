"use client";

import { Button } from "@/components/ui/button";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import type { EntitySearchResult } from "@/features/entities/types";
import { facesService } from "@/features/faces/api";
import type { FacePublic } from "@/features/faces/types";
import { toGroupedFileResult } from "@/features/search/api";
import { FileResultGroup } from "@/features/search/components/file-result-group";
import { cn } from "@/lib/utils";
import { format, parseISO } from "date-fns";
import {
  CalendarDays,
  FileText,
  Filter,
  Image as ImageIcon,
  MapPin,
  Paperclip,
  Share2,
  Smile,
  Waypoints,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { LaneName, OverviewFilters, OverviewResponse } from "../types";
import { LaneSection } from "./lane-section";
import { ImageThumb } from "./image-thumb";
import { TimeHistogram } from "./time-histogram";

interface OverviewResultsProps {
  overview: OverviewResponse;
  /** The AI read the search as about what's in photos: images lead unless the query named someone. */
  isVisual?: boolean;
  onAddFilters: (filters: Partial<OverviewFilters>) => void;
  /** Open a lane's own page; `imageId` opens that image's similar-images view. */
  onSeeAll: (lane: LaneName, options?: { imageId?: string }) => void;
}

const rowClass =
  "flex items-center gap-3 rounded-lg px-2 py-1.5 text-sm text-foreground transition-colors hover:bg-muted";

function EntityRow({
  entity,
  hero,
  onFilter,
}: {
  entity: EntitySearchResult;
  hero?: boolean;
  onFilter: () => void;
}) {
  const meta = ENTITY_TYPE_META[entity.entityType];
  return (
    <div
      className={cn(
        "flex items-center gap-3",
        hero ? "rounded-xl border border-border bg-background/60 p-4" : "rounded-lg px-2 py-1.5"
      )}
    >
      <span className={cn("grid shrink-0 place-items-center rounded-full", hero ? "size-10" : "size-7", meta.bgClass)}>
        <meta.Icon className={cn(hero ? "size-5" : "size-4", meta.textClass)} />
      </span>
      <div className="min-w-0 flex-1">
        <Link href={`/entities/${entity.id}`} className={cn("truncate hover:underline", hero && "text-lg font-medium")}>
          {entity.displayName}
        </Link>
        <p className="text-xs text-muted-foreground">
          {meta.label}
          {entity.isProvisional && " · not yet verified"}
        </p>
      </div>
      <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={onFilter}>
        <Filter className="size-3.5" /> Files mentioning
      </Button>
      <Button asChild variant="ghost" size="sm" className="h-7 gap-1 text-xs">
        <Link href={`/entities/${entity.id}/graph`}>
          <Share2 className="size-3.5" /> Graph
        </Link>
      </Button>
    </div>
  );
}

/** A face crop linking to its person (assigned, else the suggested match), or to similar faces. */
function FaceTile({ face }: { face: FacePublic }) {
  const personId = face.personId ?? face.candidatePersonId;
  const name = face.personName ?? face.candidatePersonName;
  return (
    <Link
      href={personId ? `/persons/${personId}` : `/faces?similar=${face.id}`}
      className="group block min-w-0"
      title={face.personName ? face.personName : name ? `Possible match: ${name}` : "Find similar faces"}
    >
      <span className="block aspect-square overflow-hidden rounded-md border border-border bg-muted">
        {/* eslint-disable-next-line @next/next/no-img-element -- API-served thumbnails, not static assets */}
        <img
          src={facesService.getFaceThumbnailUrl(face.id)}
          alt={name ?? ""}
          loading="lazy"
          className="size-full object-cover transition-transform group-hover:scale-105"
        />
      </span>
      <span
        className={cn(
          "mt-1 block truncate text-xs",
          face.personName ? "text-muted-foreground" : "text-annotation"
        )}
      >
        {face.personName ?? (name ? `${name}?` : "Unassigned")}
      </span>
    </Link>
  );
}

/** The results page body: lanes in the layout's order, the featured one first and larger. */
export function OverviewResults({ overview, isVisual, onAddFilters, onSeeAll }: OverviewResultsProps) {
  const router = useRouter();
  const { layout, request } = overview;
  const query = request.query;

  const lanes: Record<LaneName, (hero: boolean) => React.ReactNode> = {
    entities: (hero) => (
      <LaneSection
        key="entities"
        title="People, organizations & identifiers"
        icon={<Waypoints className="size-4" />}
        lane={overview.entities}
        onSeeAll={() => onSeeAll("entities")}
      >
        <div className="space-y-1">
          {overview.entities.items.map((entity, index) => (
            <EntityRow
              key={entity.id}
              entity={entity}
              hero={hero && index === 0}
              onFilter={() => onAddFilters({ entityIds: [entity.id] })}
            />
          ))}
        </div>
      </LaneSection>
    ),
    text: () => (
      <LaneSection
        key="text"
        title="Emails & documents"
        icon={<FileText className="size-4" />}
        lane={overview.text}
        onSeeAll={() => onSeeAll("text")}
      >
        {overview.text.shape && overview.text.shape.dateHistogram.length > 1 && (
          <div className="mb-3">
            <TimeHistogram
              months={overview.text.shape.dateHistogram}
              height={40}
              onSelect={(bin) => onAddFilters({ dateFrom: bin.dateFrom, dateTo: bin.dateTo })}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              When the top {overview.text.shape.sampleSize.toLocaleString()} matches were sent or written. Click a bar
              to narrow to it.
            </p>
          </div>
        )}
        <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
          {overview.text.items.map((raw) => {
            const group = toGroupedFileResult(raw);
            return (
              <FileResultGroup
                key={group.fileId}
                group={group}
                isSelected={false}
                searchMode="hybrid"
                query={query || null}
                onSelect={() => router.push(`/files/${group.fileId}`)}
              />
            );
          })}
        </div>
      </LaneSection>
    ),
    faces: () => {
      const personId = overview.faces.items.find((face) => face.personId)?.personId;
      return (
        <LaneSection
          key="faces"
          title="Faces"
          icon={<Smile className="size-4" />}
          lane={overview.faces}
          onSeeAll={() => (personId ? router.push(`/persons/${personId}`) : onSeeAll("faces"))}
        >
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 lg:grid-cols-12">
            {overview.faces.items.map((face) => (
              <FaceTile key={face.id} face={face} />
            ))}
          </div>
        </LaneSection>
      );
    },
    images: (hero) => (
      <LaneSection
        key="images"
        title="Images"
        icon={<ImageIcon className="size-4" />}
        lane={overview.images}
        onSeeAll={() => onSeeAll("images")}
      >
        <div className={cn("grid gap-2", hero ? "grid-cols-4 sm:grid-cols-8" : "grid-cols-8")}>
          {overview.images.items.map((image) => (
            <ImageThumb key={image.id} imageId={image.id} onOpen={() => onSeeAll("images", { imageId: image.id })} />
          ))}
        </div>
      </LaneSection>
    ),
    files: () => (
      <LaneSection key="files" title="File names" icon={<Paperclip className="size-4" />} lane={overview.files}>
        <div className="space-y-0.5">
          {overview.files.items.map((file) => (
            <Link key={file.id} href={`/files/${file.id}`} className={rowClass}>
              <span className="min-w-0 flex-1 truncate">{file.filename}</span>
              <span className="text-xs text-muted-foreground">{file.filetypeGroup}</span>
            </Link>
          ))}
        </div>
      </LaneSection>
    ),
    events: () => (
      <LaneSection
        key="events"
        title="Events"
        icon={<CalendarDays className="size-4" />}
        lane={overview.events}
        onSeeAll={() => onSeeAll("events")}
      >
        <div className="space-y-0.5">
          {overview.events.items.map((event) => (
            <button key={event.id} type="button" onClick={() => onSeeAll("events")} className={cn(rowClass, "w-full")}>
              <span className="min-w-0 flex-1 truncate text-left">{event.title}</span>
              <span className="text-xs text-muted-foreground">{format(parseISO(event.dateStart), "d MMM yyyy")}</span>
            </button>
          ))}
        </div>
      </LaneSection>
    ),
    places: () => (
      <LaneSection key="places" title="Places" icon={<MapPin className="size-4" />} lane={overview.places}>
        <div className="space-y-0.5">
          {overview.places.items.map((place) => (
            <Link key={place.id} href="/locations" className={rowClass}>
              <span className="min-w-0 flex-1 truncate">{place.name}</span>
              <span className="text-xs text-muted-foreground">
                {[place.city, place.adminArea, place.country].filter(Boolean).join(", ")}
              </span>
            </Link>
          ))}
        </div>
      </LaneSection>
    ),
  };

  const promoteImages =
    isVisual && overview.images.items.length > 0 && (layout.queryKind === "topic" || layout.queryKind === "question");
  const hero = promoteImages ? "images" : layout.hero;
  const rest = layout.laneOrder.filter((lane) => lane !== hero);
  return (
    <div className="space-y-4">
      {hero && lanes[hero](true)}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {rest.map((lane) => (
          <div key={lane} className={cn((lane === "text" || lane === "faces") && "xl:col-span-2")}>
            {lanes[lane](false)}
          </div>
        ))}
      </div>
    </div>
  );
}
