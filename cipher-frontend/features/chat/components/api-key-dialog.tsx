"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
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
import { Input } from "@/components/ui/input";
import {
  Snippet,
  SnippetCopyButton,
  SnippetInput,
} from "@/components/ai-elements/snippet";
import { useState } from "react";
import { useChatStore } from "../hooks/use-chat-store";

interface ApiKeyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ApiKeyDialog({ open, onOpenChange }: ApiKeyDialogProps) {
  const { keys, model, setKey } = useChatStore();

  const provider = model.split(":")[0];
  const currentKey = keys[provider] ?? "";

  const [value, setValue] = useState(currentKey);

  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) setValue(keys[provider] ?? "");
    onOpenChange(nextOpen);
  };

  const handleSave = () => {
    setKey(provider, value);
    onOpenChange(false);
  };

  const handleClear = () => {
    setKey(provider, "");
    setValue("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>API Key</DialogTitle>
          <DialogDescription>
            Your key is stored locally and sent only with your requests.
          </DialogDescription>
        </DialogHeader>

        <FieldGroup>
          {currentKey && (
            <Field>
              <FieldLabel className="capitalize">
                Current {provider} key
              </FieldLabel>
              <Snippet code={currentKey}>
                <SnippetInput type="password" />
                <SnippetCopyButton />
              </Snippet>
            </Field>
          )}

          <Field>
            <FieldLabel htmlFor="api-key" className="capitalize">
              {currentKey ? "Replace" : "Enter"} {provider} API key
            </FieldLabel>
            <Input
              id="api-key"
              type="password"
              placeholder="sk-..."
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </Field>
        </FieldGroup>

        <DialogFooter className="gap-2">
          {currentKey && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" className="mr-auto text-destructive hover:text-destructive">
                  Clear key
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Clear API key?</AlertDialogTitle>
                  <AlertDialogDescription>
                    The saved {provider} key will be removed from local storage.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleClear}>
                    Clear
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
          <Button onClick={handleSave}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
