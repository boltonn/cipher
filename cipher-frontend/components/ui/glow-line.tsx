/**
 * The animated indigo glow-line effect from GradientButton, extracted so
 * other "glassy pill" surfaces (search bars) can share the exact same
 * hover treatment instead of re-implementing it. Needs an ancestor with
 * `group` (or `group/<name>` -- pass `groupName` to match) for the hover
 * trigger.
 */
export function GlowLine({ groupName }: { groupName?: string }) {
  const hoverClass = groupName ? `group-hover/${groupName}:opacity-100` : "group-hover:opacity-100";
  return (
    <>
      <span
        className={`pointer-events-none absolute inset-x-0 -bottom-px block h-px w-full bg-linear-to-r from-transparent via-indigo-500 to-transparent opacity-0 transition duration-500 ${hoverClass}`}
      />
      <span
        className={`pointer-events-none absolute inset-x-10 -bottom-px mx-auto block h-px w-1/2 bg-linear-to-r from-transparent via-indigo-500 to-transparent opacity-0 blur-sm transition duration-500 ${hoverClass}`}
      />
    </>
  );
}
