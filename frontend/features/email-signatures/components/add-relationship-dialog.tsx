"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  allowedRelationships,
  takesRole,
} from "@/features/email-signatures/components/relationship-row";
import { useCreateRelationship } from "@/features/email-signatures/hooks/use-email-signatures";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import type {
  Mention,
  OntologyRelationship,
  RelationshipType,
} from "@/features/entities/types";
import { Loader2, Plus } from "lucide-react";
import { useState } from "react";

interface Draft {
  srcMentionId?: string;
  relationshipType?: RelationshipType;
  dstMentionId?: string;
  role: string;
}

function MentionSelect({
  label,
  mentions,
  value,
  exclude,
  onChange,
}: {
  label: string;
  mentions: Mention[];
  value?: string;
  exclude?: string;
  onChange: (id: string) => void;
}) {
  return (
    <Field>
      <FieldLabel className="text-xs">{label}</FieldLabel>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-9 w-full text-xs">
          <SelectValue placeholder="Pick a label from the email signature" />
        </SelectTrigger>
        <SelectContent>
          {mentions
            .filter((m) => m.id !== exclude)
            .map((m) => {
              const meta = m.entityType ? ENTITY_TYPE_META[m.entityType] : null;
              return (
                <SelectItem key={m.id} value={m.id} className="text-xs">
                  {meta && <meta.Icon size={12} className={meta.textClass} />}
                  {m.surfaceText.replace(/\s+/g, " ")}
                </SelectItem>
              );
            })}
        </SelectContent>
      </Select>
    </Field>
  );
}

/**
 * Draw a relationship the reader missed: pick two labels of the email signature and a type
 * the ontology allows between them (plus a role for employment). It is pending until accepted,
 * like an extracted one. To relate something that isn't labelled yet, label it in the text first.
 */
export function AddRelationshipDialog({
  open,
  onOpenChange,
  mentions,
  relationships,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mentions: Mention[];
  relationships: OntologyRelationship[];
}) {
  const [draft, setDraft] = useState<Draft>({ role: "" });
  const close = () => {
    setDraft({ role: "" });
    onOpenChange(false);
  };
  const create = useCreateRelationship(close);
  const src = mentions.find((m) => m.id === draft.srcMentionId);
  const dst = mentions.find((m) => m.id === draft.dstMentionId);
  const types = allowedRelationships(relationships, src, dst);
  const spec = types.find((t) => t.relationshipType === draft.relationshipType);
  const ready = !!(src && dst && spec);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
    >
      <DialogContent className="border-border bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add a relationship</DialogTitle>
          <DialogDescription>
            Between two labels of this email signature. Something not labelled
            yet? Select it in the text and label it first.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!ready) return;
            create.mutate({
              srcMentionId: src.id,
              dstMentionId: dst.id,
              relationshipType: spec.relationshipType,
              attributes:
                takesRole(spec) && draft.role.trim()
                  ? { role: draft.role.trim() }
                  : {},
            });
          }}
        >
          <MentionSelect
            label="From"
            mentions={mentions}
            value={draft.srcMentionId}
            exclude={draft.dstMentionId}
            onChange={(srcMentionId) =>
              setDraft((d) => ({ ...d, srcMentionId }))
            }
          />
          <Field>
            <FieldLabel className="text-xs">Relationship</FieldLabel>
            <Select
              value={spec ? draft.relationshipType : undefined}
              onValueChange={(value) =>
                setDraft((d) => ({
                  ...d,
                  relationshipType: value as RelationshipType,
                }))
              }
            >
              <SelectTrigger className="h-9 w-full text-xs">
                <SelectValue
                  placeholder={
                    types.length ? "Pick a type" : "Nothing fits these two"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {types.map((t) => (
                  <SelectItem
                    key={t.relationshipType}
                    value={t.relationshipType}
                    className="text-xs"
                  >
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {spec?.description && (
              <p className="text-[11px] text-muted-foreground">
                {spec.description}
              </p>
            )}
          </Field>
          <MentionSelect
            label="To"
            mentions={mentions}
            value={draft.dstMentionId}
            exclude={draft.srcMentionId}
            onChange={(dstMentionId) =>
              setDraft((d) => ({ ...d, dstMentionId }))
            }
          />
          {takesRole(spec) && (
            <Field>
              <FieldLabel className="text-xs">Role (optional)</FieldLabel>
              <Input
                value={draft.role}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, role: e.target.value }))
                }
                placeholder="Assistant Director, Recruitment Outreach"
                className="h-9 text-xs"
              />
            </Field>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={close}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!ready || create.isPending}
              className="gap-1.5 text-xs"
            >
              {create.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Plus size={12} />
              )}
              Add relationship
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
