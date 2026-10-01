const EDGE_PUNCT = /^['"`‘’“”.,;:()<>[\]_\- ]+|['"`‘’“”.,;:()<>[\]_\- ]+$/g;

/** Client mirror of the backend's `normalize_name` -- the name-group key a drawn span joins ("Nick B." -> "nick b"). */
export function foldName(value: string) {
  const folded = value
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
  return folded.replace(EDGE_PUNCT, "") || folded;
}
