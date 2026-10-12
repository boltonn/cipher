import { isAxiosError } from "axios";
import { forbidden, notFound, unauthorized } from "next/navigation";

/** Mirrors the backend's `ErrorCode` (`cipher.utils.fastapi.middleware.exceptions`), plus `network`. */
export type ApiErrorCode =
  | "unauthorized"
  | "forbidden"
  | "notFound"
  | "conflict"
  | "invalid"
  | "unavailable"
  | "serverError"
  | "error"
  | "network";

/** Codes that mean "this page can't be shown" -- a query failing with one renders the matching status page. */
export const PAGE_ERROR_CODES: ReadonlySet<ApiErrorCode> = new Set(["unauthorized", "forbidden", "notFound"]);

const CODE_BY_STATUS: Record<number, ApiErrorCode> = {
  401: "unauthorized",
  403: "forbidden",
  404: "notFound",
  409: "conflict",
  422: "invalid",
  503: "unavailable",
};

/** The API error code carried by any thrown value, or `undefined` when it isn't an API error. */
export function apiErrorCode(error: unknown): ApiErrorCode | undefined {
  if (!isAxiosError(error)) return undefined;
  if (!error.response) return "network";
  const code = (error.response.data as { code?: unknown } | undefined)?.code;
  if (typeof code === "string") return code as ApiErrorCode;
  const status = error.response.status;
  return CODE_BY_STATUS[status] ?? (status >= 500 ? "serverError" : "error");
}

/**
 * Whether a failed request should replace the page with a status page: a read (GET) that came
 * back unauthorized/forbidden/not found and that the caller didn't mark as expected.
 */
export function isPageError(error: unknown): boolean {
  if (!isAxiosError(error) || error.config?.suppressErrorToast) return false;
  if ((error.config?.method ?? "get").toLowerCase() !== "get") return false;
  const code = apiErrorCode(error);
  if (code === "notFound" && error.config?.expectNotFound) return false;
  return code !== undefined && PAGE_ERROR_CODES.has(code);
}

const INTERRUPTS: Partial<Record<ApiErrorCode, () => never>> = {
  notFound: notFound,
  forbidden,
  unauthorized,
};

/**
 * The Next.js interrupt for a page error -- thrown during render it shows `not-found.tsx` /
 * `forbidden.tsx` / `unauthorized.tsx`, without the error logging a plain thrown error gets.
 */
export function toPageInterrupt(error: unknown): unknown {
  const interrupt = INTERRUPTS[apiErrorCode(error) ?? "error"];
  if (!interrupt) return error;
  try {
    interrupt();
  } catch (thrown) {
    return thrown;
  }
  return error;
}

/** Whether a thrown value is one of the interrupts from `toPageInterrupt`. */
export function isPageInterrupt(error: unknown): boolean {
  const digest = (error as { digest?: unknown } | null)?.digest;
  return typeof digest === "string" && digest.startsWith("NEXT_HTTP_ERROR_FALLBACK;");
}
