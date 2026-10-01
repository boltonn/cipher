"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EntityPicker } from "@/features/entities/components/entity-picker";
import {
  useCreateRelationship,
  useOntology,
} from "@/features/entities/hooks/use-entities";
import type { OntologyRelationship } from "@/features/entities/types";
import { PersonPicker } from "@/features/persons/components/person-picker";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";

/** Edge types that aren't "connections" you add here. */
const EXCLUDED = new Set(["has_selector", "same_as", "appears_in_photo_with"]);

const titleCase = (s: string) =>
  s
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");

interface AddConnectionDialogProps {
  /** The person this connection starts from (bridge entity id == person id). */
  entityId: string;
  entityLabel?: string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddConnectionDialog({
  entityId,
  entityLabel,
  isOpen,
  onOpenChange,
}: AddConnectionDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="border-border bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xs font-semibold uppercase tracking-wide text-white">
            Add connection
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Add a relationship from {entityLabel || "this person"} to another entity.
          </DialogDescription>
        </DialogHeader>
        <AddConnectionForm
          key={String(isOpen)}
          entityId={entityId}
          entityLabel={entityLabel}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function AddConnectionForm({
  entityId,
  entityLabel,
  onDone,
}: {
  entityId: string;
  entityLabel?: string;
  onDone: () => void;
}) {
  const { data: ontology } = useOntology();
  const create = useCreateRelationship(entityId, onDone);

  // Relationship types a person can be the source of, minus selectors/merges/associate.
  const options = useMemo<OntologyRelationship[]>(
    () =>
      (ontology?.relationships ?? []).filter(
        (r) =>
          r.allowedSrc.includes("person") &&
          !EXCLUDED.has(r.relationshipType)
      ),
    [ontology]
  );

  const [type, setType] = useState<string>("family_of");
  const [targetId, setTargetId] = useState<string | undefined>(undefined);
  const [targetName, setTargetName] = useState<string | undefined>(undefined);
  const [role, setRole] = useState<string | undefined>(undefined);

  const spec = options.find((o) => o.relationshipType === type);
  const wantsPerson = spec?.allowedDst.length === 1 && spec.allowedDst[0] === "person";

  const isSelf = !!targetId && targetId === entityId;
  const canSubmit = !!spec && !!targetId && !isSelf && !create.isPending;

  const resetTarget = () => {
    setTargetId(undefined);
    setTargetName(undefined);
    setRole(undefined);
  };

  const handleSubmit = () => {
    if (!spec || !targetId || isSelf) return;
    create.mutate({
      dstEntityId: targetId,
      relationshipType: spec.relationshipType,
      attributes: role ? { role } : undefined,
    });
  };

  return (
    <>
      <FieldGroup>
        <Field>
          <FieldLabel className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Connection
          </FieldLabel>
          <Select
            value={type}
            onValueChange={(v) => {
              setType(v);
              resetTarget();
            }}
          >
            <SelectTrigger className="w-full border-border bg-muted/40 text-sm data-[size=default]:h-10">
              <SelectValue placeholder="Select a connection type" />
            </SelectTrigger>
            <SelectContent>
              {options.map((o) => (
                <SelectItem key={o.relationshipType} value={o.relationshipType}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field>
          <FieldLabel className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {wantsPerson ? "Person" : titleCase(spec?.allowedDst[0] ?? "entity")}
          </FieldLabel>
          {wantsPerson ? (
            <PersonPicker
              value={targetId}
              valueName={targetName}
              placeholder="Search people…"
              onSelect={(id, name) => {
                setTargetId(id);
                setTargetName(name);
              }}
            />
          ) : (
            <EntityPicker
              value={targetId}
              valueName={targetName}
              entityTypes={spec?.allowedDst ?? []}
              placeholder={`Search ${(spec?.allowedDst ?? ["entities"]).join(" / ")}…`}
              onSelect={(id, name) => {
                setTargetId(id);
                setTargetName(name);
              }}
            />
          )}
          {isSelf && (
            <p className="text-[11px] text-destructive">Pick a different entity.</p>
          )}
        </Field>

        {spec && spec.roles.length > 0 && (
          <Field>
            <FieldLabel className="text-[11px] uppercase tracking-wide text-muted-foreground">
              {entityLabel || "This person"} is the…
            </FieldLabel>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger className="w-full border-border bg-muted/40 text-sm data-[size=default]:h-10">
                <SelectValue placeholder="Role (optional)" />
              </SelectTrigger>
              <SelectContent>
                {spec.roles.map((r) => (
                  <SelectItem key={r} value={r}>
                    {titleCase(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        )}

        {create.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {(create.error as Error)?.message || "Failed to add connection"}
            </AlertDescription>
          </Alert>
        )}
      </FieldGroup>

      <DialogFooter>
        <Button variant="ghost" onClick={onDone} className="text-muted-foreground">
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="gap-2 bg-primary hover:bg-primary"
        >
          {create.isPending && <Loader2 size={14} className="animate-spin" />}
          Add connection
        </Button>
      </DialogFooter>
    </>
  );
}
