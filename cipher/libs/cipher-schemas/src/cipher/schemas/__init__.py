# isort: skip_file
from __future__ import annotations

# Import all models that have 'table=True'
##### WARNING: CAREFUL WHEN EDITING #####
##### ORDER OF IMPORTS MATTERS FOR TABLE DEPENDENCIES #####
from cipher.schemas.ingestion.file import File
from cipher.schemas.ingestion.dataset import Dataset
from cipher.schemas.ingestion.enrichment import Enrichment
from cipher.schemas.content.image import Image
from cipher.schemas.content.device import Device
from cipher.schemas.content.contact import Contact
from cipher.schemas.identity.person import Person
from cipher.schemas.identity.face import Face
from cipher.schemas.identity.face_match import FaceMatch
from cipher.schemas.graph.entity import Entity
from cipher.schemas.graph.organization import Organization
from cipher.schemas.graph.location import Location
from cipher.schemas.graph.selector import Selector
from cipher.schemas.graph.mention import Mention
from cipher.schemas.graph.entity_relationship import EntityRelationship, RelationshipCandidate
from cipher.schemas.graph.entity_match import EntityMatch
from cipher.schemas.graph.event_participant import EventParticipant
from cipher.schemas.graph.event_place import EventPlace
from cipher.schemas.graph.event import Event

__all__ = [
    "File",
    "Dataset",
    "Enrichment",
    "Image",
    "Device",
    "Contact",
    "Person",
    "Face",
    "FaceMatch",
    "Entity",
    "Organization",
    "Location",
    "Selector",
    "Mention",
    "EntityRelationship",
    "RelationshipCandidate",
    "EntityMatch",
    "Event",
    "EventParticipant",
    "EventPlace",
]
