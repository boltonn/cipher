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
import { useAgentConfig } from "../api";
import { useChatStore } from "../hooks/use-chat-store";
import { useModelOptions } from "../hooks/use-model-options";
import { PROVIDER_LABELS } from "../lib/models";
// Planned: replace Select with Combobox for searchable model picker
const _modelCombobox = Combobox;

export function ModelConfigPopover() {
  const { keys, model: storedModel, setKey, setModel } = useChatStore();
  const { options, labelFor, effectiveModel } = useModelOptions();
  const model = effectiveModel(storedModel);
  const [open, setOpen] = useState(false);

  // Initialize directly from master store data
  const [draftModel, setDraftModel] = useState(model);
  const [draftKeys, setDraftKeys] = useState<Record<string, string>>(keys);

  const draftProvider = draftModel.split(":")[0];

  const { data: agentConfig } = useAgentConfig();
  const serverHasKeyForDraft =
    agentConfig?.models.find((m) => m.id === draftModel)?.hasKey ?? false;

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

  const currentModelLabel = labelFor(model);

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
                  {options.flatMap((m) =>
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

        {draftProvider === "local" ? (
          <p className="text-xs text-muted-foreground">
            Runs against the vLLM server on your machine (localhost:8002) — no
            API key needed.
          </p>
        ) : (
          <div className="space-y-1.5">
            <Label>{PROVIDER_LABELS[draftProvider]} API Key</Label>
            <Input
              type="password"
              placeholder={
                serverHasKeyForDraft
                  ? "Server has a key — leave blank to use it"
                  : `Enter ${PROVIDER_LABELS[draftProvider]} key...`
              }
              value={draftKeys[draftProvider] ?? ""}
              onChange={(e) =>
                setDraftKeys((k) => ({ ...k, [draftProvider]: e.target.value }))
              }
            />
            <p className="text-xs text-muted-foreground">
              {serverHasKeyForDraft
                ? "The server already has a key for this model and uses it automatically. A key saved here is only used for providers the server can't cover."
                : "Stored locally. Switch model to set a different provider's key."}
            </p>
          </div>
        )}

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
