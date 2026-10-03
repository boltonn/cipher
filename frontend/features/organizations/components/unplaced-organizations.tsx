"use client";

import { NameSuggestionDialog } from "@/features/organizations/components/name-suggestion-dialog";
import { NameSuggestionRow } from "@/features/organizations/components/organization-suggestions";
import { useUnplacedNameSuggestions } from "@/features/organizations/hooks/use-organization";
import type { NameSuggestion } from "@/features/organizations/types";
import { Sparkles } from "lucide-react";
import { useState } from "react";

/**
 * Employers that email signatures name but that are not an organization yet (no entity, no resolver
 * guess). Reviewing one creates the organization and settles the person in one step.
 */
export function UnplacedOrganizations() {
  const { data: suggestions = [] } = useUnplacedNameSuggestions();
  const [reviewing, setReviewing] = useState<NameSuggestion | null>(null);
  if (suggestions.length === 0) return null;

  const byOrganization = new Map<string, NameSuggestion[]>();
  for (const s of suggestions) {
    byOrganization.set(s.target.name, [
      ...(byOrganization.get(s.target.name) ?? []),
      s,
    ]);
  }

  return (
    <section className="rounded-xl border border-annotation/40 bg-annotation/5">
      <div className="flex flex-wrap items-center gap-2 border-b border-annotation/30 px-3 py-2 text-xs">
        <Sparkles size={13} className="text-annotation" />
        <span className="font-semibold text-foreground">
          Found in signatures
        </span>
        <span className="text-muted-foreground">
          {byOrganization.size} employers that are not an organization yet —
          review to create them
        </span>
      </div>
      <div className="max-h-80 overflow-y-auto">
        {[...byOrganization].map(([organization, rows]) => (
          <div key={organization}>
            <h3 className="px-3 pb-1 pt-2 text-[11px] font-semibold text-foreground">
              {organization}
            </h3>
            <ul className="divide-y divide-annotation/20">
              {rows.map((s) => (
                <NameSuggestionRow
                  key={s.mentionRelationshipIds[0]}
                  suggestion={s}
                  onReview={() => setReviewing(s)}
                />
              ))}
            </ul>
          </div>
        ))}
      </div>
      <NameSuggestionDialog
        suggestion={reviewing}
        onOpenChange={(open) => !open && setReviewing(null)}
      />
    </section>
  );
}
