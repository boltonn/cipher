import { Mail } from "lucide-react";

/** Named in an email's from / to / cc header -- a fact from the data, so neutral (not annotation) colour. */
export function CorrespondentBadge() {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border/60 px-1.5 text-[11px] text-muted-foreground"
      title="Named in an email's from / to / cc header. Correspondents are listed first."
    >
      <Mail size={10} aria-hidden /> Correspondent
    </span>
  );
}
