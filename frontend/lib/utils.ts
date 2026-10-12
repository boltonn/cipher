import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Readable label for an API vocabulary value: "socialHandle" / "social_handle" -> "social handle" */
export function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/([a-z0-9])([A-Z])/g, (_, a: string, b: string) => `${a} ${b.toLowerCase()}`);
}

/** Human-readable file size, e.g. formatBytes(957466189) -> "957.5 MB" */
export function formatBytes(bytes: number, decimals = 1): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1
  );
  const value = bytes / Math.pow(1024, exponent);
  return `${value.toFixed(exponent === 0 ? 0 : decimals)} ${units[exponent]}`;
}

/** Compact rounded count, e.g. formatCompactNumber(957466189) -> "957.5M" */
export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}
