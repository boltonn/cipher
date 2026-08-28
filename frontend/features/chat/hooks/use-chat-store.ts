import { useEffect, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ChatStore {
  keys: Record<string, string>;
  model: string;
  datasetId?: string;
  setKey: (provider: string, key: string) => void;
  setModel: (model: string) => void;
  setDatasetId: (datasetId: string | undefined) => void;
}

// The server holds a key for this one out of the box (LLM__* env vars); other
// providers need a key added in the model settings popover.
const DEFAULT_MODEL = "google:gemini-2.5-flash";

export const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      keys: {},
      model: DEFAULT_MODEL,
      datasetId: undefined,
      setKey: (provider, key) =>
        set((s) => ({ keys: { ...s.keys, [provider]: key } })),
      setModel: (model) => set({ model }),
      setDatasetId: (datasetId) => set({ datasetId }),
    }),
    {
      name: "chat-config",
      version: 1,
      // v0 shipped a hardcoded OpenAI default that has no server key; move those
      // installs (that never explicitly picked it) onto the server-backed default.
      migrate: (persisted, version) => {
        const state = persisted as ChatStore;
        if (version === 0 && state?.model === "openai:gpt-4o-mini") {
          return { ...state, model: DEFAULT_MODEL };
        }
        return state;
      },
    }
  )
);

// Reusable hook to safe-guard against local-storage flashes/hydration mismatches
export function useChatStoreHydrated() {
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // Check if it already finished or listen to when it finishes
    const checkHydration = () =>
      setHydrated(useChatStore.persist.hasHydrated());

    checkHydration();

    const unsubFinish = useChatStore.persist.onFinishHydration(checkHydration);
    return () => unsubFinish();
  }, []);

  return hydrated;
}
