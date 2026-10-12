/** What a tag is on: file bytes by sha256 (images + every copy of a file), any entity, or an event. */
export type TagTargetType = "content" | "entity" | "event";

export interface TagTarget {
  targetType: TagTargetType;
  /** sha256 for content (an image's id); the entity / event id otherwise. */
  targetId: string;
}

/** Whether an image tag has enough analyst labels to train its classifier head (admin). */
export interface TagTrainingReadiness {
  tag: string;
  /** Images an analyst labelled with the tag. */
  positives: number;
  /** Images an analyst said are not the tag. */
  negatives: number;
  /** Positives a head needs before training includes the tag. */
  minPositives: number;
  isReady: boolean;
}

/** How one tag is used on one kind of target (`TagStats`). */
export interface TagStats {
  tag: string;
  targetType: TagTargetType;
  /** Targets an analyst labelled with the tag. */
  labelled: number;
  /** Targets an analyst said are not the tag. */
  rejected: number;
  /** Targets a model tagged or scored. */
  predicted: number;
  /** Of the analyst labels, how many are yours. */
  byYou: number;
  dateLastUsed: string;
}

export interface Tag extends TagTarget {
  id: string;
  tag: string;
  label: "positive" | "negative" | null;
  score: number | null;
  sourceType: "user" | "model";
  /** User id for a user, model name/version for a model. */
  sourceName: string;
  sourceDisplayName: string;
  dateUpdated: string;
}

/** How a tag filter matches: labelled this, labelled not this, or a model prediction nobody labelled yet. */
export type TagFilterState = "positive" | "negative" | "predicted";

/** Tag filters split by state -- the same fields the backend search params take. */
export interface TagFilterValue {
  tags?: string[];
  negativeTags?: string[];
  predictedTags?: string[];
}
