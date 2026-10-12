"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MessageCircleQuestion } from "lucide-react";
import { useState } from "react";

export interface AskUserInput {
  question?: string;
  options?: string[];
}

interface AskUserCardProps {
  input: AskUserInput | undefined;
  /** The user's pick once answered; the card then shows it instead of the choices. */
  answer?: string;
  onAnswer: (answer: string) => void;
}

/** The agent's `ask_user` question: pick an option or write your own, and the run resumes. */
export function AskUserCard({ input, answer, onAnswer }: AskUserCardProps) {
  const [other, setOther] = useState("");
  const submitOther = () => other.trim() && onAnswer(other.trim());

  return (
    <div className="rounded-lg border border-border bg-muted/40 p-3 text-sm">
      <p className="flex items-start gap-2 font-medium text-foreground">
        <MessageCircleQuestion className="mt-0.5 size-4 shrink-0 text-primary" />
        {input?.question ?? "The assistant has a question"}
      </p>
      {answer !== undefined ? (
        <p className="mt-2 pl-6 text-muted-foreground">
          You chose: <span className="text-foreground">{answer}</span>
        </p>
      ) : (
        <div className="mt-3 space-y-2 pl-6">
          <div className="flex flex-wrap gap-1.5">
            {(input?.options ?? []).map((option) => (
              <Button
                key={option}
                size="sm"
                variant="outline"
                onClick={() => onAnswer(option)}
                className="h-auto max-w-full whitespace-normal py-1.5 text-left"
              >
                {option}
              </Button>
            ))}
          </div>
          <div className="flex gap-1.5">
            <Input
              value={other}
              onChange={(event) => setOther(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && submitOther()}
              placeholder="Something else…"
              autoComplete="off"
              className="h-8 text-sm"
            />
            <Button size="sm" variant="secondary" onClick={submitOther} disabled={!other.trim()}>
              Answer
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
