"use client";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { CopyableId } from "@/components/copyable-id";
import { DatePicker } from "@/components/date-picker";
import { ProvenanceTagsInput } from "@/features/tags/components/provenance-tags-input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EntityPicker } from "@/features/entities/components/entity-picker";
import { FileViewer } from "@/features/files/components/file-viewer";
import {
  useAddParticipant,
  useAddPlace,
  useDeleteEvent,
  useEvent,
  useEventTagOptions,
  useRemoveParticipant,
  useRemovePlace,
  useUpdateEvent,
} from "@/features/events/api";
import { useDebounce } from "@/hooks/use-debounce";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";
import {
  EVENT_STATUS_LABELS,
  EVENT_TYPE_META,
  categoryMeta,
} from "@/features/events/components/event-type-meta";
import { buildDetails, detailFieldsFor, detailsToFormValues } from "@/features/events/lib/details";
import { formatDateRange, formatEventStart } from "@/features/events/lib/format";
import {
  EVENT_STATUSES,
  EVENT_TYPES,
  type EventParticipant,
  type EventPlace,
  type EventType,
  type EventUpdatePayload,
  type EventWithLinks,
  type ParticipantRole,
  type PlaceRole,
} from "@/features/events/types";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import {
  BadgeCheck,
  CalendarClock,
  FileText,
  Info,
  Loader2,
  Lock,
  MapPin,
  PanelRight,
  Pencil,
  Plus,
  Repeat,
  Sparkles,
  Trash2,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

interface EventDetailSheetProps {
  eventId: string | null;
  onOpenChange: (open: boolean) => void;
}

const HIDDEN_DETAIL_KEYS = new Set(["kind"]);
const DATE_PRECISIONS = ["exact", "day", "month", "year", "approximate"] as const;
const PARTICIPANT_ROLES: ParticipantRole[] = [
  "attendee",
  "organizer",
  "host",
  "guest",
  "traveler",
];
const PLACE_ROLES: PlaceRole[] = ["venue", "origin", "destination"];
const NONE = "__none__";

export function EventDetailSheet({ eventId, onOpenChange }: EventDetailSheetProps) {
  const { data: event, isPending } = useEvent(eventId ?? undefined);

  const [editing, setEditing] = useState(false);
  const [showSource, setShowSource] = useLocalStorageState<boolean>("events:showSource", false);
  // Leave edit mode whenever a different event is opened (adjust-state-during-render).
  const [prevId, setPrevId] = useState(eventId);
  if (eventId !== prevId) {
    setPrevId(eventId);
    setEditing(false);
  }

  const hasFile = !!event?.fileId;
  const sourceOpen = showSource && hasFile;

  const panel =
    isPending || !event ? (
      <div className="space-y-4 p-6">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-24 w-full" />
      </div>
    ) : editing ? (
      <EventEditForm
        event={event}
        onClose={() => setEditing(false)}
        hasFile={hasFile}
        sourceOpen={sourceOpen}
        onToggleSource={() => setShowSource((v) => !v)}
      />
    ) : (
      <EventReadView
        event={event}
        onEdit={() => setEditing(true)}
        onInvalid={() => onOpenChange(false)}
        hasFile={hasFile}
        sourceOpen={sourceOpen}
        onToggleSource={() => setShowSource((v) => !v)}
      />
    );

  return (
    <Sheet open={!!eventId} onOpenChange={onOpenChange}>
      <SheetContent
        className={cn(
          "gap-0 overflow-hidden p-0",
          // shadcn caps the right sheet at `data-[side=right]:sm:max-w-sm`; override
          // with the same variant prefix so tailwind-merge actually wins.
          sourceOpen
            ? "data-[side=right]:w-[92vw] data-[side=right]:sm:max-w-6xl"
            : "data-[side=right]:sm:max-w-md"
        )}
      >
        {sourceOpen && event?.fileId ? (
          <div className="flex h-full">
            <div className="min-w-0 flex-1">
              <FileViewer fileId={event.fileId} className="h-full" />
            </div>
            <div className="w-[27rem] shrink-0 overflow-y-auto border-l border-border">{panel}</div>
          </div>
        ) : (
          <div className="h-full overflow-y-auto">{panel}</div>
        )}
      </SheetContent>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ read view */

function EventReadView({
  event,
  onEdit,
  onInvalid,
  hasFile,
  sourceOpen,
  onToggleSource,
}: {
  event: EventWithLinks;
  onEdit: () => void;
  onInvalid: () => void;
  hasFile: boolean;
  sourceOpen: boolean;
  onToggleSource: () => void;
}) {
  const update = useUpdateEvent(event.id);
  const markInvalid = useDeleteEvent(onInvalid);
  return (
    <>
      <SheetHeader className="gap-2 pr-10">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <TypeBadge eventType={event.eventType} category={event.category} />
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {EVENT_STATUS_LABELS[event.status]}
          </span>
          {event.isVerified ? (
            <span className="flex items-center gap-1 text-[11px] text-primary">
              <BadgeCheck size={12} /> Verified
            </span>
          ) : event.extractor === "llm" ? (
            <span
              className="flex items-center gap-1 text-[11px] text-annotation"
              title={event.extractionModel ?? "LLM-extracted"}
            >
              <Sparkles size={12} /> AI-extracted
            </span>
          ) : null}
        </div>
        <div className="flex w-fit gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1 px-2 text-xs text-muted-foreground"
            onClick={onEdit}
          >
            <Pencil size={12} /> Edit
          </Button>
          <SourceToggle hasFile={hasFile} sourceOpen={sourceOpen} onToggle={onToggleSource} />
        </div>
        <SheetTitle
          className={cn("text-lg leading-tight", event.status === "cancelled" && "line-through opacity-60")}
        >
          {event.title}
        </SheetTitle>
        <SheetDescription className="flex items-center gap-1.5">
          <CalendarClock size={13} />
          {formatEventStart(event)}
          {formatDateRange(event) && (
            <span className="text-muted-foreground">· {formatDateRange(event)}</span>
          )}
          {event.timezone && <span className="text-muted-foreground/70">({event.timezone})</span>}
          {event.recurrenceRule && (
            <span className="flex items-center gap-1 text-muted-foreground/70" title={event.recurrenceRule}>
              <Repeat size={12} /> Recurring
            </span>
          )}
        </SheetDescription>
      </SheetHeader>

      <div className="space-y-6 px-6 py-5">
        {event.summary && (
          <p className="pb-1 text-sm leading-relaxed text-foreground/90">{event.summary}</p>
        )}

        {event.places.length > 0 && (
          <DetailBlock icon={<MapPin size={13} />} title="Places">
            <ul className="space-y-1.5">
              {event.places.map((p) => (
                <PlaceRow key={p.id} place={p} />
              ))}
            </ul>
          </DetailBlock>
        )}

        {event.participants.length > 0 && (
          <DetailBlock icon={<Users size={13} />} title="People">
            <ul className="space-y-1.5">
              {event.participants.map((p) => (
                <ParticipantRow key={p.id} participant={p} />
              ))}
            </ul>
          </DetailBlock>
        )}

        {event.details && <TypedDetails details={event.details} />}

        {event.categories.length > 0 && (
          <div className="flex flex-wrap gap-1" title="Source labels (iCalendar CATEGORIES)">
            {event.categories.map((c) => (
              <Badge
                key={c}
                variant="outline"
                className="h-5 border-border/60 bg-transparent px-1.5 text-[11px] font-normal text-muted-foreground"
              >
                {c}
              </Badge>
            ))}
          </div>
        )}

        {event.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {event.tags.map((t) => (
              <Badge
                key={t}
                variant="outline"
                className="h-5 border-border bg-muted/40 px-1.5 text-[11px] text-muted-foreground"
              >
                #{t}
              </Badge>
            ))}
          </div>
        )}

        {event.notes && (
          <DetailBlock title="Notes">
            <p className="text-xs leading-relaxed text-muted-foreground">{event.notes}</p>
          </DetailBlock>
        )}

        <div className="flex flex-col gap-2 border-t border-border pt-4 text-[11px] text-muted-foreground">
          {event.fileId && (
            <div className="flex items-center gap-2">
              <span className="uppercase tracking-wide">Source file</span>
              <Link
                href={`/files/${event.fileId}?from=/events`}
                className="flex items-center gap-1 text-primary hover:underline"
              >
                <FileText size={11} />
                Open
              </Link>
              <CopyableId id={event.fileId} />
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="uppercase tracking-wide">Extractor</span>
            <span>{event.extractor ?? "manual"}</span>
            {event.extractionModel && <span>· {event.extractionModel}</span>}
            {event.confidence != null && <span>· {Math.round(event.confidence * 100)}% conf</span>}
          </div>
          {event.sensitivity && (
            <div className="flex items-center gap-2">
              <Lock size={11} />
              <span className="capitalize">{event.sensitivity}</span>
            </div>
          )}
          {event.uid && (
            <div className="flex items-center gap-2">
              <span className="uppercase tracking-wide">UID</span>
              <span className="break-all font-mono text-[11px]">{event.uid}</span>
            </div>
          )}
        </div>

        {!event.isVerified && (
          <Button
            size="sm"
            variant="outline"
            className="w-full text-xs"
            disabled={update.isPending}
            onClick={() => update.mutate({ isVerified: true })}
          >
            <BadgeCheck size={13} /> Mark verified
          </Button>
        )}
        <ConfirmDialog
          trigger={
            <Button size="sm" variant="ghost" className="w-full text-xs text-destructive hover:text-destructive">
              <Trash2 size={13} /> Mark invalid
            </Button>
          }
          title="Mark this event invalid?"
          description="Not a real event — it is deleted along with its participants and places. The source file is kept."
          confirmLabel="Mark invalid"
          onConfirm={() => markInvalid.mutate(event.id)}
          isPending={markInvalid.isPending}
        />
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ edit form */

const dateOf = (iso: string | null) => (iso ? iso : "");
const timeOf = (iso: string | null) => (iso ? format(new Date(iso), "HH:mm") : "");

function combine(dateIso: string, time: string, allDay: boolean): string | null {
  if (!dateIso) return null;
  const datePart = dateIso.slice(0, 10);
  if (allDay || !time) return `${datePart}T00:00:00.000Z`;
  const d = new Date(`${datePart}T${time}`);
  return Number.isNaN(d.getTime()) ? `${datePart}T00:00:00.000Z` : d.toISOString();
}

function EventEditForm({
  event,
  onClose,
  hasFile,
  sourceOpen,
  onToggleSource,
}: {
  event: EventWithLinks;
  onClose: () => void;
  hasFile: boolean;
  sourceOpen: boolean;
  onToggleSource: () => void;
}) {
  const update = useUpdateEvent(event.id, onClose);

  const [title, setTitle] = useState(event.title);
  const [eventType, setEventType] = useState<EventType>(event.eventType);
  const [status, setStatus] = useState(event.status);
  const [datePrecision, setDatePrecision] = useState(event.datePrecision);
  const [summary, setSummary] = useState(event.summary ?? "");
  const [notes, setNotes] = useState(event.notes ?? "");
  const [timezone, setTimezone] = useState(event.timezone ?? "");
  const [isAllDay, setIsAllDay] = useState(event.isAllDay);
  const [startDate, setStartDate] = useState(dateOf(event.dateStart));
  const [startTime, setStartTime] = useState(timeOf(event.dateStart));
  const [endDate, setEndDate] = useState(dateOf(event.dateEnd));
  const [endTime, setEndTime] = useState(timeOf(event.dateEnd));
  const [tags, setTags] = useState<string[]>(event.tags);
  const [detailValues, setDetailValues] = useState<Record<string, string>>(
    detailsToFormValues(event.details)
  );

  const [tagQuery, setTagQuery] = useState("");
  const debouncedTagQuery = useDebounce(tagQuery, 200);
  const { data: tagSuggestions, isFetching: isFetchingTags } = useEventTagOptions({
    datasetId: event.datasetId ?? undefined,
    q: debouncedTagQuery || undefined,
  });

  const detailFields = detailFieldsFor(eventType);
  const titleError = title.trim() ? undefined : "Title is required";

  // Sensitivity and source labels are raw source metadata (iCalendar CLASS /
  // CATEGORIES) -- not analyst-editable, so they're shown read-only below and
  // never appear in the update payload.
  const save = () => {
    if (titleError) return;
    const payload: EventUpdatePayload = {
      title: title.trim(),
      eventType,
      status,
      datePrecision,
      summary: summary.trim() || null,
      notes: notes.trim() || null,
      timezone: timezone.trim() || null,
      isAllDay,
      dateStart: combine(startDate, startTime, isAllDay) ?? event.dateStart,
      dateEnd: combine(endDate, endTime, isAllDay),
      tags,
      details: buildDetails(eventType, detailValues) as EventUpdatePayload["details"],
    };
    update.mutate(payload);
  };

  return (
    <>
      <SheetHeader className="gap-1 pr-10">
        <div className="flex items-center justify-between gap-2">
          <SheetTitle className="text-sm uppercase tracking-wide">Edit event</SheetTitle>
          <SourceToggle hasFile={hasFile} sourceOpen={sourceOpen} onToggle={onToggleSource} />
        </div>
        <SheetDescription className="text-xs">
          Calendar colour follows the type; confidence and source fields stay read-only.
        </SheetDescription>
      </SheetHeader>

      <div className="space-y-5 px-6 py-5">
        <LabeledField label="Title" invalid={!!titleError}>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-invalid={!!titleError}
            className="bg-muted/40 text-sm"
          />
          {titleError && <p className="mt-1 text-[11px] text-destructive">{titleError}</p>}
        </LabeledField>

        <div className="grid grid-cols-2 gap-x-3 gap-y-5">
          <LabeledField label="Type">
            <Select value={eventType} onValueChange={(v) => setEventType(v as EventType)}>
              <SelectTrigger className="h-9 w-full bg-muted/40 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EVENT_TYPES.map((t) => {
                  const meta = EVENT_TYPE_META[t];
                  return (
                    <SelectItem key={t} value={t} className="text-sm">
                      <span className="flex items-center gap-2">
                        <meta.Icon size={13} className="text-muted-foreground" />
                        {meta.label}
                      </span>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </LabeledField>

          <LabeledField label="Status">
            <Select value={status} onValueChange={(v) => setStatus(v as typeof status)}>
              <SelectTrigger className="h-9 w-full bg-muted/40 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EVENT_STATUSES.map((s) => (
                  <SelectItem key={s} value={s} className="text-sm">
                    {EVENT_STATUS_LABELS[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </LabeledField>
        </div>

        <div className="grid grid-cols-2 gap-x-3 gap-y-5">
          <LabeledField label="Starts">
            <DatePicker value={startDate || undefined} onChange={(d) => setStartDate(d ?? "")} />
            {!isAllDay && (
              <div className="mt-1">
                <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
              </div>
            )}
          </LabeledField>
          <LabeledField label="Ends">
            <DatePicker value={endDate || undefined} onChange={(d) => setEndDate(d ?? "")} />
            {!isAllDay && (
              <div className="mt-1">
                <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
              </div>
            )}
          </LabeledField>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex h-9 w-fit shrink-0 items-center gap-2 text-xs text-muted-foreground">
            <Switch checked={isAllDay} onCheckedChange={setIsAllDay} />
            All day
          </label>
          <LabeledField label="Timezone (IANA)" className="flex-1">
            <Input
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              placeholder="America/New_York"
              className="h-9 bg-muted/40 text-sm"
            />
          </LabeledField>
        </div>

        <LabeledField label="Date precision" className="max-w-[calc(50%-0.375rem)]">
          <Select value={datePrecision} onValueChange={(v) => setDatePrecision(v as typeof datePrecision)}>
            <SelectTrigger className="h-9 w-full bg-muted/40 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DATE_PRECISIONS.map((p) => (
                <SelectItem key={p} value={p} className="text-sm capitalize">
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </LabeledField>

        <LabeledField label="Summary">
          <Textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            className="min-h-16 bg-muted/40 text-sm"
          />
        </LabeledField>

        {detailFields.length > 0 && (
          <div>
            <SectionHeading>Details</SectionHeading>
            <div className="grid grid-cols-2 gap-x-3 gap-y-5">
              {detailFields.map((f) => (
                <LabeledField key={f.name} label={f.label}>
                  {f.kind === "select" ? (
                    <Select
                      value={detailValues[f.name] ?? NONE}
                      onValueChange={(v) =>
                        setDetailValues((prev) => ({ ...prev, [f.name]: v === NONE ? "" : v }))
                      }
                    >
                      <SelectTrigger className="h-9 w-full bg-muted/40 text-sm">
                        <SelectValue placeholder="—" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE} className="text-sm">
                          —
                        </SelectItem>
                        {(f.options ?? []).map((o) => (
                          <SelectItem key={o} value={o} className="text-sm">
                            {o.replace(/_/g, " ")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      value={detailValues[f.name] ?? ""}
                      inputMode={f.kind === "text" ? undefined : "decimal"}
                      onChange={(e) =>
                        setDetailValues((prev) => ({ ...prev, [f.name]: e.target.value }))
                      }
                      className="h-9 bg-muted/40 text-sm"
                    />
                  )}
                </LabeledField>
              ))}
            </div>
          </div>
        )}

        <LabeledField label="Tags">
          <ProvenanceTagsInput
            target={{ targetType: "event", targetId: event.id }}
            value={tags}
            onChange={setTags}
            placeholder="Add a tag…"
            suggestions={tagSuggestions}
            onQueryChange={setTagQuery}
            isLoadingSuggestions={isFetchingTags}
          />
        </LabeledField>

        <LabeledField label="Notes">
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="min-h-16 bg-muted/40 text-sm"
          />
        </LabeledField>

        <SourceMeta event={event} />

        <LinkEditor event={event} />

        {update.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {(update.error as Error).message || "Failed to save the event"}
            </AlertDescription>
          </Alert>
        )}

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button variant="ghost" onClick={onClose} className="text-muted-foreground">
            Cancel
          </Button>
          <Button onClick={save} disabled={update.isPending || !!titleError} className="gap-2">
            {update.isPending && <Loader2 size={14} className="animate-spin" />}
            Save
          </Button>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------ participants + places */

function LinkEditor({ event }: { event: EventWithLinks }) {
  const addParticipant = useAddParticipant(event.id);
  const removeParticipant = useRemoveParticipant(event.id);
  const addPlace = useAddPlace(event.id);
  const removePlace = useRemovePlace(event.id);

  const [pRole, setPRole] = useState<ParticipantRole>("attendee");
  const [pEntityId, setPEntityId] = useState<string>();
  const [pEntityName, setPEntityName] = useState<string>();
  const [pName, setPName] = useState("");

  const [plRole, setPlRole] = useState<PlaceRole>("venue");
  const [plLocId, setPlLocId] = useState<string>();
  const [plLocName, setPlLocName] = useState<string>();
  const [plText, setPlText] = useState("");

  const submitParticipant = () => {
    if (!pEntityId && !pName.trim()) return;
    addParticipant.mutate(
      { entityId: pEntityId ?? null, rawName: pEntityId ? null : pName.trim(), role: pRole },
      {
        onSuccess: () => {
          setPEntityId(undefined);
          setPEntityName(undefined);
          setPName("");
        },
      }
    );
  };

  const submitPlace = () => {
    if (!plLocId && !plText.trim()) return;
    addPlace.mutate(
      { locationId: plLocId ?? null, rawText: plLocId ? null : plText.trim(), role: plRole },
      {
        onSuccess: () => {
          setPlLocId(undefined);
          setPlLocName(undefined);
          setPlText("");
        },
      }
    );
  };

  return (
    <div className="space-y-5">
      <div>
        <SectionHeading>People</SectionHeading>
        <ul className="space-y-1">
          {event.participants.map((p) => (
            <li key={p.id} className="flex items-center gap-2 text-sm">
              <span className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
                {p.role}
              </span>
              <span className="flex-1 truncate text-foreground/90">
                {p.rawName ?? p.rawEmail ?? p.entityId ?? "Unknown"}
              </span>
              <RemoveBtn onClick={() => removeParticipant.mutate(p.id)} />
            </li>
          ))}
        </ul>
        <div className="mt-2 flex items-center gap-2">
          <Select value={pRole} onValueChange={(v) => setPRole(v as ParticipantRole)}>
            <SelectTrigger className="h-8 w-28 bg-muted/40 text-xs capitalize">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PARTICIPANT_ROLES.map((r) => (
                <SelectItem key={r} value={r} className="text-xs capitalize">
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex-1">
            <EntityPicker
              value={pEntityId}
              valueName={pEntityName}
              entityTypes={["person", "organization"]}
              datasetId={event.datasetId ?? undefined}
              placeholder="Link a person / org…"
              onSelect={(id, name) => {
                setPEntityId(id);
                setPEntityName(name);
              }}
            />
          </div>
        </div>
        {!pEntityId && (
          <div className="mt-1.5 flex items-center gap-2">
            <Input
              value={pName}
              onChange={(e) => setPName(e.target.value)}
              placeholder="…or a plain name"
              className="h-8 bg-muted/40 text-xs"
            />
          </div>
        )}
        <Button
          size="sm"
          variant="outline"
          className="mt-2 h-7 gap-1 text-xs"
          disabled={addParticipant.isPending || (!pEntityId && !pName.trim())}
          onClick={submitParticipant}
        >
          <Plus size={12} /> Add person
        </Button>
      </div>

      <div>
        <SectionHeading>Places</SectionHeading>
        <ul className="space-y-1">
          {event.places.map((p) => (
            <li key={p.id} className="flex items-center gap-2 text-sm">
              <span className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
                {p.role}
              </span>
              <span className="flex-1 truncate text-foreground/90">
                {p.rawText ?? p.locationId ?? "Unnamed place"}
              </span>
              <RemoveBtn onClick={() => removePlace.mutate(p.id)} />
            </li>
          ))}
        </ul>
        <div className="mt-2 flex items-center gap-2">
          <Select value={plRole} onValueChange={(v) => setPlRole(v as PlaceRole)}>
            <SelectTrigger className="h-8 w-28 bg-muted/40 text-xs capitalize">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PLACE_ROLES.map((r) => (
                <SelectItem key={r} value={r} className="text-xs capitalize">
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex-1">
            <EntityPicker
              value={plLocId}
              valueName={plLocName}
              entityTypes={["location"]}
              datasetId={event.datasetId ?? undefined}
              placeholder="Link a location…"
              onSelect={(id, name) => {
                setPlLocId(id);
                setPlLocName(name);
              }}
            />
          </div>
        </div>
        {!plLocId && (
          <div className="mt-1.5 flex items-center gap-2">
            <Input
              value={plText}
              onChange={(e) => setPlText(e.target.value)}
              placeholder="…or plain text"
              className="h-8 bg-muted/40 text-xs"
            />
          </div>
        )}
        <Button
          size="sm"
          variant="outline"
          className="mt-2 h-7 gap-1 text-xs"
          disabled={addPlace.isPending || (!plLocId && !plText.trim())}
          onClick={submitPlace}
        >
          <Plus size={12} /> Add place
        </Button>
      </div>
    </div>
  );
}

function RemoveBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Remove"
      className="shrink-0 rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
    >
      <X size={12} />
    </button>
  );
}

/* ---------------------------------------------------------- labeled field */

/**
 * Notches the label into the top border of its control instead of stacking
 * it above with a gap — that way there's no ambiguity about whether the
 * label belongs to the field below it or the one above (see the space-y
 * rhythm on the surrounding form, which is free to breathe since labels no
 * longer consume their own line).
 */
function LabeledField({
  label,
  hint,
  invalid = false,
  className,
  children,
}: {
  label: string;
  /** Short explainer shown on hover of an info glyph next to the label, for fields whose meaning isn't self-evident. */
  hint?: string;
  invalid?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("relative", className)}>
      <span
        className={cn(
          "pointer-events-none absolute top-0 left-2.5 z-10 flex -translate-y-1/2 items-center gap-1 bg-background px-1 text-[11px] leading-none font-medium tracking-wide uppercase",
          invalid ? "text-destructive" : "text-muted-foreground"
        )}
      >
        {label}
        {hint && (
          <Tooltip delayDuration={200}>
            <TooltipTrigger asChild>
              <span className="pointer-events-auto text-muted-foreground/70 normal-case tracking-normal hover:text-foreground">
                <Info size={10} />
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-56 text-xs normal-case tracking-normal">
              {hint}
            </TooltipContent>
          </Tooltip>
        )}
      </span>
      {children}
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2 pt-1 text-[11px] font-semibold tracking-wide text-foreground/70 uppercase">
      <span className="shrink-0">{children}</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

/* --------------------------------------------------------------- source meta */

/**
 * Read-only strip for fields that come straight from the source (extractor,
 * confidence, iCalendar CLASS/CATEGORIES) -- distinct from `tags`, which is
 * the analyst's own editable field. See `LabeledField`'s lock-icon fields
 * above for the same "this isn't yours to change" affordance on a single field.
 */
function SourceMeta({ event }: { event: EventWithLinks }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border border-border/60 bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
      <span className="flex items-center gap-1 font-medium tracking-wide text-muted-foreground/70 uppercase">
        <Lock size={10} /> Source
      </span>
      <span>
        {event.extractor ?? "manual"}
        {event.extractionModel && ` · ${event.extractionModel}`}
      </span>
      {event.confidence != null && <span>{Math.round(event.confidence * 100)}% conf</span>}
      {event.sensitivity && <span className="capitalize">{event.sensitivity}</span>}
      {event.categories.map((c) => (
        <Badge
          key={c}
          variant="outline"
          className="h-5 border-border/60 bg-transparent px-1.5 text-[11px] font-normal text-muted-foreground"
        >
          {c}
        </Badge>
      ))}
    </div>
  );
}

/* --------------------------------------------------------- shared read bits */

function SourceToggle({
  hasFile,
  sourceOpen,
  onToggle,
}: {
  hasFile: boolean;
  sourceOpen: boolean;
  onToggle: () => void;
}) {
  if (!hasFile) return null;
  return (
    <Button
      size="sm"
      variant={sourceOpen ? "secondary" : "outline"}
      className="h-7 gap-1 px-2 text-xs text-muted-foreground"
      onClick={onToggle}
      title="Show the source file alongside"
    >
      <PanelRight size={12} /> Source
    </Button>
  );
}

function TypeBadge({
  eventType,
  category,
}: {
  eventType: keyof typeof EVENT_TYPE_META;
  category: string;
}) {
  const cat = categoryMeta(category);
  const meta = EVENT_TYPE_META[eventType];
  return (
    <Badge
      variant="outline"
      title="Type · the calendar colour follows the category this type maps to"
      className={cn(
        "h-6 gap-1.5 px-2 text-[11px] font-bold uppercase tracking-wide",
        cat.bgClass,
        cat.textClass,
        cat.borderClass
      )}
    >
      <meta.Icon size={11} />
      {meta.label}
    </Badge>
  );
}

function DetailBlock({
  icon,
  title,
  children,
}: {
  icon?: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}

function PlaceRow({ place }: { place: EventPlace }) {
  const label = place.rawText ?? "Unnamed place";
  return (
    <li className="flex items-center gap-2 text-sm">
      <span className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
        {place.role}
      </span>
      {place.locationId ? (
        <Link href={`/locations?focus=${place.locationId}`} className="text-foreground hover:text-primary">
          {label}
        </Link>
      ) : (
        <span className="text-foreground/90">{label}</span>
      )}
    </li>
  );
}

function ParticipantRow({ participant }: { participant: EventParticipant }) {
  const label = participant.rawName ?? participant.rawEmail ?? "Unknown";
  return (
    <li className="flex items-center gap-2 text-sm">
      <span className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
        {participant.role}
      </span>
      {participant.entityId ? (
        <Link href={`/entities/${participant.entityId}`} className="text-foreground hover:text-primary">
          {label}
        </Link>
      ) : (
        <span className="text-foreground/90">{label}</span>
      )}
      {participant.isResource && (
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground/70">resource</span>
      )}
      {participant.rsvpStatus && participant.rsvpStatus !== "needs-action" && (
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground/70">
          {participant.rsvpStatus}
        </span>
      )}
    </li>
  );
}

function TypedDetails({ details }: { details: Record<string, unknown> }) {
  const entries = Object.entries(details).filter(
    ([k, v]) => !HIDDEN_DETAIL_KEYS.has(k) && v != null && v !== ""
  );
  if (entries.length === 0) return null;
  return (
    <DetailBlock title="Details">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</dt>
            <dd className="text-foreground/90">{String(v)}</dd>
          </div>
        ))}
      </dl>
    </DetailBlock>
  );
}
