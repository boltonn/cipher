"""Coerce a raw attribute dict into the flat ``dict[str, str]`` that lands in JSONB."""

from cipher.schemas.graph.ontology import SelectorType


def coerce(selector_type: SelectorType, raw: dict) -> dict[str, str]:
    """Drop None values and stringify everything else."""
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None or value == "":
            continue
        out[str(key)] = value if isinstance(value, str) else str(value)
    return out
