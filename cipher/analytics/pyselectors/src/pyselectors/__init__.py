"""Deterministic selector extraction for the CIPHER entity layer."""

from pyselectors.extract import extract_selectors
from pyselectors.schemas import SelectorSpan

__all__ = ["SelectorSpan", "extract_selectors"]
