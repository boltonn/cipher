"use client";

import { Button } from "@/components/ui/button";
import { DatePicker } from "@/components/date-picker";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Textarea } from "@/components/ui/textarea";
import { TagsInput } from "@/components/tags-input";
import { facesService } from "@/features/faces/api";
import { FaceImageWithOverlay } from "@/features/faces/components/face-image-overlay";
import { FacePickerContent } from "@/features/faces/components/face-picker";
import { DetectedFace, FacePublic, FaceSimilarityResult } from "@/features/faces/types";
import {
  useCreatePerson,
  useCreatePersonFromFace,
  useCreatePersonFromImage,
} from "@/features/persons/hooks/use-persons";
import { PersonCreate, SexType } from "@/features/persons/types";
import { cn } from "@/lib/utils";
import { BadgeCheck, Loader2, UserRound } from "lucide-react";
import { useRef, useState } from "react";

interface CreatePersonDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** Skip the upload/detect step and create the person straight from this already-detected face. */
  sourceFace?: FacePublic | FaceSimilarityResult;
}

export function CreatePersonDialog({ isOpen, onOpenChange, sourceFace }: CreatePersonDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const [detectedFaces, setDetectedFaces] = useState<DetectedFace[]>([]);
  const [selectedFaceIndex, setSelectedFaceIndex] = useState<number | null>(null);

  const [name, setName] = useState("");
  const [sex, setSex] = useState<SexType | undefined>(undefined);
  const [dateOfBirth, setDateOfBirth] = useState<string | undefined>(undefined);
  const [notes, setNotes] = useState("");
  const [tags, setTags] = useState<string[]>([]);

  const resetForm = () => {
    setFile(null);
    setPreviewUrl(null);
    setDetectedFaces([]);
    setSelectedFaceIndex(null);
    setName("");
    setSex(undefined);
    setDateOfBirth(undefined);
    setNotes("");
    setTags([]);
  };

  const onCreated = () => {
    resetForm();
    onOpenChange(false);
  };
  const createPersonFromImage = useCreatePersonFromImage(onCreated);
  const createPersonFromFace = useCreatePersonFromFace(onCreated);
  const createPerson = useCreatePerson(onCreated);
  const isPending = createPersonFromImage.isPending || createPersonFromFace.isPending || createPerson.isPending;
  const isError = createPersonFromImage.isError || createPersonFromFace.isError || createPerson.isError;
  const error = createPersonFromImage.error || createPersonFromFace.error || createPerson.error;

  const handleFile = async (selected: File | undefined) => {
    if (!selected) return;
    setFile(selected);
    setPreviewUrl(URL.createObjectURL(selected));
    setDetectedFaces([]);
    setSelectedFaceIndex(null);
    setIsDetecting(true);
    try {
      const detected = await facesService.detect(selected);
      setDetectedFaces(detected);
      if (detected.length === 1) setSelectedFaceIndex(0);
    } finally {
      setIsDetecting(false);
    }
  };

  const handleRemovePhoto = () => {
    setFile(null);
    setPreviewUrl(null);
    setDetectedFaces([]);
    setSelectedFaceIndex(null);
  };

  const handleClose = () => {
    resetForm();
    createPersonFromImage.reset();
    createPersonFromFace.reset();
    createPerson.reset();
    onOpenChange(false);
  };

  const buildPayload = (): PersonCreate & { faceIndex?: number } => ({
    name: name.trim() || undefined,
    sex,
    dateOfBirth,
    notes: notes.trim() || undefined,
    tags,
    faceIndex: selectedFaceIndex ?? undefined,
  });

  const handleSubmit = () => {
    if (sourceFace) {
      createPersonFromFace.mutate({ faceId: sourceFace.id, payload: buildPayload() });
    } else if (file) {
      if (selectedFaceIndex === null) return; // still needs a face picked
      createPersonFromImage.mutate({ file, payload: buildPayload() });
    } else {
      createPerson.mutate(buildPayload());
    }
  };

  // needs a face picked before the rest of the form is usable
  const needsFacePick = !sourceFace && !!file && detectedFaces.length > 1 && selectedFaceIndex === null;
  const canSubmit = !isDetecting && (!!sourceFace || !file || selectedFaceIndex !== null) && !isPending;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => (open ? onOpenChange(open) : handleClose())}>
      <DialogContent className="bg-card border-border sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-white tracking-[0.1em] uppercase text-xs font-black">
            Create Person
          </DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            {sourceFace
              ? "This face will become the new person's primary reference photo."
              : "A reference photo is optional -- add one now or assign faces to this person later."}
          </DialogDescription>
        </DialogHeader>

        {needsFacePick && file ? (
          <FacePickerContent
            file={file}
            faces={detectedFaces}
            onConfirm={(index) => setSelectedFaceIndex(index)}
            onCancel={handleRemovePhoto}
          />
        ) : (
          <div className="space-y-4">
            {sourceFace ? (
              <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-black border border-annotation/40">
                <FaceImageWithOverlay
                  src={facesService.getFaceViewUrl(sourceFace.id)}
                  alt="Selected face"
                  boxes={[{ bbox: sourceFace.boundingBox, isSelected: true }]}
                />
              </div>
            ) : previewUrl && selectedFaceIndex !== null ? (
              <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-black border border-annotation/40">
                <FaceImageWithOverlay
                  src={previewUrl}
                  alt="Preview"
                  boxes={detectedFaces.map((f, i) => ({
                    bbox: f.boundingBox,
                    isSelected: i === selectedFaceIndex,
                  }))}
                />
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isDetecting}
                className={cn(
                  "w-full aspect-video rounded-xl border border-dashed flex items-center justify-center overflow-hidden transition-colors relative",
                  previewUrl ? "border-annotation/40" : "border-border hover:border-white/20 bg-muted/40"
                )}
              >
                {isDetecting ? (
                  <Loader2 size={24} className="animate-spin text-annotation" />
                ) : (
                  <span className="text-muted-foreground text-xs flex flex-col items-center gap-2">
                    <UserRound size={24} />
                    Click to choose a photo (optional)
                  </span>
                )}
              </button>
            )}
            {!sourceFace && (
              <input
                ref={fileInputRef}
                type="file"
                aria-label="Upload photo"
                accept="image/*"
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0])}
              />
            )}
            {!sourceFace && file && !isDetecting && (
              <div className="flex items-center gap-4">
                {detectedFaces.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setSelectedFaceIndex(null)}
                    className="text-[10px] text-annotation/80 hover:text-annotation uppercase tracking-widest font-bold"
                  >
                    Change face
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleRemovePhoto}
                  className="text-[10px] text-destructive/70 hover:text-destructive uppercase tracking-widest font-bold"
                >
                  Remove photo
                </button>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="person-name" className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Name
              </Label>
              <Input
                id="person-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Doe"
                className="bg-muted/40 border-border text-sm"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-[10px] uppercase tracking-widest text-muted-foreground">Sex</Label>
                <Select value={sex} onValueChange={(v) => setSex(v as SexType)}>
                  <SelectTrigger className="w-full bg-muted/40 border-border text-sm">
                    <SelectValue placeholder="Unknown" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="female">Female</SelectItem>
                    <SelectItem value="male">Male</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  Date of birth
                </Label>
                <DatePicker value={dateOfBirth} onChange={setDateOfBirth} />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="person-notes" className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Notes
              </Label>
              <Textarea
                id="person-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Analyst notes..."
                className="bg-muted/40 border-border text-sm min-h-20"
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase tracking-widest text-muted-foreground">Tags</Label>
              <TagsInput value={tags} onChange={setTags} placeholder="person-of-interest, witness..." />
            </div>

            <div className="flex items-center gap-1.5 text-[11px] text-primary/80">
              <BadgeCheck size={13} />
              People created here are always marked verified.
            </div>

            {isError && (
              <p className="text-[11px] text-destructive">
                {(error as Error)?.message || "Failed to create person"}
              </p>
            )}
          </div>
        )}

        {!needsFacePick && (
          <DialogFooter>
            <Button variant="ghost" onClick={handleClose} className="text-muted-foreground">
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="bg-annotation text-annotation-foreground hover:bg-annotation/90 gap-2"
            >
              {isPending && <Loader2 size={14} className="animate-spin" />}
              Create Person
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
