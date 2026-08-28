"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CommentSection } from "@/features/comments/components/comment-section";
import { EntityGraph } from "@/features/entities/components/entity-graph";
import { EntityMentionsByFile } from "@/features/entities/components/entity-mentions-by-file";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { Section } from "@/features/entities/components/section";
import { useEntityProfile } from "@/features/entities/hooks/use-entities";
import { FaceCard } from "@/features/faces/components/face-card";
import { FaceDetailDialog } from "@/features/faces/components/face-detail-dialog";
import { usePersonFaces } from "@/features/faces/hooks/use-person-faces";
import { FacePublic } from "@/features/faces/types";
import { EditPersonDialog } from "@/features/persons/components/edit-person-dialog";
import { PersonExampleUploadButton } from "@/features/persons/components/person-example-upload-button";
import { PersonExamplesGallery } from "@/features/persons/components/person-examples-gallery";
import {
  usePerson,
  usePersonRepresentativeFaces,
} from "@/features/persons/hooks/use-persons";
import {
  BadgeCheck,
  Cake,
  FileText,
  Fingerprint,
  ImagePlus,
  Loader2,
  Network,
  Pencil,
  ScanFace,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useMemo, useState } from "react";

export default function PersonDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const { data: person, isPending } = usePerson(id);
  const { data: representativeFaces, isPending: repPending } =
    usePersonRepresentativeFaces(id);
  const { data: profile } = useEntityProfile(id);
  const {
    data: facesData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isPending: facesPending,
  } = usePersonFaces(id);

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [selectedFace, setSelectedFace] = useState<FacePublic | null>(null);

  const recentFaces = useMemo(
    () => facesData?.pages.flatMap((p) => p.data) ?? [],
    [facesData]
  );
  const allFacesForNav = recentFaces;
  const selectedIndex = selectedFace
    ? allFacesForNav.findIndex((f) => f.id === selectedFace.id)
    : -1;

  const selectors = profile?.selectors ?? [];
  const related = profile?.relatedEntities ?? [];
  const mentionCounts = profile?.mentionCounts ?? {};
  const totalMentions = Object.values(mentionCounts).reduce((a, b) => a + b, 0);

  if (isPending || !person) {
    return (
      <div className="flex items-center justify-center py-48 text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin text-primary/40" />
      </div>
    );
  }

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20">
      <PageHeader
        eyebrow="Person"
        value={
          totalMentions
            ? `${recentFaces.length} faces · ${totalMentions} mentions`
            : `${recentFaces.length} faces`
        }
      />

      {/* Identity header */}
      <div className="mt-4 rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-6 flex flex-col gap-4">
        <div className="flex items-start gap-6">
          <PersonExamplesGallery
            personId={id}
            faces={representativeFaces ?? []}
            isPending={repPending}
          />

          <div className="flex-1 min-w-0 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2.5">
                  <h1 className="text-xl font-bold text-white">
                    {person.name || "Unnamed Person"}
                  </h1>
                  {person.isVerified && (
                    <Badge className="h-6 bg-primary/10 text-primary border-none gap-1.5 text-xs px-2.5">
                      <BadgeCheck size={14} /> Verified
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-5 mt-2 text-sm text-muted-foreground">
                  {person.sex && (
                    <span className="capitalize">{person.sex}</span>
                  )}
                  {person.dateOfBirth && (
                    <span className="flex items-center gap-1.5">
                      <Cake size={14} />
                      {new Date(person.dateOfBirth).toLocaleDateString()}
                    </span>
                  )}
                  {person.aliases.length > 0 && (
                    <span>aka {person.aliases.join(", ")}</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <PersonExampleUploadButton
                  personId={id}
                  atCap={(representativeFaces?.length ?? 0) >= 10}
                  className="flex items-center gap-2 border border-border/50 bg-muted/40 rounded-md text-muted-foreground hover:text-annotation hover:border-annotation/30 uppercase text-[10px] font-bold tracking-widest h-9 px-3 disabled:opacity-30 disabled:pointer-events-none transition-colors"
                >
                  <ImagePlus size={14} />
                  Upload Exemplar
                </PersonExampleUploadButton>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsEditOpen(true)}
                  className="border-border/50 bg-muted/40 text-muted-foreground hover:text-primary uppercase text-[10px] font-bold tracking-widest gap-2 h-9"
                >
                  <Pencil size={14} />
                  Edit
                </Button>
              </div>
            </div>

            {person.notes && (
              <p className="text-sm text-foreground leading-relaxed">
                {person.notes}
              </p>
            )}

            {person.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {person.tags.map((tag) => (
                  <Badge
                    key={tag}
                    variant="outline"
                    className="h-7 text-sm px-3 bg-muted/40 border-border text-foreground"
                  >
                    #{tag}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <div className="lg:col-span-2 flex flex-col gap-8">
          {/* Recent faces */}
          <Section
            title="Recent Faces"
            icon={<ScanFace size={14} className="text-primary" />}
          >
            {facesPending ? (
              <Loader2
                size={16}
                className="animate-spin text-muted-foreground"
              />
            ) : recentFaces.length ? (
              <>
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                  {recentFaces.map((face) => (
                    <FaceCard
                      key={face.id}
                      face={face}
                      onExpand={setSelectedFace}
                      onFindSimilar={(faceId) =>
                        router.push(`/faces?similar=${faceId}`)
                      }
                    />
                  ))}
                </div>
                {hasNextPage && (
                  <div className="flex justify-center mt-4">
                    <Button
                      variant="ghost"
                      onClick={() => fetchNextPage()}
                      disabled={isFetchingNextPage}
                      className="text-[10px] uppercase tracking-widest text-primary"
                    >
                      {isFetchingNextPage && (
                        <Loader2 size={12} className="animate-spin mr-2" />
                      )}
                      Load more
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <p className="text-[11px] text-muted-foreground italic">
                No faces assigned to this person yet.
              </p>
            )}
          </Section>

          {/* Files this person is mentioned in */}
          {profile && (
            <Section
              title="Recent Files"
              icon={<FileText size={14} className="text-primary" />}
            >
              <EntityMentionsByFile
                entityId={id}
                emptyLabel="Not mentioned in any files yet."
              />
            </Section>
          )}

          {/* Selectors tied to this person */}
          {selectors.length > 0 && (
            <Section
              title="Selectors"
              icon={<Fingerprint size={14} className="text-primary" />}
            >
              <ul className="flex flex-wrap gap-2">
                {selectors.map((s) => (
                  <li key={s.id}>
                    <Link
                      href={`/entities/${s.id}`}
                      className={`rounded-lg border px-2.5 py-1.5 font-mono text-xs hover:brightness-125 ${ENTITY_TYPE_META.selector.borderClass} ${ENTITY_TYPE_META.selector.bgClass} ${ENTITY_TYPE_META.selector.textClass}`}
                    >
                      {s.displayName}
                    </Link>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Entity connections */}
          {related.length > 0 && (
            <Section
              title="Connections"
              icon={<Network size={14} className="text-primary" />}
            >
              <ul className="mb-4 flex flex-wrap gap-2">
                {related.map((r, i) => {
                  const m = ENTITY_TYPE_META[r.entity.entityType];
                  return (
                    <li key={`${r.entity.id}-${i}`}>
                      <Link
                        href={`/entities/${r.entity.id}`}
                        className="flex items-center gap-1.5 rounded-lg border border-border bg-muted/40 px-2.5 py-1.5 text-xs hover:border-primary/40"
                      >
                        <m.Icon size={12} className={m.textClass} />
                        <span className="font-medium text-foreground">
                          {r.entity.displayName}
                        </span>
                        <span className="text-[10px] uppercase text-muted-foreground">
                          {r.direction === "out" ? "" : "← "}
                          {r.relationshipType.replace(/_/g, " ")}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
              <EntityGraph focusEntityId={id} depth={1} compact />
            </Section>
          )}
        </div>

        {/* Side column */}
        <div className="flex flex-col gap-6">
          <div className="rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-5 h-fit">
            <h2 className="mb-3 text-[10px] font-black uppercase tracking-widest text-foreground">
              Overview
            </h2>
            <dl className="space-y-1.5">
              <Stat label="Faces" value={recentFaces.length} />
              <Stat label="Mentions" value={totalMentions} />
              <Stat label="Selectors" value={selectors.length} />
              <Stat label="Connections" value={related.length} />
              <Stat label="Source" value={person.source.replace(/_/g, " ")} />
              {person.sex && <Stat label="Sex" value={person.sex} />}
              {person.dateOfBirth && (
                <Stat
                  label="Date of birth"
                  value={new Date(person.dateOfBirth).toLocaleDateString()}
                />
              )}
            </dl>
          </div>

          <div className="rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-5 h-fit">
            <CommentSection commentableType="person" commentableId={id} />
          </div>
        </div>
      </div>

      <EditPersonDialog
        person={person}
        isOpen={isEditOpen}
        onOpenChange={setIsEditOpen}
      />

      {selectedFace && selectedIndex >= 0 && (
        <FaceDetailDialog
          face={allFacesForNav[selectedIndex]}
          isOpen={!!selectedFace}
          onOpenChange={(open) => !open && setSelectedFace(null)}
          onNext={() =>
            setSelectedFace(
              allFacesForNav[
                Math.min(selectedIndex + 1, allFacesForNav.length - 1)
              ]
            )
          }
          onPrev={() =>
            setSelectedFace(allFacesForNav[Math.max(selectedIndex - 1, 0)])
          }
          hasMore={selectedIndex < allFacesForNav.length - 1}
          hasPrev={selectedIndex > 0}
          onFindSimilar={(faceId) => router.push(`/faces?similar=${faceId}`)}
        />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-xs">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium capitalize text-foreground">{value}</dd>
    </div>
  );
}
