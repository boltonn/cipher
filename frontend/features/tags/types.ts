/** What a tag is on: file bytes by sha256 (images + every copy of a file), any entity, or an event. */
export type TagTargetType = "content" | "entity" | "event";

export interface TagTarget {
  targetType: TagTargetType;
  /** sha256 for content (an image's id); the entity / event id otherwise. */
  targetId: string;
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
