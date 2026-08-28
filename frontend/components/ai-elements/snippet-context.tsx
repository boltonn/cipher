"use client";

import { createContext } from "react";

export interface SnippetContextType {
  code: string;
}

export const SnippetContext = createContext<SnippetContextType>({ code: "" });
