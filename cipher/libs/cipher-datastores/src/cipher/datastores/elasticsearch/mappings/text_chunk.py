"""Elasticsearch index mapping for the unified `text_chunks` index.

Documents and emails are chunked into the same index -- one flat document
per chunk, discriminated by `filetype_group` -- so "search everything" is a
single query rather than a federated multi-index one. Raw BM25/kNN scores
aren't directly comparable across content types with very different average
chunk lengths (a short email reply vs. a 512-token document chunk), so
cross-type ranking should stay a documented caveat for the search API layer
to account for (e.g. score-normalize before merging), not something this
mapping tries to solve.
"""

from cipher.datastores.elasticsearch.mappings.analyzers import AnalyzerName, build_analysis
from cipher.datastores.elasticsearch.mappings.settings import DEFAULT_SETTINGS
from cipher.schemas.content.message import TEXT_EMBEDDING_DIMENSION

_PARTICIPANT_PROPERTIES: dict = {
    "properties": {
        "name": {"type": "keyword"},
        "type": {"type": "keyword"},
        "value": {"type": "keyword"},
    }
}

# Structural/layout data (tables, document_structure, bounding_box) is stored
# for display/highlighting but never queried directly, so it's mapped
# `enabled: false` -- retrievable via _source, not indexed.
_NOT_INDEXED: dict = {"type": "object", "enabled": False}


def build_text_chunk_mapping(
    embedding_size: int = TEXT_EMBEDDING_DIMENSION,
    text_analyzer: AnalyzerName = AnalyzerName.ENGLISH,
) -> dict:
    """Return the full index body (settings + mappings) for the text_chunks index."""
    analyzers: list[AnalyzerName] = [AnalyzerName.ENGLISH, text_analyzer]
    return {
        "settings": {
            **DEFAULT_SETTINGS,
            "analysis": build_analysis(*analyzers),
        },
        "mappings": {
            "properties": {
                # Shared (TextChunk)
                "filetype_group": {"type": "keyword"},
                "filetype": {"type": "keyword"},
                "dataset_id": {"type": "keyword"},
                "file_id": {"type": "keyword"},
                "sha256": {"type": "keyword"},
                "duplicate_file_ids": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "start_offset": {"type": "integer"},
                "end_offset": {"type": "integer"},
                "text": {
                    "type": "text",
                    "analyzer": f"{text_analyzer}_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
                },
                "embedding": {
                    "type": "dense_vector",
                    "dims": embedding_size,
                    "index": True,
                    "similarity": "dot_product",
                },
                "tags": {"type": "keyword"},
                "keywords": {"type": "keyword"},
                "date_created": {"type": "date"},
                # Shared across document/email (ContentMetadata-derived)
                "title": {
                    "type": "text",
                    "analyzer": f"{text_analyzer}_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
                },
                "sent_from": _PARTICIPANT_PROPERTIES,
                "sent_to": _PARTICIPANT_PROPERTIES,
                # Document-specific
                "filename": {"type": "keyword"},
                "authors": {"type": "keyword"},
                "date_content_created": {"type": "date"},
                "date_content_modified": {"type": "date"},
                "page_count": {"type": "integer"},
                "detected_language": {"type": "keyword"},
                "tables": _NOT_INDEXED,
                "document_structure": _NOT_INDEXED,
                "page_number": {"type": "integer"},
                "heading_path": {"type": "keyword"},
                "token_count": {"type": "integer"},
                "bounding_box": _NOT_INDEXED,
                # Email-specific
                "sender": _PARTICIPANT_PROPERTIES,
                "cc": _PARTICIPANT_PROPERTIES,
                "bcc": _PARTICIPANT_PROPERTIES,
                "date_sent": {"type": "date"},
                "conversation_id": {"type": "keyword"},
                "email_client": {"type": "keyword"},
                "state": {"type": "keyword"},
                "message_id": {"type": "keyword"},
                "labels": {"type": "keyword"},
            }
        },
    }
