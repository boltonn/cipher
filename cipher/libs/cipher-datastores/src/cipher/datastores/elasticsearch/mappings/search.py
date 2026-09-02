"""Elasticsearch index mapping for the messages (conversation chunks) index."""

from cipher.datastores.elasticsearch.mappings.analyzers import (
    AnalyzerName,
    build_analysis,
)
from cipher.datastores.elasticsearch.mappings.settings import DEFAULT_SETTINGS
from cipher.schemas.content.message import TEXT_EMBEDDING_DIMENSION

# Analyzers used by this index. Passed to build_analysis() so only these
# are registered — avoids requiring plugins that aren't installed.
TEXT_ANALYZERS: tuple[AnalyzerName, ...] = (
    AnalyzerName.STANDARD,
    AnalyzerName.ENGLISH,
    AnalyzerName.RUSSIAN,
    AnalyzerName.UKRAINIAN,
    AnalyzerName.CHINESE,
    AnalyzerName.ICU,
    AnalyzerName.PHONE,
)

# Text field sub-fields — one per language-aware analyzer.
# Applied to both `text` and `translation` so queries can target
# e.g. messages.text.russian for stemmed Cyrillic recall.
_TEXT_LANGUAGE_SUBFIELDS: dict = {
    "keyword": {"type": "keyword", "ignore_above": 512},
    "english": {"type": "text", "analyzer": "english_analyzer"},
    "russian": {"type": "text", "analyzer": "russian_analyzer"},
    "ukrainian": {"type": "text", "analyzer": "ukrainian_analyzer"},
    "chinese": {"type": "text", "analyzer": "chinese_analyzer"},
    "icu": {"type": "text", "analyzer": "icu_analyzer"},
}


def build_messages_mapping(
    embedding_size: int = TEXT_EMBEDDING_DIMENSION,
    text_analyzer: AnalyzerName = AnalyzerName.ENGLISH,
) -> dict:
    """Return the full index body (settings + mappings) for the messages index.

    Args:
        embedding_size: Embedding dimension — injected at runtime to stay in sync with
              the model constant rather than being hardcoded in the mapping.
        text_analyzer: Analyzer to use for text fields. Override to a different
                       analyzer if needed, e.g.:
                       build_messages_mapping(text_analyzer=AnalyzerName.ENGLISH)
    """
    analyzers: list[AnalyzerName] = [
        AnalyzerName.PHONE,
        AnalyzerName.ENGLISH,
        text_analyzer,
    ]
    return {
        "settings": {
            **DEFAULT_SETTINGS,
            "analysis": build_analysis(*analyzers),
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": embedding_size,
                    "index": True,
                    "similarity": "dot_product",
                },
                "title": {  # also subject for emails
                    "type": "text",
                    "analyzer": f"{text_analyzer}_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
                },
                "subject": {"type": "alias", "path": "title"},
                "message_id": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "from": {"type": "keyword"},
                "to": {"type": "keyword"},
                "cc": {"type": "keyword"},
                "bcc": {"type": "keyword"},
                "conversation_id": {"type": "keyword"},
                "date_sent": {"type": "date"},
                "text": {
                    "type": "text",
                    "analyzer": f"{text_analyzer}_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
                },
                "tags": {"type": "keyword"},
                "keywords": {"type": "keyword"},
            }
        },
    }
