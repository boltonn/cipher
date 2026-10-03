/** Thin horizontal bar showing `value` as a share of `total`. */
export function ShareBar({ value, total }: { value: number; total: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full min-w-0.5 rounded-full bg-primary/70"
        style={{ width: `${total > 0 ? Math.min((value / total) * 100, 100) : 0}%` }}
      />
    </div>
  );
}
