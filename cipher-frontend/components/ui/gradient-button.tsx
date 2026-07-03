"use client";

import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

const BottomGradient = () => (
  <>
    <span className="absolute inset-x-0 -bottom-px block h-px w-full bg-linear-to-r from-transparent via-indigo-500 to-transparent opacity-0 transition duration-500 group-hover/btn:opacity-100" />
    <span className="absolute inset-x-10 -bottom-px mx-auto block h-px w-1/2 bg-linear-to-r from-transparent via-indigo-500 to-transparent opacity-0 blur-sm transition duration-500 group-hover/btn:opacity-100" />
  </>
);

interface GradientButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading?: boolean;
  loadingText?: string;
}

export function GradientButton({
  children,
  className,
  disabled,
  isLoading,
  loadingText,
  ...props
}: GradientButtonProps) {
  return (
    <button
      disabled={disabled || isLoading}
      className={cn(
        "group/btn relative flex h-10 w-full items-center justify-center rounded-md bg-linear-to-br from-black to-neutral-600 font-medium text-white shadow-[0px_1px_0px_0px_#ffffff40_inset,0px_-1px_0px_0px_#ffffff40_inset] disabled:opacity-50 dark:from-neutral-800 dark:to-neutral-900 dark:shadow-[0px_1px_0px_0px_#ffffff12_inset,0px_-1px_0px_0px_#ffffff08_inset]",
        className
      )}
      {...props}
    >
      {isLoading ? (
        <>
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
          {loadingText ?? "Loading…"}
        </>
      ) : (
        children
      )}
      <BottomGradient />
    </button>
  );
}
