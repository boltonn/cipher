import type {
  OrganizationSuggestion,
  SuggestionMethod,
} from "@/features/organizations/types";

export const METHOD_LABEL: Record<SuggestionMethod, string> = {
  signature: "email signature",
  emailDomain: "email domain",
  llm: "text extraction",
  coMention: "co-mention",
  selectorInference: "shared selector",
  manual: "manual",
};

const plural = (n: number, word: string) =>
  `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

/** One sentence a reviewer can check: why this suggestion exists. */
export function explainSuggestion(s: OrganizationSuggestion): string {
  const who = s.entity.displayName;
  if (s.relationshipType === "partOf") {
    return `${who} appears as a unit of ${s.unit.displayName} in ${METHOD_LABEL[s.method]}s.`;
  }
  const e = s.explanation;
  if (s.method === "emailDomain" && e) {
    const others = e.otherOrganizations.length
      ? ` (${e.otherOrganizations.map((o) => `${o.name} ${o.signatures}`).join(", ")} otherwise)`
      : "";
    return (
      `${who} sends from @${e.domain} (${plural(e.emailsSent, "email")}), and ` +
      `${e.organizationSignatures} of ${plural(e.domainSignatures, "signature")} from @${e.domain} ` +
      `name ${e.organization}${others}. Their own signature was never read.`
    );
  }
  return `${s.role ? `${s.role} — ` : ""}read from ${who}'s ${METHOD_LABEL[s.method]}.`;
}
