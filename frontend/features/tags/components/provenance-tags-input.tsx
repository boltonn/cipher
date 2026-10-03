"use client";

import { TagsInput } from "@/components/tags-input";
import type { ComponentProps } from "react";
import { useTagProvenance } from "../hooks/use-tag-provenance";
import type { TagTarget } from "../types";

type ProvenanceTagsInputProps = Omit<
  ComponentProps<typeof TagsInput>,
  "describeTag" | "confirmRemove"
> & {
  /** The tagged thing; omit for something not created yet (no history to show). */
  target?: TagTarget;
};

/** `TagsInput` that shows who/what set each tag and confirms before removing another user's. */
export function ProvenanceTagsInput({
  target,
  ...props
}: ProvenanceTagsInputProps) {
  const provenance = useTagProvenance(target);
  return <TagsInput {...props} {...provenance} />;
}
