"use client";

import { cn } from "@/lib/utils";
import { motion, useMotionTemplate, useMotionValue } from "motion/react";
import * as React from "react";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  const radius = 100;
  const [visible, setVisible] = React.useState(false);
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  function handleMouseMove({ currentTarget, clientX, clientY }: React.MouseEvent<HTMLDivElement>) {
    const { left, top } = (currentTarget as HTMLDivElement).getBoundingClientRect();
    mouseX.set(clientX - left);
    mouseY.set(clientY - top);
  }

  return (
    <motion.div
      style={{
        background: useMotionTemplate`radial-gradient(${visible ? radius + "px" : "0px"} circle at ${mouseX}px ${mouseY}px, color-mix(in oklch, var(--primary) 33%, transparent), transparent 70%)`,
      }}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      className="group/input w-full rounded-lg p-px transition duration-300"
    >
      <textarea
        data-slot="textarea"
        className={cn(
          "flex w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm text-foreground transition duration-400 placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 resize-none",
          className
        )}
        autoComplete="off"
        {...props}
      />
    </motion.div>
  );
}

export { Textarea };
