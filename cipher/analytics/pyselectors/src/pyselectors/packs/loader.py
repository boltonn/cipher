"""Load and cache selector packs from bundled JSON.

``data/<type>.json`` is the base; ``data/<type>.<iso2>.json`` is an optional
country overlay deep-merged on top when a region is resolved. Everything is
``lru_cache``d, so a pack is parsed and validated exactly once per process.
"""

import functools
import json
from importlib.resources import files

from pyselectors.packs.schema import Pack

_ROOT = files("pyselectors.packs.data")


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        elif isinstance(value, list) and isinstance(out.get(key), list):
            out[key] = out[key] + value
        else:
            out[key] = value
    return out


@functools.cache
def load_pack(selector_type: str, country: str | None = None) -> Pack:
    """Return the validated pack for ``selector_type``, with the ``country`` overlay applied."""
    data = json.loads(_ROOT.joinpath(f"{selector_type}.json").read_text("utf-8"))
    if country:
        overlay = _ROOT.joinpath(f"{selector_type}.{country.lower()}.json")
        if overlay.is_file():
            data = _deep_merge(data, json.loads(overlay.read_text("utf-8")))
    return Pack.model_validate(data)


@functools.lru_cache(maxsize=1)
def available_pack_names() -> tuple[str, ...]:
    """Every ``<type>.json`` base pack shipped in the wheel (no country overlays)."""
    return tuple(
        sorted(p.name[: -len(".json")] for p in _ROOT.iterdir() if p.name.endswith(".json") and "." not in p.name[:-5])
    )
