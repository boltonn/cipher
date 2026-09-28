import axios, { AxiosError } from "axios";
import { toast } from "sonner";

declare module "axios" {
  interface AxiosRequestConfig {
    /**
     * Skip the global error toast for this request (e.g. an expected/benign
     * 404, or an optional integration that returns 503 when unconfigured).
     * Also downgrades the dev console log from `error` to `debug` so an
     * already-handled failure doesn't surface as a Console Error.
     */
    suppressErrorToast?: boolean;
  }
}

export const baseURL =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"
    : process.env.NEXT_PUBLIC_API_URL || "/api";

export const apiClient = axios.create({
  baseURL,
  headers: {
    "Content-Type": "application/json",
  },
  // Serialize array query params as repeated keys (`?tag=a&tag=b`), which is what
  // FastAPI's `list[str]` query fields expect. Axios's default (`tag[]=a&tag[]=b`)
  // is silently dropped server-side.
  paramsSerializer: { indexes: null },
});

/** Server `detail` strings that carry an internal failure verbatim -- an ORM
 *  exception, a driver error, a stack trace. These must never reach a toast. */
const LEAKED_INTERNALS =
  /traceback|sqlalchemy|asyncpg|psycopg|\bselect .+ from \b|\bat 0x[0-9a-f]+|\n\s+file "/i;

/**
 * Turn an axios error into one short sentence a user can act on. The raw
 * `detail` from the API is only used when it's plainly a human-written
 * message; anything long, multi-line, or carrying an internal exception is
 * replaced with a generic line and logged to the console for debugging.
 */
function humanErrorMessage(error: AxiosError): string {
  if (error.code === "ERR_NETWORK" || !error.response) {
    return "Can’t reach the server. Check your connection and try again.";
  }

  const status = error.response.status;
  const data = error.response.data as
    | { detail?: unknown; message?: unknown }
    | undefined;
  const raw =
    typeof data?.detail === "string"
      ? data.detail
      : typeof data?.message === "string"
        ? data.message
        : "";

  const usable =
    raw &&
    raw.length <= 200 &&
    !raw.includes("\n") &&
    !LEAKED_INTERNALS.test(raw);

  if (usable) return raw;
  if (status >= 500)
    return "Something went wrong on the server. Try again in a moment.";
  if (status === 404) return "Not found.";
  if (status === 403) return "You don’t have access to that.";
  if (status === 401) return "Your session has expired. Sign in again.";
  return "That request couldn’t be completed.";
}

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Keep the full error for developers, but downgrade to `debug` when the
    // caller has already said it's expected -- a suppressed error shouldn't
    // trip Next's Console Error overlay.
    if (typeof window !== "undefined") {
      const log = error.config?.suppressErrorToast
        ? console.debug
        : console.error;
      log(
        "[api]",
        error.config?.method?.toUpperCase(),
        error.config?.url,
        error.response?.status,
        error.response?.data ?? error.message
      );
    }
    if (!error.config?.suppressErrorToast) {
      toast.error(humanErrorMessage(error));
    }
    return Promise.reject(error);
  }
);
