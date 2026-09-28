"""Blocking keys for entity resolution.

`blocking_keys` returns a small dict of `key_type -> key` for one name string.
`entity_keys` unions those over an entity's display name and aliases into the
`{(key_type, key)}` set that gets materialized in `entity_name_key`.

Two names that share any key are candidate matches; the scorer then decides.
Keys are cheap strings, meant to be indexed and equality-joined.

| key_type | what it catches | selectivity |
|---|---|---|
| `folded` | same script, same spelling | high |
| `translit` | cross-script / romanization variants | high |
| `given_surname` | given + primary surname, patronymic & maternal surname dropped | high |
| `sorted_tokens` | word-order noise (`Bolton Nick` / `Nick Bolton`, `Last, First`) | high |
| `phonetic` | spelling + OCR noise (`Smith`/`Smyth`, `Kowalczuk`/`Kovalchuk`) | medium |
| `surname` | primary (paternal / family) surname alone | low — pair with another signal |
| `initials` | `J.R. Bolton` / `James Robert Bolton` (3+ tokens only) | low — pair with another signal |

The low-selectivity keys stay recall-only: the resolution query drops any
individual key that matches more than a cap of entities in scope, so a name
whose surname is `li` still blocks on its precise keys.
"""

from collections.abc import Iterable

from cipher.names.culture import Culture
from cipher.names.normalize import fold, split_tokens
from cipher.names.parse import parse_name
from cipher.names.phonetic import phonetic_key
from cipher.names.translit import to_latin

__all__ = ["KEYS_VERSION", "KEY_TYPES", "blocking_keys", "entity_keys"]

# Bump when `blocking_keys` output changes so a `backfill-entity-name-keys --rekey`
# run can be triggered after a `cipher-names` upgrade.
KEYS_VERSION = 1

KEY_TYPES = ("folded", "translit", "phonetic", "sorted_tokens", "initials", "surname", "given_surname")

# Upper bound on keys materialized for one entity, so a pathological alias list
# can't bloat `entity_name_key`. Display-name keys are added first and never trimmed.
_MAX_KEYS_PER_ENTITY = 64


def blocking_keys(
    raw: str,
    *,
    culture: Culture | None = None,
    region_hint: str | None = None,
    language: str | None = None,
) -> dict[str, str]:
    """Compute every blocking key for one name string. Empty keys are dropped."""
    folded_tokens = split_tokens(fold(raw))
    latin_tokens = split_tokens(fold(to_latin(raw)))
    folded = " ".join(folded_tokens)
    latin = " ".join(latin_tokens)
    keys: dict[str, str] = {}

    if folded:
        keys["folded"] = folded
    if latin:
        keys["translit"] = latin

    ph = phonetic_key(raw)
    if ph:
        keys["phonetic"] = ph

    if len(latin_tokens) >= 2:
        keys["sorted_tokens"] = " ".join(sorted(latin_tokens))
        initials = "".join(t[0] for t in latin_tokens)
        if len(initials) >= 3:  # 2-letter initials match far too much to be worth an index row
            keys["initials"] = initials

    parsed = parse_name(raw, culture=culture, region_hint=region_hint, language=language)
    primary = fold(to_latin(parsed.primary_surname)) if parsed.primary_surname else ""
    given = fold(to_latin(parsed.given_primary)) if parsed.given_primary else ""
    if primary:
        keys["surname"] = primary
        if given:
            keys["given_surname"] = f"{given} {primary}"

    return {k: v for k, v in keys.items() if v}


def entity_keys(
    display_name: str,
    aliases: Iterable[str] = (),
    *,
    culture: Culture | None = None,
    region_hint: str | None = None,
    language: str | None = None,
) -> set[tuple[str, str]]:
    """The `{(key_type, key)}` set to index for an entity: its display name plus aliases.

    Deterministic and pure. Capped at `_MAX_KEYS_PER_ENTITY`; display-name keys
    are always kept, alias keys fill the remainder in order.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(name: str) -> None:
        for key_type, key in blocking_keys(name, culture=culture, region_hint=region_hint, language=language).items():
            pair = (key_type, key)
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)

    _add(display_name)
    kept = len(pairs)
    for alias in aliases:
        if alias and alias.strip():
            _add(alias)

    if len(pairs) <= _MAX_KEYS_PER_ENTITY:
        return set(pairs)
    return set(pairs[:kept] + pairs[kept:_MAX_KEYS_PER_ENTITY])
