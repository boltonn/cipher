"use client";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { AtSign, Search, UserRound } from "lucide-react";
import { useState } from "react";
import type { NameChoice } from "../types";

interface NameChoicesProps {
  choices: NameChoice[];
  /** One group of entity ids per name, in `choices` order (empty groups dropped). */
  onSearch: (entityGroups: string[][]) => void;
}

/** "Who do you mean by …?" -- tick the people, spellings and addresses a typed name should cover. */
export function NameChoices({ choices, onSearch }: NameChoicesProps) {
  const [ticked, setTicked] = useState(() =>
    choices.map((choice) => new Set(choice.options.flatMap((option, index) => (option.isSuggested ? [index] : []))))
  );
  const toggle = (choiceIndex: number, optionIndex: number) =>
    setTicked((previous) =>
      previous.map((set, index) => {
        if (index !== choiceIndex) return set;
        const next = new Set(set);
        if (!next.delete(optionIndex)) next.add(optionIndex);
        return next;
      })
    );
  const groups = choices
    .map((choice, index) => [...ticked[index]].flatMap((optionIndex) => choice.options[optionIndex].entityIds))
    .filter((group) => group.length > 0);

  return (
    <div className="space-y-3">
      {choices.map((choice, choiceIndex) => (
        <fieldset key={choice.name} className="space-y-1.5">
          <legend className="text-xs text-muted-foreground">
            Who do you mean by <span className="font-medium text-foreground">“{choice.name}”</span>? Ticked ones
            are searched as the same person.
          </legend>
          <div className="flex flex-wrap gap-1.5">
            {choice.options.map((option, optionIndex) => {
              const checked = ticked[choiceIndex].has(optionIndex);
              const Icon = option.entityType === "selector" ? AtSign : UserRound;
              return (
                <label
                  key={option.entityIds.join()}
                  className={cn(
                    "flex h-7 cursor-pointer items-center gap-1.5 rounded-full border px-2.5 text-xs",
                    checked ? "border-annotation/50 bg-annotation/10" : "border-border hover:bg-muted"
                  )}
                >
                  <Checkbox checked={checked} onCheckedChange={() => toggle(choiceIndex, optionIndex)} />
                  <Icon className="size-3.5 text-muted-foreground" />
                  <span className="max-w-56 truncate text-foreground">{option.displayName}</span>
                  {option.detail && <span className="text-muted-foreground">· {option.detail}</span>}
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="h-7 gap-1.5 border-annotation/40 text-xs hover:bg-annotation/10"
        disabled={groups.length === 0}
        onClick={() => onSearch(groups)}
      >
        <Search className="size-3.5 text-annotation" /> Search with the ticked ones
      </Button>
    </div>
  );
}
