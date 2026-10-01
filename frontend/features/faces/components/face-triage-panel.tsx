"use client";

import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/copyable-id";
import { PotentialMatches } from "@/features/faces/components/potential-matches";
import { useAssignFace } from "@/features/faces/hooks/use-assign-face";
import { useRejectFaces } from "@/features/faces/hooks/use-reject-faces";
import { FacePublic } from "@/features/faces/types";
import { PersonPicker } from "@/features/persons/components/person-picker";
import {
  usePerson,
  useUpdatePerson,
} from "@/features/persons/hooks/use-persons";
import { useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  BadgeCheck,
  Compass,
  ExternalLink,
  Gauge,
  ScanFace,
  Search,
  ShieldCheck,
  UserPlus,
  X,
} from "lucide-react";
import Link from "next/link";

interface FaceTriagePanelProps {
  face: FacePublic;
  onFindSimilar: (id: string) => void;
  onCreatePerson?: (face: FacePublic) => void;
}

/**
 * Per-face triage controls -- identity assignment, verification, pending-match
 * review, and detection metadata -- for one face within the shared asset viewer.
 */
export function FaceTriagePanel({
  face,
  onFindSimilar,
  onCreatePerson,
}: FaceTriagePanelProps) {
  const queryClient = useQueryClient();
  const assignFace = useAssignFace();
  const rejectFaces = useRejectFaces();
  const { data: person } = usePerson(face.personId);
  const verifyPerson = useUpdatePerson(face.personId ?? "", () =>
    queryClient.invalidateQueries({ queryKey: ["faces"] })
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <ScanFace size={14} className="text-annotation" />
        <h4 className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
          Face
        </h4>
        <div className="ml-auto">
          <CopyableId id={face.id} />
        </div>
      </div>

      {/* Assignment */}
      <section className="p-4 rounded-xl bg-black/40 border border-border/50 space-y-3">
        <PersonPicker
          value={face.personId}
          valueName={person?.name}
          onSelect={(personId) =>
            assignFace.mutate({
              id: face.id,
              assignment: { personId, assignmentMethod: "manual" },
            })
          }
        />
        {face.personId && (
          <>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-primary">
                {person?.isVerified && <BadgeCheck size={11} />}
                {person?.isVerified ? "Verified" : "Matched"}
              </span>
              <div className="flex items-center gap-3">
                <Link
                  href={`/persons/${face.personId}`}
                  className="text-xs font-medium text-primary/80 hover:text-primary flex items-center gap-1"
                >
                  View Profile <ExternalLink size={10} />
                </Link>
                <button
                  type="button"
                  onClick={() =>
                    assignFace.mutate({
                      id: face.id,
                      assignment: { personId: null },
                    })
                  }
                  className="text-xs font-medium text-destructive/60 hover:text-destructive flex items-center gap-1"
                >
                  <X size={10} /> Clear
                </button>
              </div>
            </div>
            {person && !person.isVerified && (
              <Button
                variant="outline"
                className="w-full h-8 text-xs font-medium border-primary/40 bg-primary/5 text-primary hover:bg-primary/10 gap-2"
                disabled={verifyPerson.isPending}
                onClick={() => verifyPerson.mutate({ isVerified: true })}
              >
                <ShieldCheck size={12} /> Verify Identity
              </Button>
            )}
          </>
        )}
      </section>

      <PotentialMatches faceId={face.id} />

      {/* Detection metadata */}
      <section className="p-4 rounded-xl bg-black/40 border border-border/50 space-y-4">
        <div className="flex items-center gap-2">
          <Gauge size={14} className="text-primary" />
          <h4 className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
            Detection
          </h4>
        </div>
        <div className="grid grid-cols-2 gap-y-4 gap-x-4">
          <DataPoint label="Model" value={face.detectorModel || "—"} />
          <DataPoint
            label="Confidence"
            value={
              face.detectionConfidence != null
                ? `${(face.detectionConfidence * 100).toFixed(0)}%`
                : "—"
            }
          />
          <DataPoint
            label="Quality"
            value={
              face.qualityScore != null
                ? `${(face.qualityScore * 100).toFixed(0)}%`
                : "—"
            }
          />
          <DataPoint label="Landmarks" value={String(face.landmarks.length)} />
          <DataPoint
            label="Representative"
            value={
              face.isPrimary ? "Primary" : face.isRepresentative ? "Yes" : "No"
            }
          />
        </div>
      </section>

      {face.pose && (
        <section className="p-4 rounded-xl bg-black/40 border border-border/50 space-y-4">
          <div className="flex items-center gap-2">
            <Compass size={14} className="text-primary" />
            <h4 className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
              Pose
            </h4>
          </div>
          <div className="grid grid-cols-3 gap-y-4 gap-x-4">
            <DataPoint label="Yaw" value={`${face.pose.yaw.toFixed(1)}°`} />
            <DataPoint label="Pitch" value={`${face.pose.pitch.toFixed(1)}°`} />
            <DataPoint label="Roll" value={`${face.pose.roll.toFixed(1)}°`} />
          </div>
        </section>
      )}

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          className="flex-1 h-9 text-xs font-medium border-border bg-muted/40 text-muted-foreground hover:text-annotation hover:border-annotation/40 gap-2"
          onClick={() => onFindSimilar(face.id)}
        >
          <Search size={12} /> Find Similar
        </Button>
        {onCreatePerson && (
          <Button
            variant="outline"
            className="flex-1 h-9 text-xs font-medium border-border bg-muted/40 text-muted-foreground hover:text-primary hover:border-primary/40 gap-2"
            onClick={() => onCreatePerson(face)}
          >
            <UserPlus size={12} /> Create Person
          </Button>
        )}
        <Button
          variant="outline"
          size="icon"
          aria-label="Not a face"
          title="Not a face (also rejects similar unassigned faces)"
          disabled={rejectFaces.isPending}
          className="h-9 w-9 border-border bg-muted/40 text-muted-foreground hover:text-destructive hover:border-destructive/40"
          onClick={() => rejectFaces.mutate([face.id])}
        >
          <Ban size={14} />
        </Button>
      </div>
    </div>
  );
}

const DataPoint = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-0.5">
    <p className="text-muted-foreground uppercase text-[11px] font-semibold tracking-wide leading-none mb-1">
      {label}
    </p>
    <p className="text-foreground font-mono text-[11px] truncate leading-none">
      {value}
    </p>
  </div>
);
