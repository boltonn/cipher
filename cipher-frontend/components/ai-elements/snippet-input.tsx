"use client";

import {
  InputGroupInput,
} from "@/components/ui/input-group";
import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";
import { use } from "react";

import { SnippetContext } from "./snippet-context";

export type SnippetInputProps = Omit<
  ComponentProps<typeof InputGroupInput>,
  "readOnly" | "value"
>;

export const SnippetInput = ({ className, ...props }: SnippetInputProps) => {
  const { code } = use(SnippetContext);

  return (
    <InputGroupInput
      className={cn("text-foreground", className)}
      readOnly
      value={code}
      {...props}
    />
  );
};
