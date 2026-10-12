"use client";

import { EmptyState } from "@/components/empty-state";
import { PageLoading } from "@/components/page-loading";
import { useDatasetProfile } from "@/features/datasets/api";
import type { ProfileEntity } from "@/features/datasets/types";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ArrowRight, Clock, Compass, Filter, History } from "lucide-react";
import Link from "next/link";
import { useSearchHistory } from "../api";
import type { OverviewFilters } from "../types";
import { DatasetBriefCard } from "./dataset-brief-card";
import { ImageThumb } from "./image-thumb";
import { TimeHistogram } from "./time-histogram";

interface BriefingProps {
  datasetIds: string[];
  /** Run a search with these filters and no query (e.g. files mentioning a person). */
  onFilter: (filters: Partial<OverviewFilters>) => void;
  onSearch: (query: string) => void;
  onOpenImage: (imageId: string) => void;
}

function Section({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={className}>
      <h2 className="mb-2 text-xs font-medium text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}

/** Each name opens its entity page; the filter button narrows the search to files mentioning it. */
function RankedList({ entities, onFilter }: { entities: ProfileEntity[]; onFilter: (entity: ProfileEntity) => void }) {
  if (entities.length === 0) return <p className="text-sm text-muted-foreground">None found yet.</p>;
  const peak = entities[0].files;
  return (
    <ol className="space-y-0.5">
      {entities.map((entity) => (
        <li key={entity.entityId} className="group relative flex items-center overflow-hidden rounded-md hover:bg-muted">
          <span
            aria-hidden
            className="absolute inset-y-1 left-0 rounded-r-[4px] bg-primary/10 group-hover:bg-primary/15"
            style={{ width: `${(entity.files / peak) * 100}%` }}
          />
          <Link
            href={`/entities/${entity.entityId}`}
            className="relative flex min-w-0 flex-1 items-center gap-2 px-2 py-1 text-sm"
          >
            <span className="min-w-0 flex-1 truncate text-foreground group-hover:underline">{entity.displayName}</span>
            <span className="text-xs text-muted-foreground">{entity.files.toLocaleString()}</span>
          </Link>
          <button
            type="button"
            onClick={() => onFilter(entity)}
            aria-label={`Search files mentioning ${entity.displayName}`}
            title="Search files mentioning this"
            className="relative mr-1 grid size-6 shrink-0 place-items-center rounded text-muted-foreground opacity-0 hover:bg-background hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
          >
            <Filter className="size-3.5" />
          </button>
        </li>
      ))}
    </ol>
  );
}

/** The empty-query view: what the selected datasets contain, every item a way in. */
export function Briefing({ datasetIds, onFilter, onSearch, onOpenImage }: BriefingProps) {
  const { data: profile, isPending } = useDatasetProfile(datasetIds);
  const { data: history } = useSearchHistory(6);

  if (isPending) return <PageLoading />;
  if (!profile || profile.fileCount === 0) {
    return (
      <EmptyState
        icon={Compass}
        title="Nothing profiled yet"
        body={
          profile?.unprofiledDatasetIds.length
            ? "Run `cipher profile-dataset --all` to build the overview. You can still search above."
            : "These datasets have no files yet."
        }
      />
    );
  }

  const groups = Object.entries(profile.filetypeGroupCounts);
  const pickEntity = (entity: ProfileEntity) => onFilter({ entityIds: [entity.entityId] });

  return (
    <div className="space-y-6">
      {profile.unprofiledDatasetIds.length > 0 && (
        <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          {profile.unprofiledDatasetIds.length} selected dataset
          {profile.unprofiledDatasetIds.length === 1 ? " isn't" : "s aren't"} in this overview yet — run{" "}
          <code>cipher profile-dataset</code>.
        </p>
      )}

      <DatasetBriefCard datasetIds={datasetIds} onSearch={onSearch} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Section title="What's here" className="lg:col-span-1">
          <p className="text-2xl font-semibold text-foreground">{profile.fileCount.toLocaleString()} files</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {groups.map(([group, count]) => (
              <button
                key={group}
                type="button"
                onClick={() => onFilter({ filetypeGroups: [group] })}
                className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-muted/60 px-2.5 text-xs hover:bg-muted"
              >
                <span className="text-foreground">{group}</span>
                <span className="text-muted-foreground">{count.toLocaleString()}</span>
              </button>
            ))}
          </div>
        </Section>
        <Section title="When (by date sent or written) — click a bar to narrow" className="lg:col-span-2">
          <TimeHistogram
            months={profile.dateHistogram}
            onSelect={(bin) => onFilter({ dateFrom: bin.dateFrom, dateTo: bin.dateTo })}
          />
        </Section>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
        <Section title="People & organizations (files mentioning, newsletters excluded)">
          <RankedList entities={profile.topPeopleOrgs.slice(0, 12)} onFilter={pickEntity} />
        </Section>
        <Section title="Email addresses, phones & other identifiers">
          <RankedList entities={profile.topSelectors.slice(0, 12)} onFilter={pickEntity} />
        </Section>
        <Section title="Places">
          <RankedList entities={profile.topPlaces.slice(0, 12)} onFilter={pickEntity} />
        </Section>
        <Section title="Who emails whom">
          {profile.topCorrespondents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No email traffic found.</p>
          ) : (
            <ol className="space-y-0.5">
              {profile.topCorrespondents.slice(0, 10).map((edge) => (
                <li key={`${edge.srcEntityId}-${edge.dstEntityId}`}>
                  <button
                    type="button"
                    onClick={() => onFilter({ entityIds: [edge.srcEntityId, edge.dstEntityId] })}
                    className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm hover:bg-muted"
                  >
                    <span className="min-w-0 truncate text-foreground">{edge.srcName}</span>
                    <ArrowRight className="size-3 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate text-foreground">{edge.dstName}</span>
                    <span className="text-xs text-muted-foreground">{edge.emails.toLocaleString()}</span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </Section>
      </div>

      {profile.imageSampleIds.length > 0 && (
        <Section title="A spread of the images — click one for similar images">
          <div className="grid grid-cols-6 gap-2 sm:grid-cols-8 lg:grid-cols-12">
            {profile.imageSampleIds.map((imageId) => (
              <ImageThumb key={imageId} imageId={imageId} onOpen={() => onOpenImage(imageId)} />
            ))}
          </div>
        </Section>
      )}

      {!!history?.data.length && (
        <Section title="Your recent searches">
          <div className="flex flex-wrap gap-1.5">
            {history.data.map((record) => (
              <Link
                key={record.id}
                href={`/search/${record.id}`}
                className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-muted/60 px-2.5 text-xs text-foreground hover:bg-muted"
              >
                <History className="size-3.5 text-muted-foreground" />
                {record.query || "Filtered browse"}
                <span className="text-muted-foreground">
                  <Clock className="mr-0.5 inline size-3" />
                  {formatDistanceToNow(parseISO(record.dateLastRun), { addSuffix: true })}
                </span>
              </Link>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
