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
        background: useMotionTemplate`radial-gradient(${visible ? radius + "px" : "0px"} circle at ${mouseX}px ${mouseY}px, #6366f1, transparent 80%)`,
      }}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      className="group/input rounded-lg p-0.5 transition duration-300"
    >
      <textarea
        data-slot="textarea"
        className={cn(
          "shadow-input flex w-full rounded-md border-none bg-gray-50 px-3 py-2 text-sm text-black transition duration-400 placeholder:text-neutral-400 focus-visible:ring-2 focus-visible:ring-indigo-500/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:bg-neutral-900 dark:text-neutral-100 dark:shadow-[0px_0px_1px_1px_#1a1a1a] dark:placeholder-neutral-600 dark:focus-visible:ring-indigo-500/50 resize-none",
          className
        )}
        {...props}
      />
    </motion.div>
  );
}

export { Textarea };
