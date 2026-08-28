"use client";
import { useCallback, useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
const parseCache = new Map<string, { raw: string | null; parsed: unknown }>();

function emit() {
  for (const l of listeners) l();
}

function snapshot<T>(key: string, fallback: T): T {
  const raw = typeof window === "undefined" ? null : window.localStorage.getItem(key);
  const cached = parseCache.get(key);
  if (cached && cached.raw === raw) return cached.parsed as T;
  let parsed: T = fallback;
  if (raw !== null) {
    try {
      parsed = JSON.parse(raw) as T;
    } catch {
      parsed = fallback;
    }
  }
  parseCache.set(key, { raw, parsed });
  return parsed;
}

/**
 * `useState` that persists to `localStorage` under `key`. SSR-safe: the server
 * and first client render both see `initialValue`, then the stored value is
 * adopted without a hydration mismatch. Writes sync across hooks and tabs.
 * Storage failures (private mode, quota) are swallowed -- the value just doesn't
 * persist.
 */
export function useLocalStorageState<T>(key: string, initialValue: T) {
  const value = useSyncExternalStore(
    useCallback((cb: () => void) => {
      listeners.add(cb);
      const onStorage = (e: StorageEvent) => {
        if (e.key === key) emit();
      };
      window.addEventListener("storage", onStorage);
      return () => {
        listeners.delete(cb);
        window.removeEventListener("storage", onStorage);
      };
    }, [key]),
    () => snapshot(key, initialValue),
    () => initialValue
  );

  const setValue = useCallback(
    (next: T | ((prev: T) => T)) => {
      const resolved =
        typeof next === "function"
          ? (next as (prev: T) => T)(snapshot(key, initialValue))
          : next;
      try {
        window.localStorage.setItem(key, JSON.stringify(resolved));
      } catch {
        // storage unavailable -- preference is in-memory only for this session
      }
      parseCache.set(key, { raw: JSON.stringify(resolved), parsed: resolved });
      emit();
    },
    [key, initialValue]
  );

  return [value, setValue] as const;
}
