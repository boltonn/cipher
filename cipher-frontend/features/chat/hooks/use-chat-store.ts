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

export const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      keys: {},
      model: "openai:gpt-4o-mini",
      datasetId: undefined,
      setKey: (provider, key) =>
        set((s) => ({ keys: { ...s.keys, [provider]: key } })),
      setModel: (model) => set({ model }),
      setDatasetId: (datasetId) => set({ datasetId }),
    }),
    { name: "chat-config" }
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
