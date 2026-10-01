"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DatePicker } from "@/components/date-picker";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { TagsInput } from "@/components/tags-input";
import { useUpdatePerson } from "@/features/persons/hooks/use-persons";
import { Person, SexType } from "@/features/persons/types";
import { Loader2 } from "lucide-react";
import { useState } from "react";

interface EditPersonDialogProps {
  person: Person;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditPersonDialog({ person, isOpen, onOpenChange }: EditPersonDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card border-border sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-white tracking-wide uppercase text-xs font-semibold">
            Edit Person
          </DialogTitle>
        </DialogHeader>
        {/* keyed by isOpen so each time the dialog opens it remounts with fresh state from `person` */}
        <EditPersonForm key={String(isOpen)} person={person} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function EditPersonForm({ person, onDone }: { person: Person; onDone: () => void }) {
  const [name, setName] = useState(person.name ?? "");
  const [sex, setSex] = useState<SexType | undefined>(person.sex);
  const [dateOfBirth, setDateOfBirth] = useState<string | undefined>(person.dateOfBirth);
  const [notes, setNotes] = useState(person.notes ?? "");
  const [tags, setTags] = useState<string[]>(person.tags ?? []);
  const [isVerified, setIsVerified] = useState(person.isVerified);

  const updatePerson = useUpdatePerson(person.id, onDone);

  const handleSubmit = () => {
    updatePerson.mutate({
      name: name.trim() || undefined,
      sex,
      dateOfBirth,
      notes: notes.trim() || undefined,
      tags,
      isVerified,
    });
  };

  return (
    <>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="edit-person-name" className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Name
          </Label>
          <Input
            id="edit-person-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Jane Doe"
            className="bg-muted/40 border-border text-sm"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Sex</Label>
            <Select value={sex} onValueChange={(v) => setSex(v as SexType)}>
              <SelectTrigger className="w-full bg-muted/40 border-border text-sm data-[size=default]:h-10">
                <SelectValue placeholder="Unknown" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="female">Female</SelectItem>
                <SelectItem value="male">Male</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Date of birth</Label>
            <DatePicker value={dateOfBirth} onChange={setDateOfBirth} />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="edit-person-notes" className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Notes
          </Label>
          <Textarea
            id="edit-person-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Analyst notes..."
            className="bg-muted/40 border-border text-sm min-h-20"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Tags</Label>
          <TagsInput value={tags} onChange={setTags} />
        </div>

        <div className="flex items-center justify-between">
          <Label htmlFor="edit-person-verified" className="text-[12px] text-muted-foreground font-medium">
            Mark as verified identity
          </Label>
          <Switch id="edit-person-verified" checked={isVerified} onCheckedChange={setIsVerified} />
        </div>

        {updatePerson.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {(updatePerson.error as Error)?.message || "Failed to update person"}
            </AlertDescription>
          </Alert>
        )}
      </div>

      <DialogFooter>
        <Button variant="ghost" onClick={onDone} className="text-muted-foreground">
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={updatePerson.isPending}
          className="bg-primary hover:bg-primary gap-2"
        >
          {updatePerson.isPending && <Loader2 size={14} className="animate-spin" />}
          Save Changes
        </Button>
      </DialogFooter>
    </>
  );
}
