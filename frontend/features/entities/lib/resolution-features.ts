import { humanize } from "@/lib/utils";
/**
 * Plain-language glossary for the entity-resolution scorer's signals. Shared by
 * the Resolve queue's feature chips (tooltip) and the /entities/resolution-guide
 * walkthrough. Keys match `ResolutionFeature.name` from the backend
 * (`cipher.orchestration.entity_resolution`).
 */

export interface FeatureMeta {
  /** short label rendered on the chip */
  label: string;
  /** one-sentence definition for the tooltip / guide */
  blurb: string;
  /** true when a `conflict` level on this signal vetoes the whole match */
  veto?: boolean;
}

export const RESOLUTION_FEATURE_META: Record<string, FeatureMeta> = {
  selectorOverlap: {
    label: "shared identifier",
    blurb:
      "This name and the candidate entity appear on the same email address or phone number. Strong evidence, but a shared family mailbox or a role account can put two different people on one address.",
  },
  addressName: {
    label: "address spells name",
    blurb:
      "An email address on one side spells the other side's name — “nbolton04@” for Nick Bolton. Spelling someone else's name (“cbolton@”) counts against, softly: family mailboxes are shared.",
  },
  nameExact: {
    label: "name exact",
    blurb:
      "The two names are identical once case, accents, and punctuation are normalised.",
  },
  nameTranslit: {
    label: "name transliterated",
    blurb:
      "The names match after romanising both to the Latin alphabet — e.g. «Иван Петров» and “Ivan Petrov”.",
  },
  namePhonetic: {
    label: "sounds like",
    blurb:
      "The names don't match as text but sound the same — e.g. a typo like “Cathi Boltn” for “Cathi Bolton”.",
  },
  nameTrigram: {
    label: "name similar",
    blurb:
      "Fuzzy character-overlap similarity between the two strings, when there is no exact, transliterated, or phonetic match.",
  },
  nameStructure: {
    label: "name structure",
    blurb:
      "A culture-aware breakdown of the name into given / surname / patronymic and how well those parts agree. Same surname but a clearly different first name is treated as a conflict — that's usually a relative, not the same person.",
    veto: true,
  },
  attributeAgreement: {
    label: "attributes",
    blurb:
      "A shared date of birth, employer, or nationality. A date-of-birth mismatch vetoes the match.",
    veto: true,
  },
  coMentionPrior: {
    label: "co-mentioned",
    blurb:
      "The name and the candidate entity show up in the same files alongside the same other people — the surrounding cast matches.",
  },
  typeAgreement: {
    label: "type",
    blurb:
      "Both sides are the same kind of thing (both people, or both organisations). A person-vs-organisation mismatch vetoes the match.",
    veto: true,
  },
};

export function featureMeta(name: string): FeatureMeta {
  return (
    RESOLUTION_FEATURE_META[name] ?? {
      label: humanize(name),
      blurb: "",
    }
  );
}
