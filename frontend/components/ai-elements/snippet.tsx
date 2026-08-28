"use client";

import {
  InputGroup,
  InputGroupAddon,
  InputGroupText,
} from "@/components/ui/input-group";
import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";
import { useMemo } from "react";

import { SnippetContext } from "./snippet-context";

export type { SnippetContextType } from "./snippet-context";
export { SnippetInput } from "./snippet-input";
export type { SnippetInputProps } from "./snippet-input";
export { SnippetCopyButton } from "./snippet-copy-button";
export type { SnippetCopyButtonProps } from "./snippet-copy-button";

export type SnippetProps = ComponentProps<typeof InputGroup> & {
  code: string;
};

export const Snippet = ({
  code,
  className,
  children,
  ...props
}: SnippetProps) => {
  const contextValue = useMemo(() => ({ code }), [code]);

  return (
    <SnippetContext.Provider value={contextValue}>
      <InputGroup className={cn("font-mono", className)} {...props}>
        {children}
      </InputGroup>
    </SnippetContext.Provider>
  );
};

export type SnippetAddonProps = ComponentProps<typeof InputGroupAddon>;

export const SnippetAddon = (props: SnippetAddonProps) => (
  <InputGroupAddon {...props} />
);

export type SnippetTextProps = ComponentProps<typeof InputGroupText>;

export const SnippetText = ({ className, ...props }: SnippetTextProps) => (
  <InputGroupText
    className={cn("pl-2 font-normal text-muted-foreground", className)}
    {...props}
  />
);
