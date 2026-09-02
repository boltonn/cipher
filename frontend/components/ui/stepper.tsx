"use client";

import * as React from "react";

import { cn } from "@/lib/utils";
import { CheckIcon, Loader2Icon, TriangleAlertIcon } from "lucide-react";

type Orientation = "horizontal" | "vertical";

interface StepperContextValue {
  value: number;
  setValue?: (value: number) => void;
  orientation: Orientation;
}

const StepperContext = React.createContext<StepperContextValue | null>(null);

function useStepper() {
  const context = React.use(StepperContext);
  if (!context) {
    throw new Error("Stepper.* must be used within <Stepper>");
  }
  return context;
}

interface StepItemContextValue {
  step: number;
  state: "active" | "completed" | "failed" | "loading" | "inactive";
  disabled: boolean;
}

const StepItemContext = React.createContext<StepItemContextValue | null>(null);

function useStepItem() {
  const context = React.use(StepItemContext);
  if (!context) {
    throw new Error("StepperItem children must be used within <StepperItem>");
  }
  return context;
}

function Stepper({
  value,
  onValueChange,
  orientation = "horizontal",
  className,
  ...props
}: React.ComponentProps<"div"> & {
  value: number;
  onValueChange?: (value: number) => void;
  orientation?: Orientation;
}) {
  const context = React.useMemo(
    () => ({ value, setValue: onValueChange, orientation }),
    [value, onValueChange, orientation]
  );

  return (
    <StepperContext value={context}>
      <div
        data-slot="stepper"
        data-orientation={orientation}
        className={cn(
          "group/stepper",
          orientation === "vertical" ? "flex flex-col" : "flex w-full",
          className
        )}
        {...props}
      />
    </StepperContext>
  );
}

function StepperNav({ className, ...props }: React.ComponentProps<"div">) {
  const { orientation } = useStepper();
  return (
    <div
      data-slot="stepper-nav"
      className={cn(
        "flex w-full",
        orientation === "vertical" ? "flex-col" : "items-center",
        className
      )}
      {...props}
    />
  );
}

function StepperItem({
  step,
  completed = false,
  failed = false,
  loading = false,
  disabled = false,
  className,
  ...props
}: React.ComponentProps<"div"> & {
  step: number;
  completed?: boolean;
  /** Status use: this step errored. Wins over `completed`. */
  failed?: boolean;
  /** Status use: this step is in progress. */
  loading?: boolean;
  disabled?: boolean;
}) {
  const { value, orientation } = useStepper();
  const state: StepItemContextValue["state"] = failed
    ? "failed"
    : completed
      ? "completed"
      : loading
        ? "loading"
        : value === step
          ? "active"
          : "inactive";

  const context = React.useMemo(
    () => ({ step, state, disabled }),
    [step, state, disabled]
  );

  return (
    <StepItemContext value={context}>
      <div
        data-slot="stepper-item"
        data-state={state}
        className={cn(
          "group/step",
          orientation === "vertical" ? "w-full" : "flex items-center not-last:flex-1",
          className
        )}
        {...props}
      />
    </StepItemContext>
  );
}

function StepperTrigger({
  className,
  children,
  ...props
}: React.ComponentProps<"button">) {
  const { setValue } = useStepper();
  const { step, disabled } = useStepItem();

  return (
    <button
      type="button"
      data-slot="stepper-trigger"
      disabled={disabled || !setValue}
      onClick={() => setValue?.(step)}
      className={cn(
        "flex items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
        setValue && "cursor-pointer",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function StepperIndicator({
  className,
  children,
  ...props
}: React.ComponentProps<"span">) {
  const { step, state } = useStepItem();

  return (
    <span
      data-slot="stepper-indicator"
      data-state={state}
      className={cn(
        "flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-mono font-semibold transition-colors",
        "border-border bg-muted/40 text-muted-foreground",
        "group-data-[state=active]/step:border-primary group-data-[state=active]/step:bg-primary/10 group-data-[state=active]/step:text-primary",
        "group-data-[state=loading]/step:border-primary group-data-[state=loading]/step:bg-primary/10 group-data-[state=loading]/step:text-primary",
        "group-data-[state=completed]/step:border-primary group-data-[state=completed]/step:bg-primary group-data-[state=completed]/step:text-white",
        "group-data-[state=failed]/step:border-destructive/40 group-data-[state=failed]/step:bg-destructive/10 group-data-[state=failed]/step:text-destructive",
        className
      )}
      {...props}
    >
      {children ??
        (state === "completed" ? (
          <CheckIcon className="size-3.5" />
        ) : state === "failed" ? (
          <TriangleAlertIcon className="size-3.5" />
        ) : state === "loading" ? (
          <Loader2Icon className="size-3.5 animate-spin" />
        ) : (
          step
        ))}
    </span>
  );
}

function StepperSeparator({ className, ...props }: React.ComponentProps<"div">) {
  const { orientation } = useStepper();
  return (
    <div
      data-slot="stepper-separator"
      className={cn(
        "bg-border transition-colors",
        "group-data-[state=completed]/step:bg-primary/60 group-data-[state=failed]/step:bg-destructive/40",
        orientation === "vertical" ? "mx-3 min-h-4 w-px flex-1" : "mx-3 h-px flex-1",
        className
      )}
      {...props}
    />
  );
}

function StepperTitle({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="stepper-title"
      className={cn(
        "text-[10px] font-black uppercase tracking-[0.15em] text-muted-foreground transition-colors",
        "group-data-[state=active]/step:text-foreground group-data-[state=completed]/step:text-foreground",
        "group-data-[state=loading]/step:text-foreground group-data-[state=failed]/step:text-destructive",
        className
      )}
      {...props}
    />
  );
}

function StepperDescription({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="stepper-description"
      className={cn("text-xs text-muted-foreground", className)}
      {...props}
    />
  );
}

export {
  Stepper,
  StepperNav,
  StepperItem,
  StepperTrigger,
  StepperIndicator,
  StepperSeparator,
  StepperTitle,
  StepperDescription,
};
