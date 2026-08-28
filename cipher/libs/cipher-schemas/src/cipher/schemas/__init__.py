# isort: skip_file
from __future__ import annotations

# Import all models that have 'table=True'
##### WARNING: CAREFUL WHEN EDITING #####
##### ORDER OF IMPORTS MATTERS FOR TABLE DEPENDENCIES #####
from cipher.schemas.file import File
from cipher.schemas.dataset import Dataset
from cipher.schemas.enrichment import Enrichment
from cipher.schemas.image import Image
from cipher.schemas.device import Device
from cipher.schemas.contact import Contact
from cipher.schemas.person import Person
from cipher.schemas.face import Face
from cipher.schemas.face_match import FaceMatch
from cipher.schemas.entity import Entity
from cipher.schemas.organization import Organization
from cipher.schemas.location import Location
from cipher.schemas.selector import Selector
from cipher.schemas.mention import Mention
from cipher.schemas.entity_relationship import EntityRelationship, RelationshipCandidate
from cipher.schemas.entity_match import EntityMatch

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
]
