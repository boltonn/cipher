"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CommentSection } from "@/features/comments/components/comment-section";
import { FaceCard } from "@/features/faces/components/face-card";
import { FaceDetailDialog } from "@/features/faces/components/face-detail-dialog";
import { usePersonFaces } from "@/features/faces/hooks/use-person-faces";
import { FacePublic } from "@/features/faces/types";
import { EditPersonDialog } from "@/features/persons/components/edit-person-dialog";
import { PersonExampleUploadButton } from "@/features/persons/components/person-example-upload-button";
import { PersonExamplesGallery } from "@/features/persons/components/person-examples-gallery";
import { usePerson, usePersonRepresentativeFaces } from "@/features/persons/hooks/use-persons";
import {
  BadgeCheck,
  Cake,
  ImagePlus,
  Loader2,
  Pencil,
  ScanFace,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { use, useMemo, useState } from "react";

export default function PersonDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  const { data: person, isPending } = usePerson(id);
  const { data: representativeFaces, isPending: repPending } = usePersonRepresentativeFaces(id);
  const {
    data: facesData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isPending: facesPending,
  } = usePersonFaces(id);

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [selectedFace, setSelectedFace] = useState<FacePublic | null>(null);

  const recentFaces = useMemo(() => facesData?.pages.flatMap((p) => p.data) ?? [], [facesData]);
  const allFacesForNav = recentFaces;
  const selectedIndex = selectedFace ? allFacesForNav.findIndex((f) => f.id === selectedFace.id) : -1;

  if (isPending || !person) {
    return (
      <div className="flex items-center justify-center py-48 text-slate-500">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500/40" />
      </div>
    );
  }

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20">
      <PageHeader eyebrow="Person" value={`${recentFaces.length} faces`} />

      {/* Identity header */}
      <div className="mt-4 rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6 flex flex-col gap-4">
        <div className="flex items-start gap-6">
          <PersonExamplesGallery personId={id} faces={representativeFaces ?? []} isPending={repPending} />

          <div className="flex-1 min-w-0 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2.5">
                  <h1 className="text-xl font-bold text-white">{person.name || "Unnamed Person"}</h1>
                  {person.isVerified && (
                    <Badge className="h-6 bg-indigo-500/10 text-indigo-400 border-none gap-1.5 text-xs px-2.5">
                      <BadgeCheck size={14} /> Verified
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-5 mt-2 text-sm text-slate-400">
                  {person.sex && <span className="capitalize">{person.sex}</span>}
                  {person.dateOfBirth && (
                    <span className="flex items-center gap-1.5">
                      <Cake size={14} />
                      {new Date(person.dateOfBirth).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <PersonExampleUploadButton
                  personId={id}
                  atCap={(representativeFaces?.length ?? 0) >= 10}
                  className="flex items-center gap-2 border border-white/5 bg-slate-900/40 rounded-md text-slate-400 hover:text-annotation hover:border-annotation/30 uppercase text-[10px] font-bold tracking-widest h-9 px-3 disabled:opacity-30 disabled:pointer-events-none transition-colors"
                >
                  <ImagePlus size={14} />
                  Upload Exemplar
                </PersonExampleUploadButton>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsEditOpen(true)}
                  className="border-white/5 bg-slate-900/40 text-slate-400 hover:text-indigo-400 uppercase text-[10px] font-bold tracking-widest gap-2 h-9"
                >
                  <Pencil size={14} />
                  Edit
                </Button>
              </div>
            </div>

            {person.notes && <p className="text-sm text-slate-300 leading-relaxed">{person.notes}</p>}

            {person.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {person.tags.map((tag) => (
                  <Badge
                    key={tag}
                    variant="outline"
                    className="h-7 text-sm px-3 bg-slate-900/40 border-white/10 text-slate-300"
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
          <section>
            <div className="flex items-center gap-2 mb-3">
              <ScanFace size={14} className="text-indigo-500" />
              <h2 className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
                Recent Faces
              </h2>
            </div>
            {facesPending ? (
              <Loader2 size={16} className="animate-spin text-slate-600" />
            ) : recentFaces.length ? (
              <>
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                  {recentFaces.map((face) => (
                    <FaceCard
                      key={face.id}
                      face={face}
                      onExpand={setSelectedFace}
                      onFindSimilar={(faceId) => router.push(`/faces?similar=${faceId}`)}
                    />
                  ))}
                </div>
                {hasNextPage && (
                  <div className="flex justify-center mt-4">
                    <Button
                      variant="ghost"
                      onClick={() => fetchNextPage()}
                      disabled={isFetchingNextPage}
                      className="text-[10px] uppercase tracking-widest text-indigo-400"
                    >
                      {isFetchingNextPage && <Loader2 size={12} className="animate-spin mr-2" />}
                      Load more
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <p className="text-[11px] text-slate-600 italic">No faces assigned to this person yet.</p>
            )}
          </section>
        </div>

        {/* Comments */}
        <div className="rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-5 h-fit">
          <CommentSection commentableType="person" commentableId={id} />
        </div>
      </div>

      <EditPersonDialog person={person} isOpen={isEditOpen} onOpenChange={setIsEditOpen} />

      {selectedFace && selectedIndex >= 0 && (
        <FaceDetailDialog
          face={allFacesForNav[selectedIndex]}
          isOpen={!!selectedFace}
          onOpenChange={(open) => !open && setSelectedFace(null)}
          onNext={() => setSelectedFace(allFacesForNav[Math.min(selectedIndex + 1, allFacesForNav.length - 1)])}
          onPrev={() => setSelectedFace(allFacesForNav[Math.max(selectedIndex - 1, 0)])}
          hasMore={selectedIndex < allFacesForNav.length - 1}
          hasPrev={selectedIndex > 0}
          onFindSimilar={(faceId) => router.push(`/faces?similar=${faceId}`)}
        />
      )}
    </div>
  );
}
