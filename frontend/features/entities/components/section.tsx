import type { ReactNode } from "react";

/** Shared uppercase section header used across the entity and person dossiers. */
export function Section({
  id,
  title,
  icon,
  action,
  children,
}: {
  id?: string;
  title: string;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <div className="mb-3 flex items-center gap-2">
        {icon}
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-foreground">
          {title}
        </h2>
        {action && <div className="ml-auto">{action}</div>}
      </div>
      {children}
    </section>
  );
}
