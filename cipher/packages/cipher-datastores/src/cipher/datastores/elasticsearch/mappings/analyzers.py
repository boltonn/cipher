"""Elasticsearch analyzer, tokenizer, and filter definitions.

Grouped by purpose. Import the ones you need into index mapping files and
compose them into an analysis block via build_analysis().

Plugin requirements:
    - analysis-icu        : ICU_* analyzers (unicode normalization, collation)
    - analysis-smartcn    : CHINESE_* analyzer

Install on ES node:
    bin/elasticsearch-plugin install analysis-icu
    bin/elasticsearch-plugin install analysis-smartcn
"""

from enum import StrEnum


class AnalyzerName(StrEnum):
    """All available analyzer groups. Pass these to build_analysis()."""

    STANDARD = "standard"
    ENGLISH = "english"
    RUSSIAN = "russian"
    UKRAINIAN = "ukrainian"
    CHINESE = "chinese"
    ICU = "icu"
    AUTOCOMPLETE = "autocomplete"
    PHONE = "phone"


LOWERCASE_FILTER: dict = {"type": "lowercase"}

ASCII_FOLDING_FILTER: dict = {
    "type": "asciifolding",
    "preserve_original": True,
}

EDGE_NGRAM_FILTER: dict = {
    "type": "edge_ngram",
    "min_gram": 2,
    "max_gram": 20,
}

STOP_FILTER_EN: dict = {"type": "stop", "stopwords": "_english_"}
STEMMER_EN: dict = {"type": "stemmer", "language": "english"}

STOP_FILTER_RU: dict = {"type": "stop", "stopwords": "_russian_"}
STEMMER_RU: dict = {"type": "stemmer", "language": "russian"}

# Ukrainian has no built-in ES stopword list. Snowball handles the morphology;
# for production supply a custom stopwords_path file.
STEMMER_UK: dict = {"type": "snowball", "language": "Ukrainian"}

# ICU normalizer — unicode NFKC + case folding.
# Handles ligatures, compatibility characters, fullwidth forms, etc.
ICU_NORMALIZER_FILTER: dict = {
    "type": "icu_normalizer",
    "name": "nfkc_cf",  # nfkc + case fold
    "mode": "compose",
}

# ICU folding — broader than asciifolding: handles accents, Han unification, etc.
ICU_FOLDING_FILTER: dict = {"type": "icu_folding"}


# Standard — lowercase + ascii folding. Good default for mixed-language content
# where language is unknown at index time.
STANDARD_ANALYZER: dict = {
    "type": "custom",
    "tokenizer": "standard",
    "filter": ["lowercase", "ascii_folding"],
}

# English — stemming + stop words for better recall on prose.
ENGLISH_ANALYZER: dict = {
    "type": "custom",
    "tokenizer": "standard",
    "filter": ["lowercase", "stop_en", "stemmer_en"],
}

# Russian — Cyrillic-aware stemming and stop words.
RUSSIAN_ANALYZER: dict = {
    "type": "custom",
    "tokenizer": "standard",
    "filter": ["lowercase", "stop_ru", "stemmer_ru"],
}

# Ukrainian — snowball stemmer (no built-in ES language support).
# ICU normalizer runs first to normalize Cyrillic variants before stemming.
UKRAINIAN_ANALYZER: dict = {
    "type": "custom",
    "tokenizer": "standard",
    "filter": ["icu_normalizer", "lowercase", "stemmer_uk"],
}

# Chinese — smartcn plugin, HMM-based tokenizer for simplified + traditional.
# Self-contained analyzer type; no custom filter chain needed.
CHINESE_ANALYZER: dict = {"type": "smartcn"}

# ICU — best for truly mixed-language content in a single field
# (e.g. a message that's part English, part Chinese, part Russian).
# icu_tokenizer segments by Unicode line-breaking rules, works across scripts.
ICU_ANALYZER: dict = {
    "type": "custom",
    "tokenizer": "icu_tokenizer",
    "filter": ["icu_normalizer", "icu_folding", "lowercase"],
}

# Autocomplete — edge ngrams at index time, standard tokenization at query time.
AUTOCOMPLETE_INDEX_ANALYZER: dict = {
    "type": "custom",
    "tokenizer": "standard",
    "filter": ["lowercase", "edge_ngram"],
}

AUTOCOMPLETE_SEARCH_ANALYZER: dict = {
    "type": "custom",
    "tokenizer": "standard",
    "filter": ["lowercase"],
}

# Phone numbers — strip non-digits so +1 (212) 555-0100 matches 2125550100.
PHONE_NUMBER_ANALYZER: dict = {
    "type": "custom",
    "tokenizer": "keyword",
    "char_filter": ["phone_char_filter"],
    "filter": ["lowercase"],
}


PHONE_CHAR_FILTER: dict = {
    "type": "pattern_replace",
    "pattern": "[^0-9]",
    "replacement": "",
}

_REGISTRY: dict[AnalyzerName, dict] = {
    AnalyzerName.STANDARD: {
        "analyzer": {"standard_analyzer": STANDARD_ANALYZER},
        "filter": {"ascii_folding": ASCII_FOLDING_FILTER},
    },
    AnalyzerName.ENGLISH: {
        "analyzer": {"english_analyzer": ENGLISH_ANALYZER},
        "filter": {
            "stop_en": STOP_FILTER_EN,
            "stemmer_en": STEMMER_EN,
        },
    },
    AnalyzerName.RUSSIAN: {
        "analyzer": {"russian_analyzer": RUSSIAN_ANALYZER},
        "filter": {
            "stop_ru": STOP_FILTER_RU,
            "stemmer_ru": STEMMER_RU,
        },
    },
    AnalyzerName.UKRAINIAN: {
        "analyzer": {"ukrainian_analyzer": UKRAINIAN_ANALYZER},
        "filter": {
            "icu_normalizer": ICU_NORMALIZER_FILTER,
            "stemmer_uk": STEMMER_UK,
        },
    },
    AnalyzerName.CHINESE: {
        # smartcn is a self-contained type — no custom filters needed
        "analyzer": {"chinese_analyzer": CHINESE_ANALYZER},
    },
    AnalyzerName.ICU: {
        "analyzer": {"icu_analyzer": ICU_ANALYZER},
        "filter": {
            # icu_normalizer may also be registered by UKRAINIAN — identical
            # definitions, so merging is safe (last write wins, same value)
            "icu_normalizer": ICU_NORMALIZER_FILTER,
            "icu_folding": ICU_FOLDING_FILTER,
        },
    },
    AnalyzerName.AUTOCOMPLETE: {
        "analyzer": {
            "autocomplete_index": AUTOCOMPLETE_INDEX_ANALYZER,
            "autocomplete_search": AUTOCOMPLETE_SEARCH_ANALYZER,
        },
        "filter": {"edge_ngram": EDGE_NGRAM_FILTER},
    },
    AnalyzerName.PHONE: {
        "analyzer": {"phone_analyzer": PHONE_NUMBER_ANALYZER},
        "char_filter": {"phone_char_filter": PHONE_CHAR_FILTER},
    },
}


def build_analysis(*analyzer_names: AnalyzerName) -> dict:
    """Return an ES analysis block for the specified analyzers.

    Usage::

        analysis = build_analysis(AnalyzerName.STANDARD, AnalyzerName.RUSSIAN)

    Only the named analyzers and their dependencies are included — keeps index
    settings minimal and avoids registering plugins that aren't installed.
    """
    result: dict = {"analyzer": {}, "filter": {}, "char_filter": {}}
    for name in analyzer_names:
        entry = _REGISTRY[name]
        result["analyzer"].update(entry.get("analyzer", {}))
        result["filter"].update(entry.get("filter", {}))
        result["char_filter"].update(entry.get("char_filter", {}))

    # Drop empty sections — ES rejects empty analysis sub-objects
    return {k: v for k, v in result.items() if v}
