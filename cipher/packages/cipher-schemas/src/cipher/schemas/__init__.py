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
]
