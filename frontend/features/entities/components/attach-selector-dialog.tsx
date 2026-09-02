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
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { RegionCombobox } from "@/features/entities/components/region-combobox";
import { useAttachSelector } from "@/features/entities/hooks/use-entities";
import {
  SELECTOR_KIND_LABELS,
  SELECTOR_KINDS,
  type SelectorKind,
} from "@/features/entities/types";
import { Loader2 } from "lucide-react";
import { useState } from "react";

interface AttachSelectorDialogProps {
  entityId: string;
  /** Shown in the dialog copy, e.g. the person's name. */
  entityLabel?: string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AttachSelectorDialog({
  entityId,
  entityLabel,
  isOpen,
  onOpenChange,
}: AttachSelectorDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="border-border bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xs font-black uppercase tracking-[0.1em] text-white">
            Add selector
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Link a phone, email, handle, or other strong identifier to{" "}
            {entityLabel || "this person"}.
          </DialogDescription>
        </DialogHeader>
        <AttachSelectorForm
          key={String(isOpen)}
          entityId={entityId}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function AttachSelectorForm({
  entityId,
  onDone,
}: {
  entityId: string;
  onDone: () => void;
}) {
  const [datasetId, setDatasetId] = useState<string | undefined>(undefined);
  const [kind, setKind] = useState<SelectorKind>("phone");
  const [rawValue, setRawValue] = useState("");
  const [region, setRegion] = useState<string | undefined>(undefined);

  const attach = useAttachSelector(entityId, onDone);

  const canSubmit = !!datasetId && rawValue.trim().length > 0 && !attach.isPending;

  const handleSubmit = () => {
    if (!datasetId) return;
    attach.mutate({
      datasetId,
      selectorKind: kind,
      rawValue: rawValue.trim(),
      regionHint: kind === "phone" ? region : undefined,
    });
  };

  return (
    <>
      <FieldGroup>
        <Field>
          <FieldLabel className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Dataset
          </FieldLabel>
          <DatasetSelect
            datasetId={datasetId}
            onChange={setDatasetId}
            className="h-10 w-full"
          />
          <FieldDescription className="text-[11px]">
            The dataset this selector was observed in.
          </FieldDescription>
        </Field>

        <div className="grid grid-cols-[9rem_1fr] gap-3">
          <Field>
            <FieldLabel className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Type
            </FieldLabel>
            <Select value={kind} onValueChange={(v) => setKind(v as SelectorKind)}>
              <SelectTrigger className="w-full border-border bg-muted/40 text-sm data-[size=default]:h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SELECTOR_KINDS.map((k) => (
                  <SelectItem key={k} value={k}>
                    {SELECTOR_KIND_LABELS[k]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field>
            <FieldLabel className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Value
            </FieldLabel>
            <Input
              value={rawValue}
              onChange={(e) => setRawValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit) handleSubmit();
              }}
              placeholder={
                kind === "phone"
                  ? "+1 202 555 0173"
                  : kind === "email"
                    ? "jane@example.com"
                    : "identifier"
              }
              className="border-border bg-muted/40 text-sm"
            />
          </Field>
        </div>

        {kind === "phone" && (
          <Field>
            <FieldLabel className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Country
            </FieldLabel>
            <RegionCombobox value={region} onChange={setRegion} />
            <FieldDescription className="text-[11px]">
              Normalizes a number written without a country code.
            </FieldDescription>
          </Field>
        )}

        {attach.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {(attach.error as Error)?.message || "Failed to add selector"}
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
          {attach.isPending && <Loader2 size={14} className="animate-spin" />}
          Add selector
        </Button>
      </DialogFooter>
    </>
  );
}
