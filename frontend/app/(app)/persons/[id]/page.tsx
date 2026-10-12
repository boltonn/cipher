"use client";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CommentSection } from "@/features/comments/components/comment-section";
import { AddConnectionDialog } from "@/features/entities/components/add-connection-dialog";
import { AttachSelectorDialog } from "@/features/entities/components/attach-selector-dialog";
import { EntityGraph } from "@/features/entities/components/entity-graph";
import { EntityMergePanel } from "@/features/entities/components/entity-merge-list";
import { EntityNamesPanel } from "@/features/entities/components/entity-names-panel";
import { EntitySelectorProposals } from "@/features/entities/components/entity-selector-proposals";
import { EntitySelectors } from "@/features/entities/components/entity-selectors";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { Section } from "@/features/entities/components/section";
import { useEntityProfile } from "@/features/entities/hooks/use-entities";
import { FAMILY_ROLE_INVERSE } from "@/features/entities/types";
import { PersonEventsSection } from "@/features/events/components/person-events-section";
import {
  EAGER_FACE_COUNT,
  FaceCard,
} from "@/features/faces/components/face-card";
import { FaceSelectionBar } from "@/features/faces/components/face-selection-bar";
import { useUnassignFaces } from "@/features/faces/hooks/use-assign-face";
import { useGridSelection } from "@/hooks/use-grid-selection";
import { usePersonFaces } from "@/features/faces/hooks/use-person-faces";
import { useRejectFaces } from "@/features/faces/hooks/use-reject-faces";
import { ImageViewerDialog } from "@/features/images/components/image-viewer-dialog";
import { FacePublic } from "@/features/faces/types";
import type { PersonSourceType } from "@/features/persons/types";
import { EditPersonDialog } from "@/features/persons/components/edit-person-dialog";
import { MergePersonDialog } from "@/features/persons/components/merge-person-dialog";
import { PersonExamplesGallery } from "@/features/persons/components/person-examples-gallery";
import {
  useDeletePerson,
  usePerson,
  usePersonRepresentativeFaces,
} from "@/features/persons/hooks/use-persons";
import {
  BadgeCheck,
  Cake,
  Ellipsis,
  FileText,
  Fingerprint,
  Loader2,
  type LucideIcon,
  Merge,
  Network,
  Pencil,
  Plus,
  ScanFace,
  Search,
  Share2,
  Tags,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useMemo, useState } from "react";
import { humanize } from "@/lib/utils";

const SOURCE_LABELS: Record<PersonSourceType, string> = {
  manual: "Added manually",
  faceClustering: "From face clustering",
};

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

  const deletePerson = useDeletePerson(() => router.replace("/persons"));

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isMergeOpen, setIsMergeOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isAddSelectorOpen, setIsAddSelectorOpen] = useState(false);
  const [isAddConnectionOpen, setIsAddConnectionOpen] = useState(false);
  const [showConnGraph, setShowConnGraph] = useState(true);
  const [selectedFace, setSelectedFace] = useState<FacePublic | null>(null);

  const recentFaces = useMemo(
    () => facesData?.pages.flatMap((p) => p.data) ?? [],
    [facesData]
  );
  const selectedIndex = selectedFace
    ? recentFaces.findIndex((f) => f.id === selectedFace.id)
    : -1;

  const faceSelection = useGridSelection();
  const unassignFaces = useUnassignFaces(faceSelection.clear);
  const rejectFaces = useRejectFaces();
  const recentFaceIds = useMemo(
    () => recentFaces.map((f) => f.id),
    [recentFaces]
  );

  const selectors = profile?.selectors ?? [];
  const related = profile?.relatedEntities ?? [];
  const fileCount = profile?.fileCount ?? 0;

  if (isPending || !person) {
    return <PageLoading icon={ScanFace} label="Loading person…" />;
  }

  const displayName = person.name || "Unnamed person";
  const searchHref = `/search/text?entityId=${id}`;

  const stats: {
    label: string;
    value: number;
    href?: string;
    Icon: LucideIcon;
  }[] = [
    {
      label: "Faces",
      value: recentFaces.length,
      href: "#faces",
      Icon: ScanFace,
    },
    {
      label: "Files",
      value: fileCount,
      href: searchHref,
      Icon: FileText,
    },
    {
      label: "Selectors",
      value: selectors.length,
      href: "#selectors",
      Icon: Fingerprint,
    },
    {
      label: "Connections",
      value: related.length,
      href: "#connections",
      Icon: Network,
    },
  ];

  return (
    <div className="relative mx-auto max-w-400 px-6 pb-24 pt-5">
      <PageHeader
        eyebrow="Person"
        value={
          fileCount
            ? `${recentFaces.length} faces · named in ${fileCount.toLocaleString()} file${fileCount === 1 ? "" : "s"}`
            : `${recentFaces.length} faces`
        }
        actions={
          <>
            <Button asChild variant="outline" className="h-9 gap-2 text-xs">
              <Link href={searchHref}>
                <Search size={14} />
                Find in text
              </Link>
            </Button>
            <Button
              variant="outline"
              onClick={() => setIsEditOpen(true)}
              className="h-9 gap-2 text-xs"
            >
              <Pencil size={14} />
              Edit
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="More actions"
                  className="h-9 w-9"
                >
                  <Ellipsis size={14} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuItem
                  onSelect={() => setIsMergeOpen(true)}
                  className="items-start"
                >
                  <Merge size={14} className="mt-0.5" />
                  <div>
                    <div>Merge with another person</div>
                    <div className="text-[11px] text-muted-foreground">
                      Same person recorded twice — combine faces, names and
                      links into one
                    </div>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={() => setIsDeleteOpen(true)}
                >
                  <Trash2 size={14} />
                  Delete person
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      <div className="w-full max-w-5xl">
        {/* Identity header */}
        <div className="flex flex-col gap-4 rounded-2xl border border-border bg-muted/40 p-6 backdrop-blur-2xl">
          <div className="flex items-start gap-6">
            <PersonExamplesGallery
              personId={id}
              faces={representativeFaces ?? []}
              isPending={repPending}
            />

            <div className="flex min-w-0 flex-1 flex-col gap-3">
              <div>
                <h1 className="text-2xl font-bold leading-tight text-foreground [overflow-wrap:anywhere]">
                  {displayName}
                </h1>
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted-foreground">
                  {person.isVerified && (
                    <Badge className="h-6 gap-1.5 border-none bg-primary/10 px-2.5 text-xs text-primary">
                      <BadgeCheck size={14} /> Verified
                    </Badge>
                  )}
                  {person.sex && (
                    <span className="capitalize">{person.sex}</span>
                  )}
                  {person.dateOfBirth && (
                    <span className="flex items-center gap-1.5">
                      <Cake size={14} />
                      {new Date(person.dateOfBirth).toLocaleDateString()}
                    </span>
                  )}
                  <span>{SOURCE_LABELS[person.source]}</span>
                </div>
                {person.aliases.length > 0 && (
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    Also known as {person.aliases.join(", ")}
                  </p>
                )}
              </div>

              {person.notes && (
                <p className="text-sm leading-relaxed text-foreground">
                  {person.notes}
                </p>
              )}

              {person.tags.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {person.tags.map((tag) => (
                    <Badge
                      key={tag}
                      variant="outline"
                      className="h-7 border-border bg-muted/40 px-3 text-sm text-foreground"
                    >
                      #{tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Count strip */}
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-4">
            {stats.map((s) => {
              const body = (
                <>
                  <s.Icon
                    size={18}
                    className="shrink-0 text-primary/60 transition-colors group-hover:text-primary"
                  />
                  <div className="min-w-0">
                    <div className="text-lg font-semibold text-foreground">
                      {s.value}
                    </div>
                    <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground transition-colors group-hover:text-primary">
                      {s.label}
                    </div>
                  </div>
                </>
              );
              return s.href ? (
                <a
                  key={s.label}
                  href={s.href}
                  className="group flex items-center gap-3 bg-card px-4 py-3 transition-colors hover:bg-primary/5"
                >
                  {body}
                </a>
              ) : (
                <div
                  key={s.label}
                  className="group flex items-center gap-3 bg-card px-4 py-3"
                >
                  {body}
                </div>
              );
            })}
          </div>
        </div>

        {/* Stacked sections */}
        <div className="mt-8 flex flex-col gap-10">
          {profile && <EntityMergePanel entity={profile.entity} />}
          <EntitySelectorProposals entityId={id} entityName={displayName} />

          <Section
            id="selectors"
            title="Selectors"
            icon={<Fingerprint size={14} className="text-primary" />}
            action={
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsAddSelectorOpen(true)}
                className="h-7 gap-1.5 text-xs font-medium text-primary hover:text-primary"
              >
                <Plus size={13} />
                Add
              </Button>
            }
          >
            <EntitySelectors
              entityId={id}
              selectors={selectors}
              selectorMentions={profile?.selectorMentions ?? []}
              showMentionPreviews={false}
            />
          </Section>

          <Section
            id="faces"
            title="Faces"
            icon={<ScanFace size={14} className="text-primary" />}
          >
            {facesPending ? (
              <Loader2
                size={16}
                className="animate-spin text-muted-foreground"
              />
            ) : recentFaces.length ? (
              <>
                <div className="grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-6">
                  {recentFaces.map((face, index) => (
                    <FaceCard
                      key={face.id}
                      face={face}
                      isEager={index < EAGER_FACE_COUNT}
                      onExpand={setSelectedFace}
                      onFindSimilar={(faceId) =>
                        router.push(`/faces?similar=${faceId}`)
                      }
                      onReject={(f) => rejectFaces.mutate([f.id])}
                      isSelected={faceSelection.selectedIds.has(face.id)}
                      isSelectionActive={faceSelection.selectedIds.size > 0}
                      onToggleSelect={(f, range) =>
                        faceSelection.toggle(f.id, recentFaceIds, range)
                      }
                    />
                  ))}
                </div>
                <FaceSelectionBar
                  selection={faceSelection}
                  loadedIds={recentFaceIds}
                  onUnassign={unassignFaces.mutate}
                  isUnassigning={unassignFaces.isPending}
                />
                {hasNextPage && (
                  <div className="mt-4 flex justify-center">
                    <Button
                      variant="ghost"
                      onClick={() => fetchNextPage()}
                      disabled={isFetchingNextPage}
                      className="text-xs text-primary"
                    >
                      {isFetchingNextPage && (
                        <Loader2 size={12} className="mr-2 animate-spin" />
                      )}
                      Load more
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <p className="text-[11px] italic text-muted-foreground">
                No faces assigned to this person yet.
              </p>
            )}
          </Section>

          <PersonEventsSection entityId={id} />

          <Section
            id="connections"
            title="Connections"
            icon={<Network size={14} className="text-primary" />}
            action={
              <div className="flex items-center gap-1">
                {related.length > 0 && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowConnGraph((v) => !v)}
                      className="h-7 gap-1.5 text-xs font-medium text-muted-foreground hover:text-primary"
                    >
                      <Network size={13} />
                      {showConnGraph ? "Hide graph" : "Show graph"}
                    </Button>
                    <Button
                      asChild
                      variant="ghost"
                      size="sm"
                      className="h-7 gap-1.5 text-xs font-medium text-muted-foreground hover:text-primary"
                    >
                      <Link href={`/graph?seed=${id}`}>
                        <Share2 size={13} />
                        Open in graph
                      </Link>
                    </Button>
                  </>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsAddConnectionOpen(true)}
                  className="h-7 gap-1.5 text-xs font-medium text-primary hover:text-primary"
                >
                  <Plus size={13} />
                  Add
                </Button>
              </div>
            }
          >
            {related.length > 0 ? (
              <>
                <ul className="mb-4 flex flex-wrap gap-2">
                  {related.map((r, i) => {
                    const m = ENTITY_TYPE_META[r.entity.entityType];
                    const rawRole =
                      typeof r.attributes?.role === "string"
                        ? r.attributes.role
                        : null;
                    // The stored role is "source is <role> of target"; on an
                    // incoming edge show the inverse so it reads from here.
                    const role = rawRole
                      ? r.direction === "in"
                        ? (FAMILY_ROLE_INVERSE[rawRole] ?? rawRole)
                        : rawRole
                      : null;
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
                          <span className="text-[11px] uppercase text-muted-foreground">
                            {role ?? humanize(r.relationshipType)}
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
                {showConnGraph && (
                  <EntityGraph focusEntityId={id} depth={2} compact />
                )}
              </>
            ) : (
              <p className="text-[11px] italic text-muted-foreground">
                No connections yet. Link this person to family, associates, or
                other entities.
              </p>
            )}
          </Section>

          {profile && (
            <Section
              id="names"
              title="Names in the evidence"
              icon={<Tags size={14} className="text-primary" />}
            >
              <EntityNamesPanel entity={profile.entity} />
            </Section>
          )}

          {/* CommentSection renders its own "Comments" header -- no Section
            wrapper, or the heading shows twice. */}
          <section id="comments" className="scroll-mt-20">
            <div className="rounded-2xl border border-border bg-muted/40 p-5 backdrop-blur-2xl">
              <CommentSection commentableType="entity" commentableId={id} />
            </div>
          </section>
        </div>
      </div>

      <EditPersonDialog
        person={person}
        isOpen={isEditOpen}
        onOpenChange={setIsEditOpen}
      />

      <ConfirmDialog
        open={isDeleteOpen}
        onOpenChange={setIsDeleteOpen}
        title="Delete this person?"
        description={
          <>
            This permanently deletes{" "}
            <strong className="text-foreground">{displayName}</strong> and
            their entry in the knowledge graph. Their{" "}
            {recentFaces.length.toLocaleString()} face
            {recentFaces.length === 1 ? "" : "s"} are unlinked, not deleted,
            and can be reassigned to someone else; mentions naming them become
            unresolved. Their {(profile?.relatedTotal ?? 0).toLocaleString()}{" "}
            relationship{(profile?.relatedTotal ?? 0) === 1 ? "" : "s"},
            pending face/resolution matches, and comments are deleted outright.
            This can&apos;t be undone.
          </>
        }
        confirmLabel="Delete person"
        isPending={deletePerson.isPending}
        onConfirm={() => deletePerson.mutate(id)}
      />

      <MergePersonDialog
        person={person}
        isOpen={isMergeOpen}
        onOpenChange={setIsMergeOpen}
        onMerged={(keptId) => {
          if (keptId !== id) router.replace(`/persons/${keptId}`);
        }}
      />

      <AttachSelectorDialog
        entityId={id}
        entityLabel={displayName}
        isOpen={isAddSelectorOpen}
        onOpenChange={setIsAddSelectorOpen}
      />

      <AddConnectionDialog
        entityId={id}
        entityLabel={displayName}
        isOpen={isAddConnectionOpen}
        onOpenChange={setIsAddConnectionOpen}
      />

      {selectedFace && selectedIndex >= 0 && (
        <ImageViewerDialog
          imageId={recentFaces[selectedIndex].imageId}
          focusFaceId={recentFaces[selectedIndex].id}
          isOpen={!!selectedFace}
          onOpenChange={(open) => !open && setSelectedFace(null)}
          onNext={() =>
            setSelectedFace(
              recentFaces[Math.min(selectedIndex + 1, recentFaces.length - 1)]
            )
          }
          onPrev={() =>
            setSelectedFace(recentFaces[Math.max(selectedIndex - 1, 0)])
          }
          hasMore={selectedIndex < recentFaces.length - 1}
          hasPrev={selectedIndex > 0}
          onFindSimilarFace={(faceId) =>
            router.push(`/faces?similar=${faceId}`)
          }
        />
      )}
    </div>
  );
}
