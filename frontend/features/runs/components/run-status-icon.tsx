import type { RunStatus } from "@/features/runs/types";
import { AlertTriangle, Ban, Check, CirclePause, Clock, Loader2 } from "lucide-react";

/** One icon per plan-step status, in the pipeline's own icon language. */
export const RUN_STATUS_ICON: Record<RunStatus, React.ReactNode> = {
  queued: <Clock className="size-3.5 text-muted-foreground" />,
  running: <Loader2 className="size-3.5 animate-spin text-primary" />,
  cancelling: <Loader2 className="size-3.5 animate-spin text-muted-foreground" />,
  cancelled: <Ban className="size-3.5 text-muted-foreground" />,
  completed: <Check className="size-3.5 text-primary" />,
  failed: <AlertTriangle className="size-3.5 text-destructive" />,
  stopped: <CirclePause className="size-3.5 text-muted-foreground" />,
};

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  cancelling: "Stopping",
  cancelled: "Cancelled",
  completed: "Done",
  failed: "Failed",
  stopped: "Stopped",
};
