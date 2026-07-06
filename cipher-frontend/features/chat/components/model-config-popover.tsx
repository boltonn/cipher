"use client";

import {
  EnvironmentVariable,
  EnvironmentVariables,
  EnvironmentVariablesContent,
  EnvironmentVariablesHeader,
  EnvironmentVariablesTitle,
  EnvironmentVariablesToggle,
} from "@/components/ai-elements/environment-variables";
import { PromptInputButton } from "@/components/ai-elements/prompt-input";
import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Settings2Icon } from "lucide-react";
import { useState } from "react";
import { useChatStore } from "../hooks/use-chat-store";
// Planned: replace Select with Combobox for searchable model picker
const _modelCombobox = Combobox;

const MODELS = [
  { id: "openai:gpt-4o-mini", label: "GPT-4o Mini", provider: "openai" },
  { id: "openai:gpt-4o", label: "GPT-4o", provider: "openai" },
  {
    id: "anthropic:claude-haiku-4-5-20251001",
    label: "Claude Haiku",
    provider: "anthropic",
  },
  {
    id: "anthropic:claude-sonnet-4-5",
    label: "Claude Sonnet",
    provider: "anthropic",
  },
  {
    id: "google:gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    provider: "google",
  },
  {
    id: "google:gemini-2.5-flash-lite",
    label: "Gemini 2.5 Flash Lite",
    provider: "google",
  },
  { id: "google:gemini-2.5-pro", label: "Gemini 2.5 Pro", provider: "google" },
];

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
};

export function ModelConfigPopover() {
  const { keys, model, setKey, setModel } = useChatStore();
  const [open, setOpen] = useState(false);

  // Initialize directly from master store data
  const [draftModel, setDraftModel] = useState(model);
  const [draftKeys, setDraftKeys] = useState<Record<string, string>>(keys);

  const draftProvider = draftModel.split(":")[0];

  // Intercept open toggle events directly inside the standard event loop
  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) {
      // Whenever the user pops the menu open, reset local drafts to current true values
      setDraftModel(model);
      setDraftKeys(keys);
    }
    setOpen(nextOpen);
  };

  const handleSave = () => {
    // 1. Commit draft configurations down to master state storage
    setModel(draftModel);
    Object.entries(draftKeys).forEach(([provider, key]) => {
      setKey(provider, key);
    });

    // 2. Shut the panel window down cleanly
    setOpen(false);
  };

  const currentModelLabel = MODELS.find((m) => m.id === model)?.label ?? model;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <PromptInputButton
          tooltip={{ content: "Model & API keys" }}
          variant="ghost"
          className="gap-1.5"
        >
          <Settings2Icon size={14} />
          <span className="text-xs text-muted-foreground">
            {currentModelLabel}
          </span>
        </PromptInputButton>
      </PopoverTrigger>

      <PopoverContent className="w-140 p-4 space-y-4" align="start" side="top">
        <div className="space-y-1.5">
          <Label>Model</Label>
          <Select value={draftModel} onValueChange={setDraftModel}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.keys(PROVIDER_LABELS).map((provider) => (
                <div key={provider}>
                  <p className="px-2 pt-2 pb-1 text-xs font-medium text-muted-foreground">
                    {PROVIDER_LABELS[provider]}
                  </p>
                  {MODELS.flatMap((m) =>
                    m.provider === provider
                      ? [
                          <SelectItem key={m.id} value={m.id}>
                            {m.label}
                          </SelectItem>,
                        ]
                      : []
                  )}
                </div>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label>{PROVIDER_LABELS[draftProvider]} API Key</Label>
          <Input
            type="password"
            placeholder={`Enter ${PROVIDER_LABELS[draftProvider]} key...`}
            value={draftKeys[draftProvider] ?? ""}
            onChange={(e) =>
              setDraftKeys((k) => ({ ...k, [draftProvider]: e.target.value }))
            }
          />
          <p className="text-xs text-muted-foreground">
            Stored locally. Switch model to set a different provider&apos;s key.
          </p>
        </div>

        {Object.entries(keys).filter(([, v]) => v).length > 0 && (
          <EnvironmentVariables>
            <EnvironmentVariablesHeader>
              <EnvironmentVariablesTitle>Saved keys</EnvironmentVariablesTitle>
              <EnvironmentVariablesToggle />
            </EnvironmentVariablesHeader>
            <EnvironmentVariablesContent>
              {Object.entries(keys).flatMap(([p, v]) =>
                v
                  ? [
                      <EnvironmentVariable
                        key={p}
                        name={`${p.toUpperCase()}_API_KEY`}
                        value={v}
                      />,
                    ]
                  : []
              )}
            </EnvironmentVariablesContent>
          </EnvironmentVariables>
        )}

        <Button onClick={handleSave} className="w-full">
          Save
        </Button>
      </PopoverContent>
    </Popover>
  );
}
