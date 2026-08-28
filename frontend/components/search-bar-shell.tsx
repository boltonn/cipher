"use client";

import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import { motion, useMotionTemplate, useMotionValue } from "motion/react";
import { useState } from "react";

export type SearchBarAccent = "indigo" | "annotation";

const ACTIVE_CLASSES: Record<SearchBarAccent, string> = {
  indigo: "bg-primary/5 border-primary/50 shadow-[0_0_25px_rgba(99,102,241,0.2)] ring-1 ring-primary/20",
  annotation: "bg-annotation/5 border-annotation/50 shadow-[0_0_25px_rgba(245,158,11,0.2)] ring-1 ring-annotation/20",
};

const SPINNER_CLASSES: Record<SearchBarAccent, string> = {
  indigo: "text-primary",
  annotation: "text-annotation",
};

const SPOTLIGHT_COLOR: Record<SearchBarAccent, string> = {
  indigo: "var(--primary)",
  annotation: "var(--annotation)",
};

interface SearchBarShellProps {
  /** Loading, dragging, or otherwise "hot" -- swaps the icon for a spinner and shows the glow border. */
  isActive?: boolean;
  accent?: SearchBarAccent;
  icon: React.ReactNode;
  children: React.ReactNode;
  onDragOver?: React.DragEventHandler<HTMLDivElement>;
  onDragLeave?: React.DragEventHandler<HTMLDivElement>;
  onDrop?: React.DragEventHandler<HTMLDivElement>;
  className?: string;
}

/**
 * Shared pill-shaped shell for every search bar in the app (Images, Faces,
 * Persons, Datasets). Bakes in the "active" glow state (loading/dragging)
 * and the same mouse-tracking radial spotlight the app's form `Input`
 * component shows on hover -- previously each page hand-rolled this
 * container and gradually diverged in padding, radius, and shadow.
 *
 * Structure mirrors Input: an outer layer paints the spotlight gradient,
 * a 1px inset inner layer paints the actual pill (solid background, icon,
 * content) on top -- so the spotlight only ever shows as a thin glowing
 * edge, never replacing the pill's own background.
 */
export function SearchBarShell({
  isActive,
  accent = "indigo",
  icon,
  children,
  onDragOver,
  onDragLeave,
  onDrop,
  className,
}: SearchBarShellProps) {
  const radius = 150;
  const [visible, setVisible] = useState(false);
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const handleMouseMove = ({ currentTarget, clientX, clientY }: React.MouseEvent<HTMLDivElement>) => {
    const { left, top } = currentTarget.getBoundingClientRect();
    mouseX.set(clientX - left);
    mouseY.set(clientY - top);
  };

  return (
    <motion.div
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      style={{
        background: useMotionTemplate`radial-gradient(${visible ? radius + "px" : "0px"} circle at ${mouseX}px ${mouseY}px, color-mix(in oklch, ${SPOTLIGHT_COLOR[accent]} 33%, transparent), transparent 70%)`,
      }}
      className={cn("group w-full rounded-2xl p-px transition duration-300", className)}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <div
        className={cn(
          "relative flex items-center w-full rounded-2xl border px-4 transition-all duration-500",
          isActive ? ACTIVE_CLASSES[accent] : "bg-muted/40 border-border group-hover:border-white/20 shadow-xl"
        )}
      >
        <div className="flex items-center justify-center text-muted-foreground pl-1">
          {isActive ? <Loader2 className={cn("h-4 w-4 animate-spin", SPINNER_CLASSES[accent])} /> : icon}
        </div>
        {children}
      </div>
    </motion.div>
  );
}
