# isort: skip_file
from __future__ import annotations

# Import all models that have 'table=True'
##### WARNING: CAREFUL WHEN EDITING #####
##### ORDER OF IMPORTS MATTERS FOR TABLE DEPENDENCIES #####
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.dataset import DatasetTable
from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.enrichment_run import EnrichmentRunTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.tables.chunk import ChunkTable
from cipher.datastores.postgres.tables.device import DeviceTable
from cipher.datastores.postgres.tables.message import MessageTable
from cipher.datastores.postgres.tables.contact import ContactTable
from cipher.datastores.postgres.tables.user import UserTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.face_match import FaceMatchTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_name_key import EntityNameKeyTable
from cipher.datastores.postgres.tables.organization import OrganizationTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.mention_relationship import MentionRelationshipTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.entity_relationship_candidate import (
    EntityRelationshipCandidateTable,
)
from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.event import EventTable
from cipher.datastores.postgres.tables.event_participant import EventParticipantTable
from cipher.datastores.postgres.tables.event_place import EventPlaceTable
from cipher.datastores.postgres.tables.tag import TagTable
from cipher.datastores.postgres.tables.comment import CommentTable

__all__ = [
    "FileTable",
    "DatasetTable",
    "EnrichmentTable",
    "EnrichmentRunTable",
    "ImageTable",
    "ExtractedTextTable",
    "ChunkTable",
    "DeviceTable",
    "MessageTable",
    "ContactTable",
    "UserTable",
    "PersonTable",
    "FaceTable",
    "FaceMatchTable",
    "EntityTable",
    "EntityNameKeyTable",
    "OrganizationTable",
    "LocationTable",
    "SelectorTable",
    "MentionTable",
    "MentionRelationshipTable",
    "EntityRelationshipTable",
    "EntityRelationshipCandidateTable",
    "EntityMatchTable",
    "EventTable",
    "EventParticipantTable",
    "EventPlaceTable",
    "TagTable",
    "CommentTable",
]
