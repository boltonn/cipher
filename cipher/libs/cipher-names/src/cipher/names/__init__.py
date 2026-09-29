"""Multilingual personal-name toolkit for CIPHER entity resolution.

Pure-CPU name normalization, transliteration, phonetic keys, culture-aware
parsing, comparison, and blocking-key generation. See
``docs/entity-resolution.md`` §7.
"""

from cipher.names.address import AddressAgreement, address_name_agreement
from cipher.names.compare import Level, NameComparison, compare_names
from cipher.names.culture import Culture, infer_culture
from cipher.names.keys import KEY_TYPES, KEYS_VERSION, blocking_keys, entity_keys
from cipher.names.nicknames import canonical_forms, share_nickname_root
from cipher.names.normalize import fold, tokens
from cipher.names.parse import ParsedName, parse_name
from cipher.names.phonetic import phonetic_key
from cipher.names.script import Script, dominant_script
from cipher.names.translit import to_latin

__all__ = [
    "AddressAgreement",
    "address_name_agreement",
    "KEYS_VERSION",
    "KEY_TYPES",
    "Culture",
    "Level",
    "NameComparison",
    "ParsedName",
    "Script",
    "blocking_keys",
    "canonical_forms",
    "compare_names",
    "dominant_script",
    "entity_keys",
    "fold",
    "infer_culture",
    "parse_name",
    "phonetic_key",
    "share_nickname_root",
    "to_latin",
    "tokens",
]
