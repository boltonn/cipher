"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { TagsInput } from "@/components/tags-input";
import {
  useUpdateEntity,
  useUpdateEntityDetail,
} from "@/features/entities/hooks/use-entities";
import type { Entity, EntityDetail } from "@/features/entities/types";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

interface EditEntityDialogProps {
  entity: Entity;
  detail?: EntityDetail | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

const pick = (d: EntityDetail | null | undefined, ...keys: string[]) => {
  for (const k of keys) {
    const v = d?.[k];
    if (v != null && v !== "") return String(v);
  }
  return "";
};

export function EditEntityDialog({ entity, detail, isOpen, onOpenChange }: EditEntityDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto border-border bg-card sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-xs font-black uppercase tracking-[0.1em] text-white">
            Edit {entity.entityType}
          </DialogTitle>
        </DialogHeader>
        <EditEntityForm
          key={String(isOpen)}
          entity={entity}
          detail={detail}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function EditEntityForm({
  entity,
  detail,
  onDone,
}: {
  entity: Entity;
  detail?: EntityDetail | null;
  onDone: () => void;
}) {
  const [displayName, setDisplayName] = useState(entity.displayName);
  const [aliases, setAliases] = useState<string[]>(entity.aliases ?? []);
  const [tags, setTags] = useState<string[]>(entity.tags ?? []);
  const [notes, setNotes] = useState(entity.notes ?? "");
  const [isVerified, setIsVerified] = useState(entity.isVerified);

  // detail fields (org / location / selector)
  const [legalName, setLegalName] = useState(pick(detail, "legalName", "legal_name"));
  const [orgType, setOrgType] = useState(pick(detail, "orgType", "org_type"));
  const [country, setCountry] = useState(pick(detail, "country"));
  const [addressText, setAddressText] = useState(pick(detail, "addressText", "address_text"));
  const [latitude, setLatitude] = useState(pick(detail, "latitude"));
  const [longitude, setLongitude] = useState(pick(detail, "longitude"));
  const [adminArea, setAdminArea] = useState(pick(detail, "adminArea", "admin_area"));
  const [rawValue, setRawValue] = useState(pick(detail, "rawValue", "raw_value"));
  const [regionHint, setRegionHint] = useState(pick(detail, "regionHint", "region_hint"));

  const updateEntity = useUpdateEntity(entity.id);
  const updateDetail = useUpdateEntityDetail(entity.id);
  const pending = updateEntity.isPending || updateDetail.isPending;

  const handleSubmit = async () => {
    await updateEntity.mutateAsync({
      displayName: displayName.trim() || entity.displayName,
      aliases,
      tags,
      notes: notes.trim() || undefined,
      isVerified,
    });

    if (entity.entityType === "organization") {
      await updateDetail.mutateAsync({
        legalName: legalName || null,
        orgType: orgType || null,
        country: country || null,
      });
    } else if (entity.entityType === "location") {
      await updateDetail.mutateAsync({
        addressText: addressText || null,
        latitude: latitude ? Number(latitude) : null,
        longitude: longitude ? Number(longitude) : null,
        country: country || null,
        adminArea: adminArea || null,
      });
    } else if (entity.entityType === "selector") {
      await updateDetail.mutateAsync({
        rawValue: rawValue || null,
        regionHint: regionHint || null,
      });
    }
    onDone();
  };

  return (
    <>
      <div className="space-y-4">
        <FieldRow label="Display name">
          <Input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="bg-muted/40 text-sm"
          />
        </FieldRow>

        <FieldRow label="Aliases">
          <TagsInput value={aliases} onChange={setAliases} placeholder="Add an alias…" />
        </FieldRow>

        <FieldRow label="Tags">
          <TagsInput value={tags} onChange={setTags} />
        </FieldRow>

        <FieldRow label="Notes">
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Analyst notes…"
            className="min-h-20 bg-muted/40 text-sm"
          />
        </FieldRow>

        {entity.entityType === "person" && (
          <p className="rounded-md border border-border/60 bg-muted/30 p-3 text-[11px] text-muted-foreground">
            Person attributes (date of birth, sex, nationality) are edited in{" "}
            <Link
              href={`/persons/${entity.personId ?? ""}`}
              className="font-semibold text-primary hover:underline"
            >
              Persons
            </Link>
            .
          </p>
        )}

        {entity.entityType === "organization" && (
          <>
            <FieldRow label="Legal name">
              <Input value={legalName} onChange={(e) => setLegalName(e.target.value)} className="bg-muted/40 text-sm" />
            </FieldRow>
            <div className="grid grid-cols-2 gap-3">
              <FieldRow label="Org type">
                <Input value={orgType} onChange={(e) => setOrgType(e.target.value)} className="bg-muted/40 text-sm" />
              </FieldRow>
              <FieldRow label="Country">
                <Input value={country} onChange={(e) => setCountry(e.target.value)} className="bg-muted/40 text-sm" />
              </FieldRow>
            </div>
          </>
        )}

        {entity.entityType === "location" && (
          <>
            <FieldRow label="Address">
              <Input value={addressText} onChange={(e) => setAddressText(e.target.value)} className="bg-muted/40 text-sm" />
            </FieldRow>
            <div className="grid grid-cols-2 gap-3">
              <FieldRow label="Latitude">
                <Input value={latitude} onChange={(e) => setLatitude(e.target.value)} className="bg-muted/40 text-sm" />
              </FieldRow>
              <FieldRow label="Longitude">
                <Input value={longitude} onChange={(e) => setLongitude(e.target.value)} className="bg-muted/40 text-sm" />
              </FieldRow>
              <FieldRow label="Country">
                <Input value={country} onChange={(e) => setCountry(e.target.value)} className="bg-muted/40 text-sm" />
              </FieldRow>
              <FieldRow label="Admin area">
                <Input value={adminArea} onChange={(e) => setAdminArea(e.target.value)} className="bg-muted/40 text-sm" />
              </FieldRow>
            </div>
          </>
        )}

        {entity.entityType === "selector" && (
          <div className="grid grid-cols-2 gap-3">
            <FieldRow label="Raw value">
              <Input value={rawValue} onChange={(e) => setRawValue(e.target.value)} className="bg-muted/40 text-sm" />
            </FieldRow>
            <FieldRow label="Region hint">
              <Input value={regionHint} onChange={(e) => setRegionHint(e.target.value)} className="bg-muted/40 text-sm" />
            </FieldRow>
          </div>
        )}

        <div className="flex items-center justify-between">
          <Label htmlFor="edit-entity-verified" className="text-[12px] font-medium text-muted-foreground">
            Verified entity
          </Label>
          <Switch id="edit-entity-verified" checked={isVerified} onCheckedChange={setIsVerified} />
        </div>

        {(updateEntity.isError || updateDetail.isError) && (
          <p className="text-[11px] text-destructive">Failed to save changes.</p>
        )}
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onDone} className="text-muted-foreground">
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={pending} className="gap-2 bg-primary hover:bg-primary">
          {pending && <Loader2 size={14} className="animate-spin" />}
          Save changes
        </Button>
      </DialogFooter>
    </>
  );
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}
