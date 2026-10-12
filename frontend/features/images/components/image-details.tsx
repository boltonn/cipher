"use client";

import { Button } from "@/components/ui/button";
import { facesService } from "@/features/faces/api";
import type { OverlayBox } from "@/features/faces/components/face-image-overlay";
import { FaceTriagePanel } from "@/features/faces/components/face-triage-panel";
import { useImageFaces } from "@/features/faces/hooks/use-image-faces";
import type { FacePublic } from "@/features/faces/types";
import { cn } from "@/lib/utils";
import { Camera, ImageIcon, ScanFace, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useFileImage } from "../api";
import type { ImagePublic } from "../types";

function faceMatchLabel(face: FacePublic): string | undefined {
  if (face.personName)
    return `${face.personName} · ${face.status === "verified" ? "verified" : "matched"}`;
  if (face.candidatePersonName)
    return `${face.candidatePersonName} · potential match`;
  return undefined;
}

export interface ImageFaceSelection {
  faces: FacePublic[];
  activeFace?: FacePublic;
  selectFace: (faceId: string) => void;
  findSimilar: (faceId: string) => void;
  /** Boxes to draw on the image; undefined when it has no faces. */
  overlayBoxes?: OverlayBox[];
}

/**
 * An image's faces and which one is selected -- shared by the picture (its boxes) and the
 * panel beside it (the face list and triage), so clicking either selects in both.
 */
export function useImageFaceSelection(
  imageId: string | undefined,
  {
    focusFaceId,
    onFindSimilarFace,
  }: {
    /** Face to select first; selection resets to it whenever it changes. */
    focusFaceId?: string;
    /** Run a "find similar faces" search; defaults to navigating to /faces?similar=<id>. */
    onFindSimilarFace?: (faceId: string) => void;
  } = {}
): ImageFaceSelection {
  const router = useRouter();
  const { data: faces = [] } = useImageFaces(imageId);
  const [activeFaceId, setActiveFaceId] = useState<string | undefined>(
    focusFaceId
  );
  const [prevFocusFaceId, setPrevFocusFaceId] = useState(focusFaceId);
  if (focusFaceId !== prevFocusFaceId) {
    setPrevFocusFaceId(focusFaceId);
    setActiveFaceId(focusFaceId);
  }
  const activeFace =
    faces.find((face) => face.id === activeFaceId) ??
    faces.find((face) => face.id === focusFaceId) ??
    faces[0];

  const findSimilar = useMemo(
    () =>
      onFindSimilarFace ??
      ((faceId: string) => router.push(`/faces?similar=${faceId}`)),
    [onFindSimilarFace, router]
  );

  const overlayBoxes = useMemo<OverlayBox[] | undefined>(() => {
    if (faces.length === 0) return undefined;
    return faces.map((face) => ({
      bbox: face.boundingBox,
      landmarks: face.id === activeFace?.id ? face.landmarks : undefined,
      isSelected: face.id === activeFace?.id,
      label:
        face.id === activeFace?.id
          ? (face.personName ?? face.candidatePersonName ?? undefined)
          : undefined,
      onClick: () => setActiveFaceId(face.id),
      onFindSimilar: () => findSimilar(face.id),
      matchLabel: faceMatchLabel(face),
    }));
  }, [faces, activeFace?.id, findSimilar]);

  return {
    faces,
    activeFace,
    selectFace: setActiveFaceId,
    findSimilar,
    overlayBoxes,
  };
}

/** The image's detected faces as thumbnails, with triage for the selected one. */
export function ImageFacesSection({
  selection,
  onCreatePerson,
}: {
  selection: ImageFaceSelection;
  onCreatePerson?: (face: FacePublic) => void;
}) {
  const { faces, activeFace, selectFace, findSimilar } = selection;
  if (faces.length === 0) return null;
  return (
    <section className="p-4 rounded-xl bg-black/40 border border-annotation/20 space-y-4">
      <div className="flex items-center gap-2">
        <ScanFace size={14} className="text-annotation" />
        <h4 className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
          Faces
        </h4>
        <span className="ml-auto text-[11px] font-mono text-muted-foreground">
          {faces.length} detected
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {faces.map((face) => (
          <div
            key={face.id}
            role="button"
            tabIndex={0}
            title={faceMatchLabel(face)}
            onClick={() => selectFace(face.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectFace(face.id);
              }
            }}
            className={cn(
              "group/thumb relative h-14 w-14 shrink-0 overflow-hidden rounded-lg border-2 cursor-pointer",
              face.id === activeFace?.id
                ? "border-emerald-400"
                : "border-border/50 hover:border-annotation/50"
            )}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- tiny same-origin crop, server already downscales */}
            <img
              src={facesService.getFaceThumbnailUrl(face.id)}
              alt=""
              className="h-full w-full object-cover"
            />
            <span
              role="button"
              tabIndex={-1}
              title="Find similar faces"
              onClick={(event) => {
                event.stopPropagation();
                findSimilar(face.id);
              }}
              className="absolute inset-x-0 bottom-0 flex justify-center bg-black/75 py-0.5 opacity-0 transition-opacity group-hover/thumb:opacity-100"
            >
              <Search size={11} className="text-annotation" />
            </span>
          </div>
        ))}
      </div>

      {activeFace && (
        <FaceTriagePanel
          face={activeFace}
          onFindSimilar={findSimilar}
          onCreatePerson={onCreatePerson}
        />
      )}
    </section>
  );
}

/** Camera details from the image's EXIF; nothing when it has none. */
export function ImageCameraSection({ image }: { image: ImagePublic }) {
  const details = [
    {
      label: "Camera",
      value:
        [image.cameraMake, image.cameraModel].filter(Boolean).join(" ") || null,
    },
    { label: "Aperture", value: image.aperture ? `ƒ/${image.aperture}` : null },
    { label: "ISO", value: image.iso?.toString() ?? null },
    {
      label: "Focal length",
      value: image.focalLength ? `${image.focalLength}mm` : null,
    },
    {
      label: "Date taken",
      value: image.dateTaken
        ? new Date(image.dateTaken).toLocaleDateString()
        : null,
    },
    {
      label: "Elevation",
      value: image.gpsAltitude ? `${image.gpsAltitude.toFixed(1)}m` : null,
    },
  ].filter(
    (detail): detail is { label: string; value: string } =>
      detail.value !== null
  );
  if (details.length === 0) return null;
  return (
    <section className="p-4 rounded-xl bg-black/40 border border-border/50 space-y-4">
      <div className="flex items-center gap-2">
        <Camera size={14} className="text-primary" />
        <h4 className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
          Camera
        </h4>
      </div>
      <div className="grid grid-cols-2 gap-y-4 gap-x-4">
        {details.map((detail) => (
          <div key={detail.label} className="flex flex-col gap-0.5 min-w-0">
            <p className="text-muted-foreground uppercase text-[11px] font-semibold tracking-wide leading-none mb-1">
              {detail.label}
            </p>
            <p className="text-foreground font-mono text-[11px] truncate leading-none">
              {detail.value}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

/** A file's image record (when the images pipeline has processed it) and its face selection. */
export function useFileImageDetails(file: {
  id?: string;
  filetypeGroup: string;
}) {
  const { data: image } = useFileImage(
    file.filetypeGroup === "image" ? file.id : undefined
  );
  const selection = useImageFaceSelection(image?.id);
  return { image, selection };
}

/** A file's image analysis: find similar images, its faces, its camera details. */
export function FileImageDetails({
  image,
  selection,
}: {
  image: ImagePublic;
  selection: ImageFaceSelection;
}) {
  return (
    <div className="space-y-4">
      <Button
        asChild
        variant="outline"
        size="sm"
        className="h-8 w-full gap-2 text-xs"
      >
        <Link href={`/images?id=${image.id}`}>
          <ImageIcon size={13} /> Find similar images
        </Link>
      </Button>
      <ImageFacesSection selection={selection} />
      <ImageCameraSection image={image} />
    </div>
  );
}
